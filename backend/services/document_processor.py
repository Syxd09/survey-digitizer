"""
Phase 1 — Image Quality & Preprocessing
=======================================
Standardises incoming images into OCR-ready assets with orientation correction,
size normalisation, and quality validation.
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Dict, Any, Optional
from skimage.filters import threshold_sauvola

from config import settings

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Implements Phase 1 of the OCR Form Processing Pipeline v2.0."""

    def __init__(self, target_width: int = None):
        self.target_width = target_width or settings.TARGET_WIDTH
        self.blur_threshold = settings.BLUR_THRESHOLD
        self.brightness_min, self.brightness_max = settings.BRIGHTNESS_THRESHOLD
        self.orientation_ratio = settings.ORIENTATION_RATIO
        self.max_deskew_angle = settings.MAX_DESKEW_ANGLE

    def process_document(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Executes the Phase 1 pipeline: Quality → Orientation → Deskew → Normalise → Enhance.
        
        Returns:
            Tuple of (processed_image, diagnostics_dict)
        """
        diag = {
            "version": "2.0",
            "stage": "Phase 1: Preprocessing",
            "quality": {},
            "orientation": {},
            "normalization": {}
        }
        
        h_orig, w_orig = img_bgr.shape[:2]
        diag["original_dims"] = {"w": w_orig, "h": h_orig}

        # 1. Quality Assessment
        quality_diag = self._assess_quality(img_bgr)
        diag["quality"] = quality_diag
        
        # 2. Coarse Orientation Correction
        # Rule: If Width > Height, rotate 90 deg clockwise (assumes portrait form)
        img_orient, orientation_diag = self._correct_orientation(img_bgr)
        diag["orientation"] = orientation_diag

        # 3. Fine Deskew (Hough Transform)
        img_deskew, deskew_diag = self._fine_deskew(img_orient)
        diag["orientation"].update(deskew_diag)

        # 4. Fixed Width Normalisation
        img_norm, norm_diag = self._normalise_size(img_deskew)
        diag["normalization"] = norm_diag
        
        # 4.5 Check for rejection (Phase 1 SPEC: Reject if skew > 15 deg)
        if abs(deskew_diag.get("skew_angle", 0)) > self.max_deskew_angle:
            diag["quality"]["status"] = "REJECT"
            diag["quality"]["rejection_reason"] = f"Skew angle ({deskew_diag['skew_angle']}°) exceeds limit ({self.max_deskew_angle}°)"

        # 5. Conditional Enhancement (CLAHE + Sauvola)
        img_final, enhance_diag = self._conditional_enhance(img_norm)
        diag["enhancement"] = enhance_diag

        logger.info(f"[Phase 1] Complete. Scale Factor: {norm_diag['scale_factor']:.4f}")
        return img_final, diag

    def _assess_quality(self, img_bgr: np.ndarray) -> Dict[str, Any]:
        """Check for blur and brightness issues."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # Blur check: Laplacian variance
        blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_blurry = blur_val < self.blur_threshold
        
        # Brightness check: Mean pixel intensity
        brightness_val = np.mean(gray)
        is_too_dark = brightness_val < self.brightness_min
        is_too_bright = brightness_val > self.brightness_max
        
        return {
            "blur_value": round(float(blur_val), 2),
            "is_blurry": bool(is_blurry),
            "brightness_value": round(float(brightness_val), 2),
            "is_too_dark": bool(is_too_dark),
            "is_too_bright": bool(is_too_bright),
            "status": "PASS" if not (is_blurry or is_too_dark or is_too_bright) else "FAIL"
        }

    def _correct_orientation(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Rotate if image is landscape (W > H by 1.3x factor) but expected portrait."""
        h, w = img_bgr.shape[:2]
        if w > (h * self.orientation_ratio):
            logger.info(f"[Phase 1] Landscape detected (W/H ratio: {w/h:.2f}). Rotating 90° CW.")
            rotated = cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
            return rotated, {"coarse_rotated": True, "rotation_degrees": 90, "wh_ratio": round(w/h, 2)}
        return img_bgr, {"coarse_rotated": False, "rotation_degrees": 0, "wh_ratio": round(w/h, 2)}

    def _fine_deskew(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Correct small rotations using Hough Transform."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        
        if lines is None:
            return img_bgr, {"fine_deskew_applied": False, "skew_angle": 0.0}
            
        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            if -10 < angle < 10: # Only look for small skews
                angles.append(angle)
        
        if not angles:
            return img_bgr, {"fine_deskew_applied": False, "skew_angle": 0.0}
            
        median_angle = np.median(angles)
        
        # Only apply if > 0.5 degrees
        if abs(median_angle) > 0.5:
            (h, w) = img_bgr.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            rotated = cv2.warpAffine(img_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated, {"fine_deskew_applied": True, "skew_angle": round(float(median_angle), 2)}
            
        return img_bgr, {"fine_deskew_applied": False, "skew_angle": round(float(median_angle), 2)}

    def _normalise_size(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Resize to fixed width while maintaining aspect ratio."""
        h, w = img_bgr.shape[:2]
        scale_factor = self.target_width / float(w)
        target_height = int(h * scale_factor)
        
        resized = cv2.resize(img_bgr, (self.target_width, target_height), interpolation=cv2.INTER_AREA)
        
        return resized, {
            "scale_factor": round(float(scale_factor), 6),
            "target_width": self.target_width,
            "target_height": target_height
        }

    def _conditional_enhance(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Apply CLAHE and Sauvola binarization if image quality is poor."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        diag = {"clahe_applied": False, "sauvola_applied": False}
        
        # 1. CLAHE for contrast
        contrast = np.std(gray)
        diag["contrast_score"] = round(float(contrast), 2)
        
        enhanced = img_bgr
        if contrast < 40.0:
            logger.info(f"[Phase 1] Low contrast ({contrast:.2f}). Applying CLAHE.")
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l_enhanced = clahe.apply(l)
            enhanced_lab = cv2.merge((l_enhanced, a, b))
            enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            diag["clahe_applied"] = True
            gray = l_enhanced # Update gray for potential Sauvola

        # 2. Sauvola for binarization (only if blurry or very low contrast)
        # Sauvola is expensive, so we only use it if needed for better OCR
        blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur_val < self.blur_threshold or contrast < 30.0:
            logger.info(f"[Phase 1] Poor quality (Blur: {blur_val:.2f}, Contrast: {contrast:.2f}). Applying Sauvola.")
            thresh_sauvola = threshold_sauvola(gray, window_size=25)
            binary_sauvola = (gray > thresh_sauvola).astype(np.uint8) * 255
            # Convert back to BGR for pipeline consistency
            enhanced = cv2.cvtColor(binary_sauvola, cv2.COLOR_GRAY2BGR)
            diag["sauvola_applied"] = True
            
        return enhanced, diag

def get_document_processor() -> DocumentProcessor:
    return DocumentProcessor()
