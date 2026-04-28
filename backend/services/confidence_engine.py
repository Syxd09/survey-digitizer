"""
Phase 7 — Confidence Engine (Multi-signal)
=========================================
Computes a final confidence score for each field based on multiple signals.
"""

import logging
from typing import Dict, Any, Optional
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
            "radio_group": 0.1,
            "dynamic_grid": 0.15  # Highest boost — backed by morphological detection
        }

    def compute_field_confidence(
        self, 
        ocr_conf: float, 
        quality_status: str, 
        validation_status: str,
        extraction_method: str = "anchor",
        pattern_match: bool = True,
        visual_diff: Optional[float] = None
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

        # 5. Visual Signal (Optional)
        # If visual_diff is provided, it's used as a strong signal for selection accuracy.
        # We normalize visual_diff (0.0 to 1.0) relative to threshold.
        s_visual = 0.0
        if visual_diff is not None:
            # If diff > 2*threshold, it's very clear.
            s_visual = min(1.0, visual_diff / (settings.VISUAL_CONFIDENCE_THRESHOLD * 2))

        # Weighted Sum
        score = (
            (s_ocr * self.weights["ocr"]) +
            (s_val * self.weights["validation"]) +
            (s_pat * self.weights["pattern"]) +
            (s_method * self.weights.get("method", 0.0)) +
            (s_visual * self.weights.get("visual", 0.0))
        )
        
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
                "method_offset": s_method,
                "visual_diff": s_visual if visual_diff is not None else None
            }
        }

def get_confidence_engine() -> ConfidenceEngine:
    return ConfidenceEngine()
