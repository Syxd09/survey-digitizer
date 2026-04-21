"""
SurveyProcessor — Hydra v11.0 PRODUCTION
=========================================
Full pipeline:
  perspective correction → lighting normalisation → adaptive binarisation
  → deskew → content-type detection → language detection
  → PaddleOCR (printed) | EasyOCR (multilingual) | TrOCR (handwriting)
  → img2table (structured tables)
  → universal layout reconstruction
  → rapidfuzz semantic correction
  → Claude vision fallback (low-confidence crops)
  → SQLite-backed active-learning memory
"""

import base64
import io
import json
import logging
import os
import sqlite3
import threading
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ── Optional imports with graceful degradation ────────────────────────────────

try:
    from skimage.filters import threshold_sauvola
    SAUVOLA_AVAILABLE = True
except ImportError:
    SAUVOLA_AVAILABLE = False
    logger.warning("[IMPORT] scikit-image not found — falling back to OTSU binarisation")

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False
    logger.warning("[IMPORT] PaddleOCR not found — using EasyOCR only")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("[IMPORT] EasyOCR not found — OCR accuracy will be limited")

try:
    from img2table.document import Image as Img2TableImage
    from img2table.ocr import EasyOCR as Img2EasyOCR
    IMG2TABLE_AVAILABLE = True
except ImportError:
    IMG2TABLE_AVAILABLE = False
    logger.warning("[IMPORT] img2table not found — using contour-based table detection")

try:
    from rapidfuzz import fuzz
    from rapidfuzz import process as fuzz_process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("[IMPORT] rapidfuzz not found — using static correction dictionary only")

try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.warning("[IMPORT] langdetect not found — defaulting to English")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("[IMPORT] anthropic SDK not found — Claude fallback disabled")


# ── Domain vocabulary for fuzzy correction ────────────────────────────────────

DOMAIN_VOCAB: List[str] = [
    "Read-Only", "Write", "Full Access", "Insert", "Update", "Delete",
    "Exempt", "Analyst", "Engineer", "Admin", "Manager", "Supervisor",
    "Approved", "Rejected", "Pending", "Completed", "Cancelled",
    "Signature", "Date", "Name", "Address", "Phone", "Email",
    "Yes", "No", "N/A", "True", "False",
    "View", "Select", "Execute", "Create", "Drop",
]


