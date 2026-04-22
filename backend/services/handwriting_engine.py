"""
Hydra v13.0 — Handwriting Engine (TrOCR)
==========================================
Dedicated engine for handwritten text extraction.
Uses Microsoft's TrOCR model trained on handwriting.

Triggered when:
  1. Classifier detects doc_type == "handwritten"
  2. A region within a document is identified as handwritten

Gracefully falls back to None if transformers/TrOCR unavailable.
"""

import logging
from typing import Optional, List, Dict
from PIL import Image

logger = logging.getLogger(__name__)


class HandwritingEngine:
    """
    Extracts text from handwritten regions using TrOCR.
    
    TrOCR (Transformer-based OCR) is specifically trained on handwriting,
    unlike EasyOCR/Tesseract which work best on printed text.
    """

    def __init__(self):
        self.model = None
        self.processor = None
        self.device = "cpu"
        self._available = False
        self._load_model()

    def _load_model(self):
        """Load TrOCR handwriting model."""
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            model_name = "microsoft/trocr-large-handwritten"
            logger.info(f"[HANDWRITING] Loading {model_name} (this requires ~3.3GB RAM)...")

            self.processor = TrOCRProcessor.from_pretrained(model_name)
            self.model = VisionEncoderDecoderModel.from_pretrained(model_name)

            # TrOCR is small enough for CPU; MPS has issues with some ops
            self.model.to("cpu")
            self.model.eval()
            self._available = True
            logger.info("[HANDWRITING] TrOCR Large loaded successfully.")

        except ImportError:
            logger.warning(
                "[HANDWRITING] transformers not available — handwriting engine disabled"
            )
        except Exception as exc:
            logger.warning(f"[HANDWRITING] TrOCR load failed: {exc}")

    @property
    def available(self) -> bool:
        return self._available

    def extract_text(self, image_crop: Image.Image) -> str:
        """
        Extract text from a single handwritten text region.
        
        Args:
            image_crop: PIL Image of a cropped handwriting region
        
        Returns:
            Extracted text string
        """
        if not self._available:
            return ""

        try:
            import torch

            # Ensure RGB
            if image_crop.mode != "RGB":
                image_crop = image_crop.convert("RGB")

            pixel_values = self.processor(
                images=image_crop, return_tensors="pt"
            ).pixel_values.to("cpu")

            with torch.no_grad():
                generated_ids = self.model.generate(
                    pixel_values, 
                    max_new_tokens=128,
                    num_beams=4,
                    early_stopping=True,
                    no_repeat_ngram_size=3
                )

            text = self.processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]

            return text.strip()

        except Exception as exc:
            logger.warning(f"[HANDWRITING] Extraction failed: {exc}")
            return ""

    def extract_from_regions(
        self,
        full_image: Image.Image,
        regions: List[Dict],
    ) -> List[Dict]:
        """
        Extract handwritten text from multiple regions.
        
        Args:
            full_image: Full document image
            regions: List of dicts with "bbox" keys (x1, y1, x2, y2)
        
        Returns:
            List of dicts with extracted text and confidence
        """
        if not self._available:
            return []

        results = []
        for region in regions:
            bbox = region.get("bbox")
            if not bbox:
                continue

            x1, y1, x2, y2 = bbox
            crop = full_image.crop((x1, y1, x2, y2))

            # Skip very small crops
            if crop.width < 10 or crop.height < 10:
                continue

            text = self.extract_text(crop)
            if text:
                results.append({
                    "text": text,
                    "bbox": bbox,
                    "engine": "trocr",
                    "conf": 0.7,  # TrOCR doesn't output confidence; use baseline
                })

        return results


def get_handwriting_engine() -> HandwritingEngine:
    return HandwritingEngine()
