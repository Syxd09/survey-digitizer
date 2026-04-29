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
        """Handles 90/270 (Landscape -> Portrait) and 180 (Upside Down) rotations."""
        h, w = img_bgr.shape[:2]
        diag = {"coarse_rotated": False, "rotation_degrees": 0, "wh_ratio": round(w/h, 2)}
        rotated = img_bgr

        # 1. Handle 90/270 (Landscape)
        if w > h:
            logger.info(f"[Phase 1] Landscape detected (W/H ratio: {w/h:.2f}). Rotating 90° CW.")
            rotated = cv2.rotate(rotated, cv2.ROTATE_90_CLOCKWISE)
            diag["coarse_rotated"] = True
            diag["rotation_degrees"] += 90
            h, w = rotated.shape[:2] # Update dims

        # 2. Handle 180 (Upside Down) using text confidence heuristic
        try:
            import easyocr
            # We crop the top 30% of the image (which usually contains the title/header)
            crop_h = int(h * 0.3)
            top_crop = rotated[0:crop_h, 0:w]
            
            # Use local easyocr for a fast check
            reader = easyocr.Reader(['en'], gpu=False)
            results = reader.readtext(top_crop)
            
            # If no text found or average confidence is very low, it might be upside down
            if not results:
                # Let's check the bottom 30% just in case it's upside down
                bottom_crop = rotated[h-crop_h:h, 0:w]
                bottom_results = reader.readtext(bottom_crop)
                if bottom_results:
                    logger.info("[Phase 1] Text found at bottom but not top. Likely 180° upside down.")
                    rotated = cv2.rotate(rotated, cv2.ROTATE_180)
                    diag["coarse_rotated"] = True
                    diag["rotation_degrees"] += 180
        except Exception as e:
            logger.warning(f"[Phase 1] 180-degree detection failed, skipping: {e}")

        return rotated, diag

    def _fine_deskew(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Correct arbitrary rotation and perspective using 4-Point Transform."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Find largest contour which usually represents the document paper
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img_bgr, {"fine_deskew_applied": False, "skew_angle": 0.0}
            
        largest_contour = max(contours, key=cv2.contourArea)
        
        # If the largest contour doesn't take up at least 20% of the image, fallback to minAreaRect text rotation
        h, w = img_bgr.shape[:2]
        if cv2.contourArea(largest_contour) < (h * w * 0.2):
            # Fallback: Find the minimum bounding box of all text/lines
            rect = cv2.minAreaRect(largest_contour)
            raw_angle = rect[-1]
            
            # cv2.minAreaRect returns angle in different ranges depending on version:
            #   Old (< 4.5): [-90, 0)  where -90 means upright/axis-aligned
            #   New (>= 4.5): [0, 90)  where 0 means upright/axis-aligned
            # We need to extract the actual skew: deviation from nearest 90° multiple.
            # Normalize raw_angle to [0, 180) first, then compute skew as distance from nearest multiple of 90.
            normalized = raw_angle % 180  # Map to [0, 180)
            # Distance from nearest axis (0, 90, 180)
            skew = min(normalized, abs(90 - normalized), abs(180 - normalized))
            
            # Determine correction direction
            if skew > 0.5:
                # Simple approach: use the raw angle modulo to determine correction
                if normalized < 45:
                    correction_angle = -normalized
                elif normalized < 90:
                    correction_angle = 90 - normalized
                elif normalized < 135:
                    correction_angle = 90 - normalized
                else:
                    correction_angle = 180 - normalized
                    
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, correction_angle, 1.0)
                rotated = cv2.warpAffine(img_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                return rotated, {"fine_deskew_applied": True, "skew_angle": round(float(skew), 2)}
            return img_bgr, {"fine_deskew_applied": False, "skew_angle": 0.0}

        # Otherwise, perform 4-point transform
        epsilon = 0.02 * cv2.arcLength(largest_contour, True)
        approx = cv2.approxPolyDP(largest_contour, epsilon, True)
        
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            # Order points: top-left, top-right, bottom-right, bottom-left
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]
            
            (tl, tr, br, bl) = rect
            widthA = np.linalg.norm(br - bl)
            widthB = np.linalg.norm(tr - tl)
            maxWidth = max(int(widthA), int(widthB))
            
            heightA = np.linalg.norm(tr - br)
            heightB = np.linalg.norm(tl - bl)
            maxHeight = max(int(heightA), int(heightB))
            
            dst = np.array([
                [0, 0],
                [maxWidth - 1, 0],
                [maxWidth - 1, maxHeight - 1],
                [0, maxHeight - 1]], dtype="float32")
                
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img_bgr, M, (maxWidth, maxHeight))
            return warped, {"fine_deskew_applied": True, "perspective_warped": True, "skew_angle": 0.0}
            
        return img_bgr, {"fine_deskew_applied": False, "skew_angle": 0.0}

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
        diag = {"clahe_applied": False, "sauvola_applied": False, "median_blur_applied": True}
        
        # 0. Median Blur for Salt-and-Pepper noise reduction
        gray = cv2.medianBlur(gray, 3)
        img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) # Update BGR with denoised gray

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
