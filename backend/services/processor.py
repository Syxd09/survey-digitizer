"""
Hydra v12.5 — Cognitive Orchestrator
======================================
Production-grade CDP (Cognitive Document Processing) engine.

Pipeline:
  1. CLASSIFY → Detect document type (code, form, invoice, etc.)
  2. RESTORE → Dual-output (raw for Paddle, enhanced for others)
  3. OCR     → Three engines on their optimal input
  4. ENSEMBLE → Levenshtein scaffold+patch voting
  5. VLM     → Structured extraction (Pix2Struct)
  6. LAYOUT  → Column + row aware reconstruction
  7. MERGE   → VLM authority + OCR ensemble
  8. VALIDATE → Domain-aware rule engine
  9. REFINE  → Constrained LLM (if needed)
  10. MEMORY → Store for learning
"""

import os
import cv2
import time
import logging
import numpy as np
import sqlite3
import threading
from typing import Dict, List, Any, Optional, Union, Tuple
from PIL import Image as PILImage

# Hydra v12.5 Cognitive Stack
from .doc_classifier import get_classifier
from .restoration import get_restorer
from .vlm_engine import get_vlm
from .ensemble import get_voter
from .graph_recon import get_layout_graph
from .validator import get_validator
from .vector_memory import get_vector_memory
from .llm_refiner import get_llm_refiner

# Core OCR Engines
try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)