class SurveyProcessor:
    """
    Singleton-safe OCR processor.  Instantiate ONCE at application startup
    (via FastAPI lifespan) and reuse the same instance for every request.
    """

    def __init__(self, custom_vocab: Optional[List[str]] = None):
        import torch

        self.device = self._pick_device(torch)
        logger.info(f"[PROCESSOR] Initialising on device: {self.device}")

        # Extend domain vocabulary if caller supplied extras
        self.vocab = DOMAIN_VOCAB + (custom_vocab or [])

        # ── Load OCR engines ────────────────────────────────────────────────
        self.paddle_reader = self._load_paddle()
        self.easy_reader   = self._load_easyocr()
        self.troc_model, self.troc_processor = self._load_trocr(torch)

        # ── img2table (optional) ────────────────────────────────────────────
        self.img2table_ocr = self._load_img2table_ocr()

        # ── Active-learning memory (SQLite + in-memory LRU) ─────────────────
        self.memory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "feedback_loop", "memory.db"
        )
        self._db_lock = threading.Lock()
        self._memory_cache: Dict[str, str] = {}
        self._init_memory_db()

        logger.info("[PROCESSOR] Initialisation complete")

    # ═══════════════════════════════════════════════════════════════════════════
    # Initialisation helpers
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _pick_device(torch) -> str:
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_paddle(self) -> Optional[Any]:
        if not PADDLE_AVAILABLE:
            return None
        try:
            use_gpu = self.device in ("cuda",)
            reader = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=use_gpu,
                show_log=False,
                det_db_score_mode="slow",   # higher accuracy
                rec_algorithm="SVTR_LCNet",
            )
            logger.info(f"[PADDLE] Loaded (gpu={use_gpu})")
            return reader
        except Exception as exc:
            logger.warning(f"[PADDLE] Failed to load: {exc}")
            return None

    def _load_easyocr(self) -> Optional[Any]:
        if not EASYOCR_AVAILABLE:
            return None
        try:
            gpu = self.device in ("cuda", "mps")
            reader = easyocr.Reader(
                ["en", "pt", "es", "fr", "de", "it"],
                gpu=gpu,
                model_storage_directory=os.path.join(
                    os.path.expanduser("~"), ".EasyOCR", "model"
                ),
            )
            logger.info(f"[EASYOCR] Loaded (gpu={gpu}, 6 languages)")
            return reader
        except Exception as exc:
            logger.warning(f"[EASYOCR] Failed to load: {exc}")
            return None

    def _load_trocr(self, torch) -> Tuple[Optional[Any], Optional[Any]]:
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            proc  = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
            model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
            model.to(self.device)
            model.eval()
            logger.info(f"[TROCR] Loaded on {self.device}")
            return model, proc
        except Exception as exc:
            logger.warning(f"[TROCR] Failed to load: {exc}")
            return None, None

    def _load_img2table_ocr(self) -> Optional[Any]:
        if not IMG2TABLE_AVAILABLE or not EASYOCR_AVAILABLE:
            return None
        try:
            return Img2EasyOCR(lang=["en", "pt"])
        except Exception as exc:
            logger.warning(f"[IMG2TABLE] OCR init failed: {exc}")
            return None

    def _init_memory_db(self):
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with self._db_lock:
            conn = sqlite3.connect(self.memory_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS patterns "
                "(hash TEXT PRIMARY KEY, text TEXT, ts REAL, use_count INTEGER DEFAULT 1)"
            )
            conn.commit()
            # Warm the in-memory cache (top 2000 most-used patterns)
            rows = conn.execute(
                "SELECT hash, text FROM patterns ORDER BY use_count DESC LIMIT 2000"
            ).fetchall()
            self._memory_cache = {r[0]: r[1] for r in rows}
            conn.close()
        logger.info(f"[MEMORY] Loaded {len(self._memory_cache)} cached patterns")

    # ═══════════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════════

    def process(self, pil_image: PILImage.Image) -> Dict[str, Any]:
        """Full pipeline entry point.  Returns standardised JSON result dict."""
        t_start = time.time()

        # Normalise colour space
        img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)

        # ── Stage 1: quality gate (run ONCE, pass report downstream) ────────
        quality = self._check_quality(img)
        logger.info(f"[PIPELINE] Quality: {quality}")

        # ── Stage 2: preprocessing chain ────────────────────────────────────
        img = self._correct_perspective(img)
        img = self._normalize_lighting(img) if quality["brightness"] < 80 else self._enhance_image(img)
        img = self._enhance_for_handwriting(img)
        img = self._deskew(img)

        if quality["blur_score"] < 80 and SAUVOLA_AVAILABLE:
            img = self._binarize_sauvola(img)
        elif quality["blur_score"] < 10:
            img = self._deblur_image(img)

        # ── Stage 3: content-type detection ─────────────────────────────────
        hw_ratio   = self._estimate_handwriting_ratio(img)
        language   = self._detect_language(img)
        logger.info(f"[PIPELINE] handwriting_ratio={hw_ratio:.2f}, lang={language}")

        # ── Stage 4: structural scan (table cells / checkboxes) ─────────────
        _, structural_boxes = self._detect_table_cells(img)

        # ── Stage 5: text scan (engine-routed) ──────────────────────────────
        text_regions = self._get_full_text_scan(img, hw_ratio, language)

        # ── Stage 6: reconstruction ──────────────────────────────────────────
        result = self._reconstruct_universal(structural_boxes, text_regions, img, quality)

        elapsed = round(time.time() - t_start, 2)
        result["diagnostics"].update({
            "quality":              quality,
            "handwriting_ratio":    round(hw_ratio, 3),
            "detected_language":    language,
            "processing_duration":  elapsed,
            "logic_version":        "Hydra-v11.0-PRODUCTION",
        })
        logger.info(f"[PIPELINE] Done in {elapsed}s — {len(result['questions'])} fields extracted")
        return result

    def register_feedback(self, image_hash: str, text: str) -> bool:
        """Persist a user correction and update the in-memory cache."""
        try:
            with self._db_lock:
                conn = sqlite3.connect(self.memory_path)
                conn.execute(
                    "INSERT INTO patterns (hash, text, ts, use_count) VALUES (?,?,?,1) "
                    "ON CONFLICT(hash) DO UPDATE SET text=excluded.text, ts=excluded.ts, "
                    "use_count=use_count+1",
                    (image_hash, text, time.time()),
                )
                conn.commit()
                conn.close()
            self._memory_cache[image_hash] = text
            logger.info(f"[MEMORY] Learned {image_hash} → {text!r}")
            return True
        except Exception as exc:
            logger.error(f"[MEMORY] Save failed: {exc}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Preprocessing pipeline
    # ═══════════════════════════════════════════════════════════════════════════

    def _correct_perspective(self, img: np.ndarray) -> np.ndarray:
        """Warp trapezoidal (phone-shot) documents back to a flat rectangle."""
        try:
            h, w = img.shape[:2]
            img_area = h * w

            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges   = cv2.Canny(blurred, 50, 150)
            kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            edges   = cv2.dilate(edges, kernel, iterations=1)

            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

            for cnt in contours:
                peri  = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                if len(approx) != 4:
                    continue

                quad_area = cv2.contourArea(approx)
                ratio = quad_area / img_area

                # Must be a meaningful document region, not image border or noise
                if not (0.20 < ratio < 0.97):
                    continue

                pts  = approx.reshape(4, 2).astype(np.float32)
                rect = self._order_points(pts)
                ww   = int(max(
                    np.linalg.norm(rect[0] - rect[1]),
                    np.linalg.norm(rect[2] - rect[3]),
                ))
                wh   = int(max(
                    np.linalg.norm(rect[0] - rect[3]),
                    np.linalg.norm(rect[1] - rect[2]),
                ))
                dst = np.array([[0,0],[ww-1,0],[ww-1,wh-1],[0,wh-1]], dtype=np.float32)
                M   = cv2.getPerspectiveTransform(rect, dst)
                warped = cv2.warpPerspective(img, M, (ww, wh), flags=cv2.INTER_CUBIC)
                logger.info(f"[PERSPECTIVE] Corrected quad ratio={ratio:.2f}, size={ww}x{wh}")
                return warped
        except Exception as exc:
            logger.warning(f"[PERSPECTIVE] Failed: {exc}")
        return img

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s         = pts.sum(axis=1)
        rect[0]   = pts[np.argmin(s)]   # top-left
        rect[2]   = pts[np.argmax(s)]   # bottom-right
        diff      = np.diff(pts, axis=1)
        rect[1]   = pts[np.argmin(diff)]  # top-right
        rect[3]   = pts[np.argmax(diff)]  # bottom-left
        return rect

    def _binarize_sauvola(self, img: np.ndarray) -> np.ndarray:
        """Adaptive Sauvola threshold — handles uneven lighting / shadows."""
        try:
            gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = threshold_sauvola(gray, window_size=25, k=0.2)
            binary = ((gray > thresh) * 255).astype(np.uint8)
            return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        except Exception as exc:
            logger.warning(f"[SAUVOLA] Failed: {exc}")
            return img

    def _enhance_image(self, img: np.ndarray) -> np.ndarray:
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)
        except Exception:
            return img

    def _normalize_lighting(self, img: np.ndarray) -> np.ndarray:
        """CLAHE on LAB L-channel for dark/poorly-lit scans."""
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(12, 12))
            return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)
        except Exception:
            return img

    def _enhance_for_handwriting(self, img: np.ndarray) -> np.ndarray:
        try:
            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray, None, 3, 7, 21)
            clahe   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            return cv2.cvtColor(clahe.apply(denoised), cv2.COLOR_GRAY2BGR)
        except Exception:
            return img

    def _deblur_image(self, img: np.ndarray) -> np.ndarray:
        try:
            kernel   = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
            sharp    = cv2.filter2D(img, -1, kernel)
            gaussian = cv2.GaussianBlur(sharp, (0, 0), 2.0)
            return cv2.addWeighted(sharp, 1.5, gaussian, -0.5, 0)
        except Exception:
            return img

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        try:
            gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray   = cv2.bitwise_not(gray)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 10:
                return img
            angle  = cv2.minAreaRect(coords)[-1]
            if -3 < angle < 3 or 87 < angle < 93:
                return img
            angle  = -(90 + angle) if angle < -45 else -angle
            h, w   = img.shape[:2]
            M      = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            return img

    def _skeletonize(self, img: np.ndarray) -> np.ndarray:
        """Zhang-Suen thinning with a hard iteration cap to prevent runaway loops."""
        try:
            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            _, bw   = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
            skel    = np.zeros_like(bw)
            tmp     = bw.copy()
            for _ in range(100):            # hard cap — prevents infinite loop
                eroded = cv2.erode(tmp, element)
                diff   = cv2.subtract(tmp, cv2.dilate(eroded, element))
                skel   = cv2.bitwise_or(skel, diff)
                tmp    = eroded.copy()
                if cv2.countNonZero(tmp) == 0:
                    break
            return cv2.bitwise_not(skel)
        except Exception:
            return img

    # ═══════════════════════════════════════════════════════════════════════════
    # Content-type & language detection
    # ═══════════════════════════════════════════════════════════════════════════

    def _estimate_handwriting_ratio(self, img: np.ndarray) -> float:
        """
        High coefficient of variation in connected-component areas → handwriting.
        Low CV → uniform printed glyphs.
        """
        try:
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 5]
            if len(areas) < 5:
                return 0.0
            cv_val = float(np.std(areas)) / (float(np.mean(areas)) + 1e-6)
            return min(1.0, cv_val / 60.0)
        except Exception:
            return 0.3   # assume mixed if detection fails

    def _detect_language(self, img: np.ndarray) -> str:
        """Quick language detection via EasyOCR + langdetect."""
        if not LANGDETECT_AVAILABLE or self.easy_reader is None:
            return "en"
        try:
            h, w  = img.shape[:2]
            small = cv2.resize(img, (min(w, 600), min(h, 400)))
            texts = self.easy_reader.readtext(small, detail=0, paragraph=True)
            combined = " ".join(texts[:6])
            if len(combined.strip()) > 10:
                return langdetect.detect(combined)
        except Exception:
            pass
        return "en"

    # ═══════════════════════════════════════════════════════════════════════════
    # Quality assessment
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_quality(self, img: np.ndarray) -> Dict[str, Any]:
        gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mean, std  = cv2.meanStdDev(gray)
        brightness = float(mean[0][0])
        contrast   = float(std[0][0])

        warnings = []
        if blur_score < 100:
            warnings.append("LOW_RESOLUTION_OR_BLURRY")
        if brightness < 40:
            warnings.append("LOW_LIGHTING")
        if contrast < 20:
            warnings.append("LOW_CONTRAST")

        return {
            "status":     "POOR" if warnings else "GOOD",
            "blur_score": round(blur_score, 2),
            "brightness": round(brightness, 2),
            "contrast":   round(contrast, 2),
            "warnings":   warnings,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # OCR engines
    # ═══════════════════════════════════════════════════════════════════════════

    def _run_paddle_ocr(self, img: np.ndarray) -> List[Dict]:
        """PaddleOCR — fast, accurate for printed/typed text."""
        if self.paddle_reader is None:
            return []
        try:
            result = self.paddle_reader.ocr(img, cls=True)
            if not result or result[0] is None:
                return []
            regions = []
            for line in result[0]:
                if not line:
                    continue
                pts, (text, conf) = line
                x1 = int(min(p[0] for p in pts))
                y1 = int(min(p[1] for p in pts))
                x2 = int(max(p[0] for p in pts))
                y2 = int(max(p[1] for p in pts))
                regions.append({
                    "text":   text,
                    "bbox":   (x1, y1, x2, y2),
                    "conf":   float(conf),
                    "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                    "engine": "paddle",
                })
            return regions
        except Exception as exc:
            logger.warning(f"[PADDLE] OCR failed: {exc}")
            return []

    def _run_easy_ocr(self, img: np.ndarray) -> List[Dict]:
        """EasyOCR — multilingual, good for mixed scripts."""
        if self.easy_reader is None:
            return []
        try:
            params = {
                "text_threshold": 0.3,
                "low_text":       0.2,
                "link_threshold": 0.4,
                "canvas_size":    2560,
                "mag_ratio":      1.0,
            }
            raw = self.easy_reader.readtext(img, **params)

            # Attempt 2× upscale if sparse results
            if len(raw) < 15:
                h, w   = img.shape[:2]
                img_2x = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
                raw_2x = self.easy_reader.readtext(img_2x, **params)
                if len(raw_2x) > len(raw):
                    raw = [([[p[0]/2, p[1]/2] for p in b], t, p_)
                           for b, t, p_ in raw_2x]

            regions = []
            for bbox, text, conf in raw:
                x1 = int(bbox[0][0]); y1 = int(bbox[0][1])
                x2 = int(bbox[2][0]); y2 = int(bbox[2][1])
                regions.append({
                    "text":   text,
                    "bbox":   (x1, y1, x2, y2),
                    "conf":   float(conf),
                    "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                    "engine": "easyocr",
                })
            return regions
        except Exception as exc:
            logger.warning(f"[EASYOCR] Failed: {exc}")
            return []

    def _get_full_text_scan(
        self,
        img: np.ndarray,
        hw_ratio: float,
        language: str,
    ) -> List[Dict]:
        """
        Route to the best engine based on content type, then merge results.
        Strategy:
          hw_ratio < 0.4  → PaddleOCR primary, EasyOCR supplement
          hw_ratio >= 0.4 → EasyOCR primary (TrOCR applied per-crop later)
        """
        primary: List[Dict] = []
        supplement: List[Dict] = []

        if hw_ratio < 0.4 and self.paddle_reader is not None:
            primary    = self._run_paddle_ocr(img)
            supplement = self._run_easy_ocr(img) if len(primary) < 10 else []
        else:
            primary    = self._run_easy_ocr(img)

        # Merge, deduplicating by IoU
        merged = self._merge_regions(primary, supplement)

        # Filter noise
        noise_patterns = [
            "pylance", "reportundefinedvariable", "ln ", "col ",
            "keyword arguments", '"df"',
        ]
        filtered = []
        for r in merged:
            low = r["text"].lower()
            if any(p in low for p in noise_patterns):
                continue
            if len(r["text"].strip()) < 3 and r["conf"] < 0.9:
                continue
            filtered.append(r)

        logger.info(
            f"[TEXT_SCAN] engine={'paddle' if hw_ratio<0.4 else 'easyocr'}, "
            f"primary={len(primary)}, merged={len(merged)}, filtered={len(filtered)}"
        )
        return filtered

    @staticmethod
    def _merge_regions(primary: List[Dict], supplement: List[Dict]) -> List[Dict]:
        """
        Add supplement regions that don't significantly overlap with any
        primary region (IoU < 0.3).
        """
        if not supplement:
            return primary

        def iou(a, b) -> float:
            ax1, ay1, ax2, ay2 = a["bbox"]
            bx1, by1, bx2, by2 = b["bbox"]
            ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            if inter == 0:
                return 0.0
            area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
            area_b = max(1, (bx2 - bx1) * (by2 - by1))
            return inter / (area_a + area_b - inter)

        merged = list(primary)
        for s in supplement:
            if all(iou(s, p) < 0.3 for p in primary):
                merged.append(s)
        return merged

    def _extract_text_with_troc(
        self,
        img_crop: np.ndarray,
        high_precision: bool = False,
    ) -> str:
        """TrOCR for handwritten field crops."""
        if self.troc_model is None or self.troc_processor is None:
            return ""
        try:
            import torch

            if img_crop is None or img_crop.size == 0:
                return ""
            if img_crop.shape[0] < 2 or img_crop.shape[1] < 2:
                return ""

            h, w = img_crop.shape[:2]
            if h < 60 or w < 100:
                scale   = 2.0
                img_crop = cv2.resize(img_crop, None, fx=scale, fy=scale,
                                      interpolation=cv2.INTER_CUBIC)

            if high_precision:
                gray   = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) \
                         if len(img_crop.shape) == 3 else img_crop
                kernel = np.ones((2, 2), np.uint8)
                inv    = cv2.bitwise_not(gray)
                dilated = cv2.dilate(inv, kernel, iterations=1)
                img_crop = cv2.bitwise_not(dilated)
                if len(img_crop.shape) == 2:
                    img_crop = cv2.cvtColor(img_crop, cv2.COLOR_GRAY2RGB)

            pil_img  = PILImage.fromarray(img_crop)
            pixel_v  = self.troc_processor(pil_img, return_tensors="pt").pixel_values
            pixel_v  = pixel_v.to(self.device)

            with torch.no_grad():
                ids = self.troc_model.generate(
                    pixel_v,
                    max_length=64,
                    num_beams=10 if high_precision else 4,
                    early_stopping=True,
                    repetition_penalty=1.2,
                )
            return self.troc_processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        except Exception as exc:
            logger.warning(f"[TROCR] Failed: {exc}")
            return ""

    def _claude_verify_crop(self, img_crop: np.ndarray, context_label: str) -> str:
        """
        Claude claude-opus-4-6 vision fallback for crops with confidence < 0.45.
        Requires ANTHROPIC_API_KEY env variable.
        """
        if not ANTHROPIC_AVAILABLE:
            return ""
        try:
            rgb  = cv2.cvtColor(img_crop, cv2.COLOR_BGR2RGB) \
                   if len(img_crop.shape) == 3 else img_crop
            pil  = PILImage.fromarray(rgb)
            buf  = io.BytesIO()
            pil.save(buf, format="PNG")
            b64  = base64.b64encode(buf.getvalue()).decode()

            client = anthropic.Anthropic()
            msg    = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=64,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type":   "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/png",
                                "data":       b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"This is a cropped field from a form labelled '{context_label}'. "
                                "Return ONLY the exact text you can read. "
                                "If it is a signature, return [SIGNATURE]. "
                                "If it is blank or empty, return [BLANK]. "
                                "No explanation, no punctuation outside the answer."
                            ),
                        },
                    ],
                }],
            )
            result = msg.content[0].text.strip()
            logger.info(f"[CLAUDE] Verified crop '{context_label}' → {result!r}")
            return result
        except Exception as exc:
            logger.warning(f"[CLAUDE] Verify failed: {exc}")
            return ""

    # ═══════════════════════════════════════════════════════════════════════════
    # Structural detection
    # ═══════════════════════════════════════════════════════════════════════════

    def _detect_table_cells(self, img: np.ndarray) -> Tuple[bool, List[Dict]]:
        """
        Try img2table first (handles borderless tables).
        Fall back to contour-based detection.
        """
        if IMG2TABLE_AVAILABLE and self.img2table_ocr is not None:
            cells = self._detect_via_img2table(img)
            if cells:
                logger.info(f"[TABLE] img2table found {len(cells)} cells")
                return True, cells

        return self._detect_via_contours(img)

    def _detect_via_img2table(self, img: np.ndarray) -> List[Dict]:
        try:
            rgb     = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = PILImage.fromarray(rgb)
            doc     = Img2TableImage(src=pil_img)
            tables  = doc.extract_tables(
                ocr=self.img2table_ocr,
                implicit_rows=True,
                borderless_tables=True,
                min_confidence=50,
            )
            cells = []
            for table in tables:
                for row in table.content.values():
                    for cell in row:
                        if cell.bbox is None:
                            continue
                        x1, y1, x2, y2 = (
                            cell.bbox.x1, cell.bbox.y1,
                            cell.bbox.x2, cell.bbox.y2,
                        )
                        cells.append({
                            "x": x1, "y": y1,
                            "w": x2 - x1, "h": y2 - y1,
                            "bbox": (x1, y1, x2, y2),
                            "text": cell.value or "",
                        })
            return cells
        except Exception as exc:
            logger.warning(f"[IMG2TABLE] Failed: {exc}")
            return []

    def _detect_via_contours(self, img: np.ndarray) -> Tuple[bool, List[Dict]]:
        try:
            gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, bw  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(bw, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            img_area = img.shape[0] * img.shape[1]
            cells    = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if area < img_area * 0.0005:
                    continue
                if not (15 < w < img.shape[1] * 0.8 and 15 < h < img.shape[0] * 0.8):
                    continue
                ar = w / float(h)
                if not (0.4 < ar < 12):
                    continue
                cells.append({"x": x, "y": y, "w": w, "h": h, "bbox": (x, y, x+w, y+h)})

            if not cells:
                return False, []

            rects = [[c["x"], c["y"], c["w"], c["h"]] for c in cells]
            rects, _ = cv2.groupRectangles(rects, 1, 0.2)
            dedup = [{"x":r[0],"y":r[1],"w":r[2],"h":r[3],"bbox":(r[0],r[1],r[0]+r[2],r[1]+r[3])}
                     for r in rects]

            pruned = []
            for i, c1 in enumerate(dedup):
                if c1["w"] > img.shape[1] * 0.4:
                    pruned.append(c1)
                    continue
                has_sibling = any(
                    i != j and
                    np.hypot(c1["x"] - c2["x"], c1["y"] - c2["y"]) < 250
                    for j, c2 in enumerate(dedup)
                )
                if has_sibling:
                    pruned.append(c1)

            logger.info(f"[CONTOURS] {len(cells)} raw → {len(dedup)} dedup → {len(pruned)} pruned")
            return len(pruned) > 0, pruned
        except Exception as exc:
            logger.warning(f"[CONTOURS] Failed: {exc}")
            return False, []

    def _detect_signature(self, img_crop: np.ndarray) -> bool:
        """
        Improved signature detection:
        density + max-component ratio + wide aspect ratio guard.
        """
        try:
            if img_crop is None or img_crop.size == 0:
                return False
            gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) \
                   if len(img_crop.shape) == 3 else img_crop
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            density = cv2.countNonZero(bw) / bw.size

            n, _, stats, _ = cv2.connectedComponentsWithStats(bw)
            if n < 2:
                return False

            areas = stats[1:, cv2.CC_STAT_AREA]
            max_ratio = np.max(areas) / bw.size

            h, w = img_crop.shape[:2]
            aspect = w / max(h, 1)

            # Signatures: dense ink, large connected mass, typically wide
            return density > 0.12 and max_ratio > 0.04 and aspect > 1.5
        except Exception:
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Semantic correction
    # ═══════════════════════════════════════════════════════════════════════════

    def _semantic_correction(self, text: str) -> str:
        if not text or len(text.strip()) < 2:
            return text

        # 1. Rapidfuzz fuzzy match against domain vocabulary
        if RAPIDFUZZ_AVAILABLE and len(text) > 2:
            try:
                match, score, _ = fuzz_process.extractOne(
                    text, self.vocab, scorer=fuzz.WRatio
                )
                # Only accept correction when very similar AND not much longer
                if score >= 88 and abs(len(text) - len(match)) <= 4:
                    return match
            except Exception:
                pass

        # 2. Legacy static mapping (kept as last resort for the most common artifacts)
        _STATIC_MAP = {
            "twirted":    "(Write)",
            "fvll":       "(Full)",
            "fvill":      "(Full)",
            "cfuid":      "(Full)",
            "read-onlyy": "(Read-Only)",
            "vieww":      "View",
            "exemptt":    "Exempt",
        }
        low = text.lower().strip()
        for k, v in _STATIC_MAP.items():
            if k in low:
                return v

        return text

    # ═══════════════════════════════════════════════════════════════════════════
    # Layout reconstruction
    # ═══════════════════════════════════════════════════════════════════════════

    def _reconstruct_universal(
        self,
        boxes: List[Dict],
        text_regions: List[Dict],
        img: np.ndarray,
        quality: Dict,
    ) -> Dict[str, Any]:
        questions: List[Dict] = []

        if not text_regions:
            return {
                "questions": [],
                "diagnostics": {"logic": "EMPTY_PAGE"},
            }

        text_regions.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))
        claimed_boxes: set = set()
        claimed_text: set  = set()

        # ── Pass A: checkbox / MCQ mapping ───────────────────────────────────
        for i, t in enumerate(text_regions):
            if t["conf"] < 0.1:
                continue
            tx, ty = t["center"]

            nearby = []
            for j, b in enumerate(boxes):
                if j in claimed_boxes:
                    continue
                bx = b["x"] + b["w"] / 2
                by = b["y"] + b["h"] / 2
                if np.hypot(tx - bx, ty - by) < 350:
                    nearby.append((np.hypot(tx - bx, ty - by), j, b))

            valid = [n for n in nearby if abs(n[2]["y"] - t["bbox"][1]) < 60]
            if not valid:
                continue

            claimed_text.add(i)
            valid.sort(key=lambda x: x[0])
            selected_val = None
            max_dark     = 0.0

            for dist, idx, b in valid:
                claimed_boxes.add(idx)
                crop = img[b["bbox"][1]:b["bbox"][3], b["bbox"][0]:b["bbox"][2]]
                if crop.size > 0:
                    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    th = cv2.adaptiveThreshold(
                        g, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
                        11, 2,
                    )
                    dr = cv2.countNonZero(th) / th.size
                    if dr > max_dark and dr > 0.1:
                        max_dark     = dr
                        selected_val = t["text"]

            questions.append({
                "question":  self._semantic_correction(t["text"]),
                "options":   [f"Option {k+1}" for k in range(len(valid))],
                "selected":  selected_val,
                "confidence": t["conf"],
                "status":    "OK" if selected_val else "UNSELECTED",
            })

        # ── Pass B: key-value / list mapping for unclaimed text ───────────────
        unclaimed = sorted(
            [i for i in range(len(text_regions))
             if i not in claimed_text and text_regions[i]["conf"] > 0.1],
            key=lambda i: text_regions[i]["bbox"][1],
        )

        rows: List[List[int]] = []
        if unclaimed:
            cur_row   = [unclaimed[0]]
            row_y_sum = text_regions[unclaimed[0]]["bbox"][1]
            for idx in unclaimed[1:]:
                avg_y = row_y_sum / len(cur_row)
                if abs(text_regions[idx]["bbox"][1] - avg_y) < 55:
                    cur_row.append(idx)
                    row_y_sum += text_regions[idx]["bbox"][1]
                else:
                    rows.append(cur_row)
                    cur_row   = [idx]
                    row_y_sum = text_regions[idx]["bbox"][1]
            if cur_row:
                rows.append(cur_row)

        for row_idx_list in rows:
            if len(row_idx_list) >= 2:
                row_idx_list.sort(key=lambda i: text_regions[i]["bbox"][0])
                key_i, val_i = row_idx_list[0], row_idx_list[-1]
                key_text = self._semantic_correction(text_regions[key_i]["text"])
                val_text = self._semantic_correction(text_regions[val_i]["text"])

                # Crop of the value region for hash + signature check
                vb      = text_regions[val_i]["bbox"]
                crop_v  = img[
                    max(0, vb[1]-5):min(img.shape[0], vb[3]+5),
                    max(0, vb[0]-5):min(img.shape[1], vb[2]+5),
                ]
                v_hash  = self._get_image_hash(crop_v)
                conf    = (text_regions[key_i]["conf"] + text_regions[val_i]["conf"]) / 2

                # Check memory first
                if v_hash in self._memory_cache:
                    val_text = self._memory_cache[v_hash]
                    status   = "LEARNED_MATCH"
                    conf     = 1.0
                elif self._detect_signature(crop_v):
                    val_text = "[SIGNATURE_DETECTED]"
                    status   = "SIGNATURE"
                    conf     = 0.95
                else:
                    if text_regions[val_i]["conf"] < 0.7:
                        skel    = self._skeletonize(crop_v)
                        refined = self._extract_text_with_troc(skel, high_precision=True)
                        if refined:
                            val_text = self._semantic_correction(refined)

                    # Last resort: Claude vision fallback
                    if conf < 0.45 and crop_v.size > 0:
                        claude_text = self._claude_verify_crop(crop_v, key_text)
                        if claude_text and claude_text not in ("[BLANK]",):
                            val_text = claude_text
                            conf     = 0.95

                    status = "LIST_PAIR"

                if self._is_noisy_label(key_text) and status == "SIGNATURE":
                    key_text = "Signature / Verification Field"

                questions.append({
                    "question":   key_text,
                    "selected":   val_text,
                    "options":    [],
                    "confidence": round(conf, 4),
                    "status":     status,
                    "imageHash":  v_hash,
                })

            else:
                # Standalone note
                idx    = row_idx_list[0]
                t      = text_regions[idx]
                tb     = t["bbox"]
                crop   = img[tb[1]:tb[3], tb[0]:tb[2]]
                v_hash = self._get_image_hash(crop)
                text   = self._semantic_correction(t["text"])
                conf   = t["conf"]

                if v_hash in self._memory_cache:
                    text   = self._memory_cache[v_hash]
                    status = "LEARNED_MATCH"
                    conf   = 1.0
                else:
                    # Apply TrOCR for low-confidence handwritten notes
                    if conf < 0.55:
                        refined = self._extract_text_with_troc(crop, high_precision=False)
                        if refined:
                            text = self._semantic_correction(refined)

                    # Claude fallback
                    if conf < 0.45 and crop.size > 0:
                        claude_text = self._claude_verify_crop(crop, "standalone field")
                        if claude_text and claude_text not in ("[BLANK]",):
                            text = claude_text
                            conf = 0.95

                    status = "HANDWRITTEN_NOTE"

                questions.append({
                    "question":   text,
                    "selected":   text,
                    "options":    [],
                    "confidence": round(conf, 4),
                    "status":     status,
                    "imageHash":  v_hash,
                })

        return {
            "questions": questions,
            "diagnostics": {
                "logic":      "UNIVERSAL_V11",
                "text_count": len(text_regions),
                "box_count":  len(boxes),
                "row_count":  len(rows),
            },
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # Utility helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _detect_vertical_gutters(self, text_regions: List[Dict], img_width: int) -> List[float]:
        if not text_regions:
            return []
        xs = sorted(t["center"][0] for t in text_regions)
        cols: List[List[float]] = [[xs[0]]]
        for x in xs[1:]:
            if x - cols[-1][-1] < 250:
                cols[-1].append(x)
            else:
                cols.append([x])
        return [sum(c) / len(c) for c in cols]

    @staticmethod
    def _get_image_hash(img_crop: np.ndarray) -> str:
        try:
            if img_crop is None or img_crop.size == 0:
                return "0"
            gray    = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) \
                      if len(img_crop.shape) == 3 else img_crop
            resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
            diff    = resized[:, 1:] > resized[:, :-1]
            return hex(int("".join(diff.flatten().astype(int).astype(str)), 2))[2:]
        except Exception:
            return "0"

    @staticmethod
    def _is_noisy_label(text: str) -> bool:
        if not text or len(text) < 3:
            return True
        special = sum(1 for c in text if not c.isalnum() and c != " ")
        if special / len(text) > 0.4:
            return True
        noisy = ["prg", "round", "#", "__", "none", "null"]
        return any(p in text.lower() for p in noisy)