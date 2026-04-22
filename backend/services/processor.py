"""
Hydra v13.0 — Cognitive Orchestrator
======================================
Production-grade VLM-driven document processing engine.

CRITICAL CHANGE from v12.5:
  VLM is now the CONTROLLER. OCR fills text INTO VLM-defined structure.

Pipeline:
  1. INPUT      → Normalise image
  2. CLASSIFY   → Detect document type (with fallback safety)
  3. RESTORE    → Dual-output (raw for Paddle, enhanced for others)
  4. OCR        → Three engines on their optimal input
  5. ENSEMBLE   → Levenshtein scaffold+patch voting
  6. VLM        → Extract document SKELETON (structure authority)
  7. MAP        → Map OCR text INTO VLM skeleton (VLMStructureMapper)
  8. VALIDATE   → Domain-aware + cross-field validation
  9. REFINE     → Constrained LLM (only if needed)
  10. MEMORY    → Store for learning
"""

import os
import cv2
import time
import logging
import hashlib
import numpy as np
import sqlite3
import threading
from typing import Dict, List, Any, Optional, Union, Tuple
from PIL import Image as PILImage

# Hydra v13.0 Cognitive Stack
from .doc_classifier import get_classifier
from .restoration import get_restorer
from .vlm_engine import get_vlm
from .vlm_structure_mapper import get_structure_mapper
from .ensemble import get_voter
from .graph_recon import get_layout_graph
from .validator import get_validator
from .vector_memory import get_vector_memory
from .survey_extractor import SurveyExtractor
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