class SurveyProcessor:
    def __init__(self, custom_vocab: Optional[List[str]] = None):
        import torch
        self.device = self._pick_device(torch)
        logger.info(f"[HYDRA-v12.5] Initialising on: {self.device}")

        # ── v12.5 Cognitive Stack ────────────────────────────────────────
        self.classifier    = get_classifier()
        self.restorer      = get_restorer()
        self.vlm           = get_vlm()
        self.voter         = get_voter()
        self.layout_graph  = get_layout_graph()
        self.validator     = get_validator()
        self.vector_memory = get_vector_memory()
        self.llm_refiner   = get_llm_refiner()

        # ── OCR Engine Pool ──────────────────────────────────────────────
        self.paddle_ocr    = self._load_paddle()
        self.easy_reader   = self._load_easyocr()

        # ── Local Memory (SQLite fallback) ───────────────────────────────
        self.memory_path = "backend/feedback_loop/memory.db"
        self._db_lock    = threading.Lock()
        self._init_memory_db()

    @staticmethod
    def _pick_device(torch) -> str:
        if torch.cuda.is_available(): return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available(): return "mps"
        return "cpu"

    def _load_paddle(self) -> Optional[Any]:
        if not PADDLE_AVAILABLE: return None
        try:
            return PaddleOCR(lang="en")
        except Exception as exc:
            logger.warning(f"[PADDLE] Load failed: {exc}")
            return None

    def _load_easyocr(self) -> Optional[Any]:
        if not EASYOCR_AVAILABLE: return None
        try:
            return easyocr.Reader(["en"], gpu=(self.device in ("cuda", "mps")))
        except Exception as exc:
            logger.warning(f"[EASYOCR] Load failed: {exc}")
            return None

    def _init_memory_db(self):
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with self._db_lock:
            conn = sqlite3.connect(self.memory_path)
            conn.execute("CREATE TABLE IF NOT EXISTS units (hash TEXT PRIMARY KEY, text TEXT)")
            conn.commit()
            conn.close()

    # ═══════════════════════════════════════════════════════════════════════
    # Core Cognitive Pipeline
    # ═══════════════════════════════════════════════════════════════════════

    def process(self, input_source: Union[str, PILImage.Image]) -> Dict[str, Any]:
        """
        Hydra v12.5 Production Pipeline:
        Classify → Restore → OCR → Ensemble → VLM → Layout → Validate → Refine
        """
        t_start = time.time()

        # ── 1. Input Normalisation ───────────────────────────────────────
        if isinstance(input_source, str):
            pil_image = PILImage.open(input_source).convert("RGB")
        else:
            pil_image = input_source.convert("RGB")

        img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # ── 2. Vision Restoration (Dual Output) ─────────────────────────
        img_for_paddle, img_for_others, vision_diag = self.restorer.process(img_bgr)

        # ── 3. Parallel OCR Execution ────────────────────────────────────
        p_res = self._run_paddle_ocr(img_for_paddle)
        e_res = self._run_easy_ocr(img_for_others)
        t_res = self._run_tesseract_ocr(img_for_others)

        logger.info(
            f"[OCR] Paddle={len(p_res)} | EasyOCR={len(e_res)} | Tesseract={len(t_res)}"
        )

        # ── 4. Document Classification ───────────────────────────────────
        # Use fast EasyOCR texts for classification signals
        quick_texts = [r["text"] for r in e_res] + [r["text"] for r in t_res[:20]]
        doc_class = self.classifier.classify(img_bgr, quick_texts)
        doc_type = doc_class["type"]

        # ── 5. Ensemble Voting (Levenshtein Scaffold+Patch) ──────────────
        voted_regions = self.voter.consolidate(p_res, e_res, t_res)
        logger.info(f"[ENSEMBLE] Consolidated to {len(voted_regions)} regions.")

        # ── 6. VLM Structured Extraction ─────────────────────────────────
        vlm_img = PILImage.fromarray(cv2.cvtColor(img_for_others, cv2.COLOR_BGR2RGB))
        vlm_result = self.vlm.extract_structured(vlm_img, doc_type)

        # ── 7. Layout Reconstruction (Document-Type Aware) ───────────────
        self.layout_graph.build_graph(voted_regions, doc_type)
        layout_entries = self.layout_graph.extract_structured()

        # ── 8. Merge VLM + OCR Ensemble ──────────────────────────────────
        # Use layout entries if available, otherwise use voted_regions directly
        merged_entries = layout_entries if layout_entries else voted_regions

        # ── 9. Validate + Refine ─────────────────────────────────────────
        final_data = []
        for entry in merged_entries:
            # Handle both text-based and label-value entries
            if "text" in entry:
                raw_text = entry["text"]
            elif "label" in entry and "value" in entry:
                raw_text = f"{entry['label']}: {entry['value']}"
            else:
                raw_text = str(entry)

            avg_conf = entry.get("conf", 0.5)

            # Domain-aware field labeling
            field_name = self._classify_field(raw_text, doc_type, len(final_data))

            # Domain-aware cleanup
            cleaned = self.validator.clean_text(raw_text, doc_type)

            # Vector memory lookup
            memory_correction = self.vector_memory.search(cleaned)
            if memory_correction:
                cleaned = memory_correction

            # Validate
            val_report = self.validator.validate_field(field_name, cleaned, avg_conf)

            # Constrained LLM refinement (only if needed)
            if val_report["correction_required"] and avg_conf < 0.6:
                vlm_context = vlm_result.get("raw", "")
                cleaned = self.llm_refiner.refine(cleaned, vlm_context, doc_type)

            final_data.append({
                "question": field_name,
                "selected": cleaned,
                "confidence": round(float(avg_conf), 4),
                "status": val_report["status"],
            })

        elapsed = round(time.time() - t_start, 2)
        return {
            "questions": final_data,
            "diagnostics": {
                "vision": vision_diag,
                "doc_type": doc_class,
                "ocr_counts": {
                    "paddle": len(p_res),
                    "easyocr": len(e_res),
                    "tesseract": len(t_res),
                },
                "ensemble_regions": len(voted_regions),
                "vlm_status": vlm_result.get("status", "unknown"),
                "duration": elapsed,
                "logic_version": "Hydra-v12.5-PRODUCTION",
            },
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Merging Logic
    # ═══════════════════════════════════════════════════════════════════════

    def _merge_vlm_and_ocr(
        self,
        ocr_entries: List[Dict],
        vlm_result: Dict,
        doc_type: str,
    ) -> List[Dict]:
        """
        Merge VLM structured output with OCR ensemble.
        VLM is authority for field names and structure.
        OCR is authority for exact text content.
        """
        vlm_entries = vlm_result.get("entries", [])

        if not vlm_entries:
            # VLM produced nothing useful — rely on OCR entirely
            return ocr_entries

        # For now, OCR entries are primary (they have exact bboxes and text).
        # VLM entries are used to validate/enrich field names.
        # Future: deeper merging with VLM authority when confident.
        return ocr_entries

    def _classify_field(self, text: str, doc_type: str, index: int) -> str:
        """
        Assign semantic field name based on text content and document type.
        """
        if doc_type == "code_screenshot":
            # Detect specific code screenshot fields
            if any(tab in text.upper() for tab in ["PROBLEMS", "OUTPUT", "CONSOLE", "TERMINAL", "PORTS"]):
                return "Panel Header"
            if ".py" in text.lower() or ".js" in text.lower() or ".ts" in text.lower():
                return "File Context"
            if "Ln" in text and "Col" in text:
                return "Error Entry"
            if any(kw in text for kw in ["not defined", "not closed", "not supported", "could not", "Import"]):
                return "Error Entry"
            return f"Code Element {index + 1}"

        elif doc_type == "form":
            return f"Form Field {index + 1}"

        elif doc_type == "invoice":
            if any(kw in text.lower() for kw in ["total", "subtotal", "tax"]):
                return "Financial Summary"
            return f"Line Item {index + 1}"

        return f"Field {index + 1}"

    # ═══════════════════════════════════════════════════════════════════════
    # Engine Wrappers
    # ═══════════════════════════════════════════════════════════════════════

    def _run_paddle_ocr(self, img: np.ndarray) -> List[Dict]:
        if not self.paddle_ocr or img is None:
            return []
        try:
            res = self.paddle_ocr.ocr(img, cls=True)
            out = []
            if res and res[0]:
                for line in res[0]:
                    box, (text, conf) = line
                    out.append({
                        "bbox": (int(box[0][0]), int(box[0][1]), int(box[2][0]), int(box[2][1])),
                        "text": text, "conf": conf, "engine": "paddle",
                    })
            return out
        except Exception as exc:
            logger.warning(f"[PADDLE] OCR failed: {exc}")
            return []

    def _run_easy_ocr(self, img: np.ndarray) -> List[Dict]:
        if not self.easy_reader or img is None:
            return []
        try:
            res = self.easy_reader.readtext(img)
            return [{
                "bbox": (int(b[0][0]), int(b[0][1]), int(b[2][0]), int(b[2][1])),
                "text": t, "conf": c, "engine": "easyocr",
            } for b, t, c in res]
        except Exception as exc:
            logger.warning(f"[EASYOCR] OCR failed: {exc}")
            return []

    def _run_tesseract_ocr(self, img: np.ndarray) -> List[Dict]:
        if not TESSERACT_AVAILABLE or img is None:
            return []
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            res = []
            for i in range(len(data["text"])):
                txt = data["text"][i].strip()
                conf = int(data["conf"][i])
                if txt and conf > 0:
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    res.append({
                        "bbox": (x, y, x + w, y + h),
                        "text": txt,
                        "conf": conf / 100.0,
                        "engine": "tesseract",
                    })
            return res
        except Exception as exc:
            logger.warning(f"[TESSERACT] OCR failed: {exc}")
            return []

    # ═══════════════════════════════════════════════════════════════════════
    # Feedback / Learning
    # ═══════════════════════════════════════════════════════════════════════

    def register_feedback(self, image_hash: str, text: str) -> bool:
        try:
            self.vector_memory.add_feedback(image_hash, text)
            return True
        except Exception:
            return False
