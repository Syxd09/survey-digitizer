"""
Phase 7 — Confidence Engine (Multi-signal)
=========================================
Computes a final confidence score for each field based on multiple signals.
"""

import logging
from typing import Dict, Any
from config import settings

logger = logging.getLogger(__name__)

class ConfidenceEngine:
    """Implements Phase 7: Multi-factor confidence scoring."""

    def __init__(self):
        self.weights = settings.CONFIDENCE_WEIGHTS
        self.method_offsets = {
            "anchor": 0.1,
            "zone": -0.2,
            "line_search": 0.0,
            "radio_group": 0.1
        }

    def compute_field_confidence(
        self, 
        ocr_conf: float, 
        quality_status: str, 
        validation_status: str,
        extraction_method: str = "anchor",
        pattern_match: bool = True
    ) -> Dict[str, Any]:
        """
        Calculates weighted confidence score with method-based offsets.
        """
        # 1. OCR Signal
        s_ocr = ocr_conf
        
        # 2. Validation Signal
        s_val = 1.0 if validation_status == "OK" else 0.5
        if validation_status == "REJECT":
            s_val = 0.0
            
        # 3. Pattern Signal
        s_pat = 1.0 if pattern_match else 0.0
        
        # 4. Method Signal (Additive Factor)
        s_method = self.method_offsets.get(extraction_method, 0.0)

        # Weighted Sum
        score = (
            (s_ocr * self.weights["ocr"]) +
            (s_val * self.weights["validation"]) +
            (s_pat * self.weights["pattern"]) +
            (s_method * self.weights.get("method", 0.0))
        )
        
        # Method Signal is already in the sum now
        final_score = score
        
        # Quality Penalty (Phase 1 impact)
        if quality_status == "FAIL":
            final_score *= 0.8 # 20% penalty for poor quality

        final_score = max(0.0, min(1.0, final_score))

        return {
            "score": round(float(final_score), 4),
            "signals": {
                "ocr": s_ocr,
                "validation": s_val,
                "pattern": s_pat,
                "method_offset": s_method
            }
        }

def get_confidence_engine() -> ConfidenceEngine:
    return ConfidenceEngine()
