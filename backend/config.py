"""
Phase 13 — Configuration & Extensibility
=======================================
Centralized configuration for the v2.0 Pipeline.
"""

import os
from pydantic_settings import BaseSettings

from typing import Tuple, Dict, Optional
import sys

class Settings(BaseSettings):
    # Image Preprocessing
    TARGET_WIDTH: int = 1200
    BLUR_THRESHOLD: float = 50.0
    BRIGHTNESS_THRESHOLD: Tuple[float, float] = (40.0, 240.0)
    
    # Security (Phase 15)
    API_KEY: str = os.getenv("API_KEY", "pipeline_secret_v2")
    
    # OCR
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    OCR_RETRIES: int = 3
    OCR_BACKOFF: int = 1
    
    # Line Reconstruction
    Y_PROXIMITY_THRESHOLD: float = 0.5
    
    # Extraction
    PIXEL_DENSITY_THRESHOLD: float = 0.15 # 15% for checkboxes
    MARGIN_EXCLUSION_RATIO: float = 0.10 # 10% outer margin
    
    # Confidence thresholds
    AUTO_ACCEPT_THRESHOLD: float = 0.85
    CONFIDENCE_WEIGHTS: Dict[str, float] = {
        "ocr": 0.4,
        "validation": 0.3,
        "pattern": 0.2,
        "method": 0.1
    }
    
    # Orientation & Deskew
    ORIENTATION_RATIO: float = 1.3 # Width > Height by 1.3x for landscape detection
    MAX_DESKEW_ANGLE: float = 15.0 # Reject if skew > 15 degrees
    
    # Persistence
    DB_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pipeline.db")
    
    # Phase 14/15: Operational settings
    CORS_ORIGINS: str = "*"
    MAX_UPLOAD_BYTES: int = 10_485_760  # 10MB
    RATE_LIMIT_RPM: int = 20
    
    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

    def validate_settings(self):
        """Phase 13: Startup validation to fail-fast on invalid thresholds."""
        try:
            if not (0 < self.PIXEL_DENSITY_THRESHOLD < 1):
                raise ValueError("PIXEL_DENSITY_THRESHOLD must be between 0 and 1")
            if abs(sum(self.CONFIDENCE_WEIGHTS.values()) - 1.0) > 0.01:
                raise ValueError("CONFIDENCE_WEIGHTS must sum to 1.0")
            if self.TARGET_WIDTH < 500:
                raise ValueError("TARGET_WIDTH too small for reliable OCR")
            if not self.GOOGLE_API_KEY:
                # We log a warning but don't exit, as user might want local fallback (if implemented)
                import logging
                logging.warning("GOOGLE_API_KEY is missing. OCR will fail unless fallback is configured.")
        except Exception as e:
            import logging
            logging.critical(f"CRITICAL CONFIG ERROR: {e}")
            sys.exit(1)

settings = Settings()
settings.validate_settings()