# TrOCR for handwriting
try:
    from .handwriting_engine import get_handwriting_engine
    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class SurveyProcessor:
    def __init__(self, custom_vocab: Optional[List[str]] = None):
        import torch
        self.device = self._pick_device(torch)
        logger.info(f"[HYDRA-v13.0] Initialising on: {self.device}")

        # ── v13.0 Cognitive Stack ────────────────────────────────────────
        self.classifier       = get_classifier()
        self.restorer         = get_restorer()
        self.vlm              = get_vlm()
        self.structure_mapper = get_structure_mapper()
        self.voter            = get_voter()
        self.layout_graph     = get_layout_graph()
        self.validator        = get_validator()
        self.vector_memory    = get_vector_memory()
        self.llm_refiner      = get_llm_refiner()

        # ── OCR Engine Pool ──────────────────────────────────────────────
        self.paddle_ocr    = self._load_paddle()
        self.easy_reader   = self._load_easyocr()

        # ── Handwriting Engine ───────────────────────────────────────────
        self.handwriting_engine = None
        if TROCR_AVAILABLE:
            try:
                self.handwriting_engine = get_handwriting_engine()
                logger.info("[HYDRA-v13.0] TrOCR handwriting engine loaded")
            except Exception as exc:
                logger.warning(f"[HYDRA-v13.0] TrOCR load failed: {exc}")

        # ── Survey Extractor (shares OCR engines) ────────────────────────
        ocr_engines = {}
        if self.easy_reader:
            ocr_engines["easyocr"] = self.easy_reader
        self.survey_extractor = SurveyExtractor(
            ocr_engines=ocr_engines,
            handwriting_engine=self.handwriting_engine
        )
        logger.info("[HYDRA-v13.0] SurveyExtractor initialised")

        # ── Local Memory (SQLite fallback) ───────────────────────────────
        self.memory_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "feedback_loop", "memory.db"
        )
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
    # Core Cognitive Pipeline (VLM-DRIVEN — v13.0)
    # ═══════════════════════════════════════════════════════════════════════

    def process(self, input_source: Union[str, PILImage.Image]) -> Dict[str, Any]:
        """
        Hydra v13.0 Production Pipeline:
        Classify → Restore → OCR → Ensemble → VLM Skeleton → Map → Validate → Refine
        
        KEY CHANGE: VLM defines structure, OCR fills values.
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

        # ── 4. Document Classification (with fallback safety) ────────────
        quick_texts = [r["text"] for r in e_res] + [r["text"] for r in t_res[:20]]
        doc_class = self.classifier.classify(img_bgr, quick_texts)
        doc_type = doc_class["type"]
        doc_confidence = doc_class.get("confidence", 0.0)

        # Classifier safety: if confidence too low, fallback to general
        if doc_confidence < 0.3 and doc_type != "general":
            logger.warning(
                f"[CLASSIFIER] Low confidence ({doc_confidence:.2f}) for {doc_type} — "
                f"falling back to general pipeline"
            )
            doc_class["original_type"] = doc_type
            doc_class["fallback"] = True
            doc_type = "general"
            doc_class["type"] = "general"

        # ── 4b. Survey Form Fast-Path ────────────────────────────────────
        if doc_type == "survey_form":
            logger.info("[HYDRA] Survey form detected — routing to SurveyExtractor")
            survey_result = self.survey_extractor.extract(img_bgr)

            # Cross-validate with VLM skeleton
            vlm_img = PILImage.fromarray(cv2.cvtColor(img_for_others, cv2.COLOR_BGR2RGB))
            vlm_skeleton = self.vlm.extract_skeleton(vlm_img, doc_type)

            elapsed = round(time.time() - t_start, 2)
            return self._format_survey_result(
                survey_result, doc_class, vision_diag, elapsed,
                {"paddle": len(p_res), "easyocr": len(e_res), "tesseract": len(t_res)},
                vlm_skeleton=vlm_skeleton,
            )

        # ── 5. Ensemble Voting (Levenshtein Scaffold+Patch + TrOCR) ──────
        voted_regions = self.voter.consolidate(
            p_res, e_res, t_res, 
            handwriting_engine=self.handwriting_engine,
            image_bgr=img_bgr
        )
        logger.info(f"[ENSEMBLE] Consolidated to {len(voted_regions)} regions (TrOCR integrated).")

        # ── 6. VLM Structural Extraction (AUTHORITY) ─────────────────────
        vlm_img = PILImage.fromarray(cv2.cvtColor(img_for_others, cv2.COLOR_BGR2RGB))
        vlm_skeleton = self.vlm.extract_skeleton(vlm_img, doc_type)

        logger.info(
            f"[VLM] Skeleton: {vlm_skeleton.get('status', 'unknown')} | "
            f"Fields: {len(vlm_skeleton.get('fields', []))} | "
            f"Table: {'yes' if vlm_skeleton.get('table') else 'no'}"
        )

        vlm_field_count = len(vlm_skeleton.get('fields', []))
        if vlm_field_count < max(3, len(voted_regions) * 0.3):
            logger.info(
                f"[PIPELINE] VLM weak ({vlm_field_count} fields vs {len(voted_regions)} OCR regions) "
                f"— mapper will use OCR-primary mode with smart grouping"
            )

        # ── 7. Map OCR INTO VLM Structure ────────────────────────────────
        # THIS is the critical reversal: VLM defines WHAT, OCR provides HOW
        structured_entries = self.structure_mapper.map_ocr_to_structure(
            vlm_skeleton, voted_regions, doc_type
        )

        logger.info(
            f"[MAPPER] Produced {len(structured_entries)} entries | "
            f"Sources: {self._count_sources(structured_entries)}"
        )

        # ── 8. Validate + Refine ─────────────────────────────────────────
        final_data = []
        for entry in structured_entries:
            raw_text = entry.get("selected", "")
            avg_conf = entry.get("confidence", 0.5)
            field_name = entry.get("question", "Field")

            # Domain-aware cleanup
            cleaned = self.validator.clean_text(raw_text, doc_type)

            # Vector memory lookup (learning from past corrections)
            memory_correction = self.vector_memory.search(cleaned)
            if memory_correction:
                cleaned = memory_correction

            # Validate
            val_report = self.validator.validate_field(field_name, cleaned, avg_conf)

            # Constrained LLM refinement (only if needed AND low confidence)
            if val_report["correction_required"] and avg_conf < 0.6:
                vlm_context = vlm_skeleton.get("structure_raw", "")
                cleaned = self.llm_refiner.refine(cleaned, vlm_context, doc_type)

            final_data.append({
                "question": field_name,
                "selected": cleaned,
                "confidence": round(float(avg_conf), 4),
                "status": val_report["status"],
                "source": entry.get("source", "unknown"),
                "agreement": entry.get("agreement", False),
                "imageHash": hashlib.md5(f"{doc_type}_{field_name}".encode()).hexdigest(),
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
                "vlm_skeleton": {
                    "status": vlm_skeleton.get("status"),
                    "fields_count": len(vlm_skeleton.get("fields", [])),
                    "has_table": vlm_skeleton.get("table") is not None,
                    "sections": vlm_skeleton.get("sections", []),
                },
                "mapped_entries": len(structured_entries),
                "source_breakdown": self._count_sources(structured_entries),
                "duration": elapsed,
                "logic_version": "Hydra-v13.0-VLM-DRIVEN",
            },
        }

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
    # Survey Processing (with VLM cross-validation)
    # ═══════════════════════════════════════════════════════════════════════

    def process_survey(self, input_source: Union[str, PILImage.Image]) -> Dict[str, Any]:
        """
        Dedicated survey processing endpoint — uses SurveyExtractor
        with VLM cross-validation for structure confidence.
        """
        t_start = time.time()

        if isinstance(input_source, str):
            pil_image = PILImage.open(input_source).convert("RGB")
        else:
            pil_image = input_source.convert("RGB")

        img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Run quick OCR for classification
        _, img_for_others, vision_diag = self.restorer.process(img_bgr)
        e_res = self._run_easy_ocr(img_for_others)
        t_res = self._run_tesseract_ocr(img_for_others)
        quick_texts = [r["text"] for r in e_res] + [r["text"] for r in t_res[:20]]
        doc_class = self.classifier.classify(img_bgr, quick_texts)

        # Extract survey data
        survey_result = self.survey_extractor.extract(img_bgr)

        # VLM cross-validation
        vlm_img = PILImage.fromarray(cv2.cvtColor(img_for_others, cv2.COLOR_BGR2RGB))
        vlm_skeleton = self.vlm.extract_skeleton(vlm_img, "survey_form")

        elapsed = round(time.time() - t_start, 2)

        return self._format_survey_result(
            survey_result, doc_class, vision_diag, elapsed,
            {"easyocr": len(e_res), "tesseract": len(t_res)},
            vlm_skeleton=vlm_skeleton,
        )

    def _format_survey_result(
        self, survey_result, doc_class, vision_diag, elapsed, ocr_counts,
        vlm_skeleton: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Format SurveyResult into the standard API response."""
        survey_dict = survey_result.to_dict()

        # Build questions format
        questions = []
        for q in survey_result.questions:
            entry = {
                "question": f"{q.number}. {q.text}" if q.number else q.text,
                "selected": q.selected_column,
                "confidence": q.confidence,
                "status": "✅ OK" if q.confidence > 0.7 else "⚠️ Low Confidence",
                "imageHash": hashlib.md5(f"survey_{q.text}".encode()).hexdigest(),
            }

            # If VLM skeleton exists, cross-validate
            if vlm_skeleton and vlm_skeleton.get("status") == "ok":
                vlm_fields = vlm_skeleton.get("fields", [])
                vlm_match = self._vlm_cross_validate_question(
                    q, vlm_fields
                )
                if vlm_match:
                    entry["vlm_agreement"] = vlm_match.get("agreement", False)
                    if vlm_match.get("agreement"):
                        # VLM agrees → boost confidence
                        entry["confidence"] = min(entry["confidence"] + 0.1, 1.0)
                    else:
                        # VLM disagrees → flag for review
                        entry["status"] = "⚠️ VLM Disagrees"
                        entry["vlm_answer"] = vlm_match.get("vlm_answer")

            questions.append(entry)

        result = {
            "questions": questions,
            "survey_data": survey_dict,
            "diagnostics": {
                "vision": vision_diag,
                "doc_type": doc_class,
                "ocr_counts": ocr_counts,
                "form_type": survey_result.form_type,
                "columns_detected": survey_result.columns,
                "questions_extracted": len(survey_result.questions),
                "vlm_skeleton": {
                    "status": vlm_skeleton.get("status") if vlm_skeleton else "skipped",
                    "fields_count": len(vlm_skeleton.get("fields", [])) if vlm_skeleton else 0,
                } if vlm_skeleton else None,
                "duration": elapsed,
                "logic_version": "Hydra-v13.0-SURVEY",
            },
        }
        return result

    def _vlm_cross_validate_question(self, question, vlm_fields):
        """Cross-validate a survey question against VLM skeleton fields."""
        from rapidfuzz import fuzz

        q_text = question.text or ""
        q_selected = question.selected_column or ""

        for field in vlm_fields:
            field_text = field.get("text", "")
            score = fuzz.partial_ratio(q_text.lower(), field_text.lower())
            if score > 60:
                vlm_answer = field.get("vlm_answer", "")
                agreement = (
                    vlm_answer and q_selected and
                    fuzz.ratio(vlm_answer.lower(), q_selected.lower()) > 60
                )
                return {
                    "agreement": agreement,
                    "vlm_answer": vlm_answer,
                    "match_score": score,
                }
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _count_sources(entries: List[Dict]) -> Dict[str, int]:
        """Count entries by source type."""
        counts = {}
        for entry in entries:
            src = entry.get("source", "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts

    # ═══════════════════════════════════════════════════════════════════════
    # Feedback / Learning
    # ═══════════════════════════════════════════════════════════════════════

    def register_feedback(self, image_hash: str, text: str) -> bool:
        try:
            self.vector_memory.add_feedback(image_hash, text)
            return True
        except Exception:
            return False
