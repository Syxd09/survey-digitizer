import os
import json
import base64
import logging
import asyncio
import io
import cv2
import numpy as np
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from PIL import Image as PILImage
from services.processor import SurveyProcessor

load_dotenv()
logger = logging.getLogger(__name__)

class ExtractionOrchestrator:
    def __init__(self):
        # Initialize Local Fail-safe Engine (Primary Authority)
        # Now augmented with MPS acceleration and TrOCR recognition
        self.local_processor = SurveyProcessor()

    async def digitize(self, image_b64: str) -> Dict[str, Any]:
        """Orchestrate extraction using HIGH-ACCURACY LOCAL OCR only."""
        # 1. Run local OCR with handwriting enhancements
        try:
            logger.info("[HYDRA] Running Local High-Accuracy Engine (EasyOCR + TrOCR)")
            result = await self._digitize_local(image_b64)
            
            if result and result.get("questions") and len(result["questions"]) > 0:
                avg_conf = result.get("diagnostics", {}).get("avg_confidence", 0)
                null_rate = result.get("diagnostics", {}).get("null_rate", 1.0)
                
                result["diagnostics"]["engine"] = "LOCAL_HYDRA_V2"
                result["diagnostics"]["handwriting_mode"] = self._detect_handwriting(image_b64)
                
                logger.info(f"[HYDRA] Success: LOCAL_HYDRA_V2, conf={avg_conf:.2f}, questions={len(result['questions'])}")
                return result
            else:
                logger.warning("[HYDRA] Local engine returned no results or failed.")
        except Exception as e:
            logger.error(f"[HYDRA] Local process failed: {e}")

        return {
            "questions": [],
            "diagnostics": {"error": "Local OCR processing failed", "engine": "NONE", "v": "6.0-LOCAL-ONLY"}
        }

    def _get_bytes_from_b64(self, image_b64: str) -> bytes:
        """Sanitize and decode base64 string, handling data URI prefixes."""
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            return base64.b64decode(image_b64)
        except Exception as e:
            logger.error(f"[HYDRA] Base64 decode failed: {e}")
            raise

    def _detect_handwriting(self, image_b64: str) -> bool:
        """Handwriting detection is now integrated into the main processor's logic,
        but we keep this for diagnostic reporting."""
        return True # Assume handwriting mode is on for local surveys

    async def _digitize_local(self, image_b64: str) -> Optional[Dict[str, Any]]:
        """Run local Python OCR engine as the primary processor."""
        try:
            img_data = self._get_bytes_from_b64(image_b64)
            pil_img = PILImage.open(io.BytesIO(img_data))
            
            # Use the existing SurveyProcessor (which now has TrOCR and MPS)
            local_result = self.local_processor.process(pil_img)
            
            questions = local_result.get("questions", [])
            avg_conf = sum(q.get("confidence", 0) for q in questions) / max(1, len(questions)) if questions else 0
            
            # Merge diagnostics from local processor with orchestrator metrics
            diagnostics = local_result.get("diagnostics", {})
            diagnostics.update({
                "avg_confidence": avg_conf,
                "null_rate": sum(1 for q in questions if q.get("selected") is None) / max(1, len(questions)) if questions else 1,
                "logic_version": diagnostics.get("logic_version", "Hydra-v10.0-AUTHORITY")
            })
            
            return {
                "questions": questions,
                "diagnostics": diagnostics
            }
        except Exception as e:
            logger.error(f"[HYDRA] Local engine sub-call failed: {str(e)}")
            return None

    def register_correction(self, image_hash: str, corrected_text: str) -> bool:
        """Register a user correction into Hydra's memory."""
        try:
            return self.local_processor.register_feedback(image_hash, corrected_text)
        except Exception as e:
            logger.error(f"[HYDRA] Failed to register correction: {e}")
            return False
