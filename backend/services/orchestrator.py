"""
ExtractionOrchestrator
======================
Thin async orchestration layer.

Key design:
  - Does NOT own or create models.  Receives the singleton SurveyProcessor
    via dependency injection from main.py (FastAPI lifespan).
  - All CPU-bound OCR work is dispatched to a ThreadPoolExecutor via
    asyncio.run_in_executor() so the uvicorn event loop is never blocked.
  - register_correction() delegates to the processor's SQLite memory.
"""

import asyncio
import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from PIL import Image as PILImage

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    def __init__(self, processor, executor: ThreadPoolExecutor):
        """
        Parameters
        ----------
        processor : SurveyProcessor
            The singleton processor — already fully initialised.
        executor  : ThreadPoolExecutor
            Shared thread pool owned by the application lifespan.
        """
        self.processor = processor
        self.executor  = executor

    # ─────────────────────────────────────────────────────────────────────────
    # Public async API
    # ─────────────────────────────────────────────────────────────────────────

    async def digitize(self, image_b64: str) -> Dict[str, Any]:
        """
        Decode the base64 image and run OCR in the thread pool.
        Returns the standard result dict (questions + diagnostics).
        """
        loop = asyncio.get_event_loop()
        try:
            pil_img = await loop.run_in_executor(
                self.executor,
                self._decode_image,
                image_b64,
            )
        except Exception as exc:
            logger.error(f"[ORCH] Image decode failed: {exc}")
            return self._error_result("Image decode failed")

        try:
            result = await loop.run_in_executor(
                self.executor,
                self.processor.process,
                pil_img,
            )
        except Exception as exc:
            logger.error(f"[ORCH] OCR processing failed: {exc}")
            return self._error_result(f"OCR failed: {exc}")

        # Enrich diagnostics
        questions = result.get("questions", [])
        avg_conf  = (
            sum(q.get("confidence", 0) for q in questions) / len(questions)
            if questions else 0.0
        )
        null_rate = (
            sum(1 for q in questions if q.get("selected") is None) / len(questions)
            if questions else 1.0
        )

        diag = result.setdefault("diagnostics", {})
        diag.update({
            "engine":           "LOCAL_HYDRA_V11",
            "avg_confidence":   round(avg_conf, 4),
            "null_rate":        round(null_rate, 4),
            "question_count":   len(questions),
            "handwriting_mode": diag.get("handwriting_ratio", 0) >= 0.4,
        })

        logger.info(
            f"[ORCH] Success — {len(questions)} fields, "
            f"avg_conf={avg_conf:.2f}, null_rate={null_rate:.2f}"
        )
        return result

    async def digitize_survey(self, image_b64: str) -> Dict[str, Any]:
        """
        Decode base64 image and run survey-specific extraction in the thread pool.
        Forces the SurveyExtractor path regardless of classification.
        """
        loop = asyncio.get_event_loop()
        try:
            pil_img = await loop.run_in_executor(
                self.executor,
                self._decode_image,
                image_b64,
            )
        except Exception as exc:
            logger.error(f"[ORCH] Image decode failed: {exc}")
            return self._error_result("Image decode failed")

        try:
            result = await loop.run_in_executor(
                self.executor,
                self.processor.process_survey,
                pil_img,
            )
        except Exception as exc:
            logger.error(f"[ORCH] Survey extraction failed: {exc}")
            return self._error_result(f"Survey extraction failed: {exc}")

        # Enrich diagnostics
        questions = result.get("questions", [])
        avg_conf = (
            sum(q.get("confidence", 0) for q in questions) / len(questions)
            if questions else 0.0
        )
        null_rate = (
            sum(1 for q in questions if q.get("selected") is None) / len(questions)
            if questions else 1.0
        )

        diag = result.setdefault("diagnostics", {})
        diag.update({
            "engine": "LOCAL_HYDRA_SURVEY",
            "avg_confidence": round(avg_conf, 4),
            "null_rate": round(null_rate, 4),
            "question_count": len(questions),
        })

        logger.info(
            f"[ORCH] Survey done — {len(questions)} questions, "
            f"avg_conf={avg_conf:.2f}"
        )
        return result

    def register_correction(self, image_hash: str, corrected_text: str) -> bool:
        """Persist a user correction into the active-learning memory."""
        try:
            return self.processor.register_feedback(image_hash, corrected_text)
        except Exception as exc:
            logger.error(f"[ORCH] register_correction failed: {exc}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _decode_image(image_b64: str) -> PILImage.Image:
        """Sanitise data-URI prefix and decode base64 → PIL Image (RGB)."""
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        raw = base64.b64decode(image_b64)
        return PILImage.open(io.BytesIO(raw)).convert("RGB")

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        return {
            "questions":   [],
            "diagnostics": {
                "error":          message,
                "engine":         "NONE",
                "logic_version":  "Hydra-v11.0-PRODUCTION",
            },
        }