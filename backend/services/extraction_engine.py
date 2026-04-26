"""
Phase 4 — Extraction Engine (Hybrid)
====================================
Locates and extracts field values using Anchor-based, Zone-based, 
or Line-based search strategies.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process
from .mark_detector import get_mark_detector

logger = logging.getLogger(__name__)

class ExtractionEngine:
    """Implements Phase 4: Template-driven data extraction."""

    def __init__(self):
        self.mark_detector = get_mark_detector()

    def extract_fields(self, lines: List[Dict[str, Any]], template: Dict[str, Any], img_bgr: Any, all_words: List[Dict] = None) -> List[Dict[str, Any]]:
        """
        Extracts all fields defined in the template.
        
        Args:
            lines: Reconstructed lines from Phase 3.
            template: Dict containing field definitions.
            img_bgr: Preprocessed image (for checkbox analysis).
            all_words: Optional list of all word detections (for zone filtering).
            
        Returns:
            List of extracted fields with metadata.
        """
        results = []
        h, w = img_bgr.shape[:2]
        all_words = all_words or []

        for field in template.get("fields", []):
            field_id = field.get("id")
            strategy = field.get("strategy", "anchor")
            field_type = field.get("type", "text")
            
            extracted = {
                "id": field_id,
                "type": field_type,
                "raw_value": None,
                "confidence": 0.0,
                "status": "NOT_FOUND",
                "strategy": strategy,
                "bbox": None
            }

            if strategy == "anchor":
                extracted = self._extract_by_anchor(field, lines, extracted)
            elif strategy == "zone":
                extracted = self._extract_by_zone(field, img_bgr, extracted, w, h, all_words)
            elif strategy == "line_search":
                extracted = self._extract_by_line_search(field, lines, extracted)
            elif strategy == "radio_group":
                extracted = self._extract_by_radio_group(field, img_bgr, extracted, w, h)

            results.append(extracted)

        logger.info(f"[Phase 4] Extracted {len(results)} fields.")
        return results

    def _extract_by_anchor(self, field: Dict, lines: List[Dict], entry: Dict) -> Dict:
        """Finds a label and looks for value to the right or below it."""
        # 1. Multi-Anchor Support (Phase 4 spec: list of aliases)
        anchors = field.get("anchor_texts") or [field.get("anchor_text", "")]
        best_anchor = None
        best_score = 0
        
        for line in lines:
            line_text_lower = line["text"].lower()
            for anchor in anchors:
                if not anchor: continue
                score = fuzz.partial_ratio(anchor.lower(), line_text_lower)
                if score > 85 and score > best_score:
                    best_score = score
                    best_anchor = line
                    anchor_text = anchor # Keep track of which anchor matched

        if not best_anchor:
            return entry

        direction = field.get("search_direction", "right")
        max_dist = field.get("max_distance", 500) # Default 500px

        # 2. Search for value
        if direction == "right":
            # Look for text in the SAME line that is NOT the anchor text
            # This is a simplification; a better way is to look at word positions.
            # For now, we take the text in the same line after the anchor text.
            line_text = best_anchor["text"]
            # Find start index of anchor in text
            match = re.search(re.escape(anchor_text.lower()), line_text.lower())
            if match:
                value = line_text[match.end():].strip()
                # Clean up leading symbols common in forms (:, -, etc.)
                value = re.sub(r"^[:\-\s]+", "", value)
                if value:
                    entry["raw_value"] = value
                    entry["confidence"] = best_anchor["confidence"]
                    entry["status"] = "OK"
                    entry["bbox"] = best_anchor["bbox"]
        
        elif direction == "below":
            # Look for the line immediately below the anchor line
            anchor_idx = lines.index(best_anchor)
            if anchor_idx + 1 < len(lines):
                below_line = lines[anchor_idx + 1]
                # Check vertical distance
                v_dist = below_line["bbox"][1] - best_anchor["bbox"][3]
                if v_dist < max_dist:
                    entry["raw_value"] = below_line["text"]
                    entry["confidence"] = below_line["confidence"]
                    entry["status"] = "OK"
                    entry["bbox"] = below_line["bbox"]

        return entry

    def _extract_by_zone(self, field: Dict, img_bgr: Any, entry: Dict, w: int, h: int, all_words: List[Dict]) -> Dict:
        """Looks in a specific rectangular zone."""
        bbox_ratio = field.get("bbox_ratio") # [x1_ratio, y1_ratio, x2_ratio, y2_ratio]
        if not bbox_ratio:
            return entry
            
        real_bbox = [
            int(bbox_ratio[0] * w),
            int(bbox_ratio[1] * h),
            int(bbox_ratio[2] * w),
            int(bbox_ratio[3] * h)
        ]
        entry["bbox"] = real_bbox

        if field.get("type") == "checkbox":
            res = self.mark_detector.is_marked(img_bgr, real_bbox)
            entry["raw_value"] = "MARKED" if res["is_marked"] else "EMPTY"
            entry["confidence"] = 1.0 # Pixel density is deterministic
            entry["status"] = "OK"
            entry["density"] = res["density"]
        else:
            # Phase 4 Spec: Filter all_words by real_bbox
            zone_words = []
            for word in all_words:
                # Calculate center of word bbox
                wb = word["bbox"]
                cx = sum(p[0] for p in wb) / 4
                cy = sum(p[1] for p in wb) / 4
                
                if real_bbox[0] <= cx <= real_bbox[2] and real_bbox[1] <= cy <= real_bbox[3]:
                    zone_words.append(word)
            
            if zone_words:
                # Sort by X-left then Y-top
                zone_words.sort(key=lambda x: (x["bbox"][0][0], x["bbox"][0][1]))
                entry["raw_value"] = " ".join([w["text"] for w in zone_words])
                entry["confidence"] = min([w["confidence"] for w in zone_words])
                entry["status"] = "OK"
            else:
                entry["raw_value"] = ""
                entry["status"] = "NOT_FOUND"
            
        return entry

    def _extract_by_radio_group(self, field: Dict, img_bgr: Any, entry: Dict, w: int, h: int) -> Dict:
        """Phase 4.5: Winner Takes All logic for radio button groups."""
        options = field.get("options", [])
        if not options:
            return entry
            
        densities = []
        for opt in options:
            bbox_ratio = opt.get("bbox_ratio")
            if not bbox_ratio: continue
            
            real_bbox = [
                int(bbox_ratio[0] * w),
                int(bbox_ratio[1] * h),
                int(bbox_ratio[2] * w),
                int(bbox_ratio[3] * h)
            ]
            res = self.mark_detector.is_marked(img_bgr, real_bbox)
            densities.append({
                "value": opt.get("value"),
                "density": res["density"],
                "bbox": real_bbox
            })
            
        if not densities:
            return entry
            
        # Winner Takes All (Highest density)
        winner = max(densities, key=lambda x: x["density"])
        
        entry["raw_value"] = winner["value"]
        entry["confidence"] = 1.0 # Logic is deterministic
        entry["status"] = "OK"
        entry["bbox"] = winner["bbox"]
        entry["all_densities"] = densities # For audit trace
        
        return entry

    def _extract_by_line_search(self, field: Dict, lines: List[Dict], entry: Dict) -> Dict:
        """Regex search across all lines."""
        pattern = field.get("regex")
        if not pattern:
            return entry
            
        for line in lines:
            match = re.search(pattern, line["text"])
            if match:
                # If groups exist, take the first group, else full match
                val = match.group(1) if match.groups() else match.group(0)
                entry["raw_value"] = val
                entry["confidence"] = line["confidence"]
                entry["status"] = "OK"
                entry["bbox"] = line["bbox"]
                break
                
        return entry

def get_extraction_engine() -> ExtractionEngine:
    return ExtractionEngine()
