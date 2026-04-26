"""
Phase 4.5 — Checkbox & Radio Button Detection
============================================
Analyses specific regions for pixel density to detect marks.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any
from config import settings

logger = logging.getLogger(__name__)

class MarkDetector:
    """Implements Phase 4.5: Pixel density analysis for checkboxes."""

    def __init__(self, density_threshold: float = None):
        self.density_threshold = density_threshold or settings.PIXEL_DENSITY_THRESHOLD

    def is_marked(self, img_bgr: np.ndarray, bbox: list) -> Dict[str, Any]:
        """
        Detects if a checkbox/radio is marked based on pixel density.
        
        Args:
            img_bgr: Preprocessed image
            bbox: [x_min, y_min, x_max, y_max]
            
        Returns:
            Dict with "is_marked" (bool) and "density" (float)
        """
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # 1. Crop the region
        crop = img_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return {"is_marked": False, "density": 0.0, "status": "ERROR: Empty Crop"}

        # 1.5 Margin Exclusion (Phase 4.5 spec: 10% outer border)
        ch, cw = crop.shape[:2]
        my = int(ch * settings.MARGIN_EXCLUSION_RATIO)
        mx = int(cw * settings.MARGIN_EXCLUSION_RATIO)
        
        # Ensure margin doesn't consume the whole crop
        if ch > 2*my and cw > 2*mx:
            crop = crop[my:ch-my, mx:cw-mx]

        # 2. Convert to grayscale and apply Otsu thresholding
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # We invert the image so that marks (ink) are white (255)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # 3. Calculate pixel density
        total_pixels = thresh.size
        marked_pixels = np.count_nonzero(thresh)
        density = marked_pixels / float(total_pixels)
        
        is_marked = density > self.density_threshold
        
        return {
            "is_marked": bool(is_marked),
            "density": round(float(density), 4),
            "status": "MARKED" if is_marked else "EMPTY"
        }

def get_mark_detector() -> MarkDetector:
    return MarkDetector()
