"""
Hydra v12.5 — Restoration Layer
================================
Dual-output image preprocessing.
Produces TWO images:
  - raw_corrected: polarity-only (for PaddleOCR's internal preprocessing)
  - enhanced: CLAHE + denoise (for EasyOCR + Tesseract)
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Dict

logger = logging.getLogger(__name__)


class ImageRestorer:
    def __init__(self):
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def process(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict]:
        """
        Main entry point for image restoration.

        Returns:
            (img_for_paddle, img_for_others, diagnostics)
            - img_for_paddle: minimal processing (polarity only)
            - img_for_others: enhanced for EasyOCR / Tesseract
        """
        if img is None:
            return None, None, {}

        diagnostics = {}

        # 1. Evaluate Polarity (Dark vs Light)
        img_polarity_corrected, is_dark = self._handle_polarity(img)
        diagnostics["is_dark_mode"] = is_dark

        # 2. PaddleOCR path: polarity-corrected only + mild resize if tiny
        img_for_paddle = img_polarity_corrected.copy()
        h, w = img_for_paddle.shape[:2]
        if h < 600 or w < 600:
            img_for_paddle = self._upscale_clean(img_for_paddle, factor=2.0)
            diagnostics["paddle_upscaled"] = True

        # 3. Enhanced path for EasyOCR + Tesseract
        img_enhanced = self._enhance_text_clarity(img_polarity_corrected)
        h2, w2 = img_enhanced.shape[:2]
        if h2 < 1000 or w2 < 1000:
            img_enhanced = self._upscale_clean(img_enhanced, factor=2.0)
            diagnostics["enhanced_upscaled"] = True

        return img_for_paddle, img_enhanced, diagnostics

    def _handle_polarity(self, img: np.ndarray) -> Tuple[np.ndarray, bool]:
        """
        Detects dark-themed images and inverts to black-on-white.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        mean_brightness = float(np.mean(gray))

        if mean_brightness < 80:
            logger.info(f"[RESTORE] Dark mode detected (avg={mean_brightness:.1f}). Inverting.")
            return cv2.bitwise_not(img), True
        return img, False

    def _enhance_text_clarity(self, img: np.ndarray) -> np.ndarray:
        """
        CLAHE contrast enhancement + mild denoising.
        No sharpening kernel — it creates ringing artifacts that destroy OCR.
        """
        # Convert to LAB for perceptual contrast enhancement
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)

        # CLAHE on luminance channel
        l_enhanced = self.clahe.apply(l_chan)
        lab_enhanced = cv2.merge((l_enhanced, a_chan, b_chan))
        enhanced = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        # Mild denoising (preserve edges)
        denoised = cv2.fastNlMeansDenoisingColored(enhanced, None, 6, 6, 7, 15)

        return denoised

    def _upscale_clean(self, img: np.ndarray, factor: float = 2.0) -> np.ndarray:
        """
        Clean upscale using INTER_CUBIC. No post-sharpening.
        """
        h, w = img.shape[:2]
        new_size = (int(w * factor), int(h * factor))
        return cv2.resize(img, new_size, interpolation=cv2.INTER_CUBIC)


def get_restorer():
    return ImageRestorer()
