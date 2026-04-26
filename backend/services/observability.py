"""
Phase 12 — Observability, Logging & Debugging
============================================
Implements the tracing and debug bundle system.
"""

import os
import json
import zipfile
import logging
import io
from typing import Dict, Any, Optional
from datetime import datetime
import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEBUG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "debug_traces"
)

class ObservabilityService:
    """Handles Phase 12: Debug tracing and bundle generation."""

    def __init__(self, debug_dir: str = DEBUG_DIR):
        self.debug_dir = debug_dir
        os.makedirs(self.debug_dir, exist_ok=True)

    def save_trace(self, request_id: str, data: Dict[str, Any], images: Dict[str, Any] = None):
        """Saves a detailed trace of the processing request."""
        trace_path = os.path.join(self.debug_dir, f"{request_id}_trace.json")
        
        # We don't save raw images in the JSON, only paths or metadata
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        
        # If we have binary images, we save them separately
        if images:
            for name, img in images.items():
                img_path = os.path.join(self.debug_dir, f"{request_id}_{name}.jpg")
                img.save(img_path, "JPEG")

    def generate_debug_bundle(self, request_id: str, db_service: Any) -> Optional[str]:
        """Creates a ZIP bundle for debugging a specific request."""
        request_data = db_service.get_request(request_id)
        if not request_data:
            return None

        zip_path = os.path.join(self.debug_dir, f"debug_{request_id}.zip")
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # 1. Add trace JSON
            trace_file = os.path.join(self.debug_dir, f"{request_id}_trace.json")
            if os.path.exists(trace_file):
                zf.write(trace_file, "trace.json")
            
            # 2. Add original image
            trace = request_data.get("trace") or {}
            original_path = trace.get("file_path", "")
            if original_path and os.path.exists(original_path):
                zf.write(original_path, "original.jpg")
            
            # 3. Add preprocessed image
            preprocessed_path = os.path.join(self.debug_dir, f"{request_id}_preprocessed.jpg")
            if os.path.exists(preprocessed_path):
                zf.write(preprocessed_path, "preprocessed.jpg")
            
            # 4. Add DB snapshot for this request
            zf.writestr("db_snapshot.json", json.dumps(request_data, indent=2, default=str))

        return zip_path

    def generate_debug_overlay(self, img_bgr: np.ndarray, diag: Dict[str, Any]) -> np.ndarray:
        """Phase 12: Generates an image with bounding boxes for all detected fields."""
        overlay = img_bgr.copy()
        
        # Draw fields
        for field in diag.get("fields", []):
            bbox = field.get("bbox")
            if not bbox: continue
            
            # Draw rectangle
            color = (0, 255, 0) # Green for OK
            if field.get("status") == "REJECT":
                color = (0, 0, 255) # Red for Reject
            elif field.get("status") == "NEEDS_REVIEW":
                color = (0, 165, 255) # Orange for Review
                
            x1, y1, x2, y2 = [int(v) for v in bbox]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
            
            # Label
            label = f"{field['id']}: {field.get('cleaned_value', '')[:10]}"
            cv2.putText(overlay, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        return overlay

def get_observability_service() -> ObservabilityService:
    return ObservabilityService()
