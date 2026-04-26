"""
Phase 3 — Line Reconstruction
============================
Groups individual word detections into coherent, spatially-sorted lines.
"""

import logging
from typing import List, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


def _get_rect(poly):
    """Convert polygon [[x,y], ...] to [x_min, y_min, x_max, y_max]."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [min(xs), min(ys), max(xs), max(ys)]

class LineReconstructor:
    """Implements Phase 3: Spatial word grouping into lines."""

    def __init__(self, y_threshold_ratio: float = None):
        self.y_threshold_ratio = y_threshold_ratio or settings.Y_PROXIMITY_THRESHOLD

    def reconstruct_lines(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Groups words into lines based on vertical proximity and horizontal merging.
        """
        if not words:
            return []

        # 1. Sort words primarily by Y-top, secondarily by X-left
        sorted_words = sorted(words, key=lambda w: (_get_rect(w["bbox"])[1], _get_rect(w["bbox"])[0]))

        lines = []
        current_line_words = [sorted_words[0]]

        for i in range(1, len(sorted_words)):
            prev_word = current_line_words[-1]
            curr_word = sorted_words[i]
            
            p_rect = _get_rect(prev_word["bbox"])
            c_rect = _get_rect(curr_word["bbox"])

            # Calculate Y-centers
            prev_center_y = (p_rect[1] + p_rect[3]) / 2
            curr_center_y = (c_rect[1] + c_rect[3]) / 2
            
            # Calculate heights
            prev_h = p_rect[3] - p_rect[1]
            curr_h = c_rect[3] - c_rect[1]
            avg_h = (prev_h + curr_h) / 2

            # Vertical proximity check
            if abs(curr_center_y - prev_center_y) < (avg_h * self.y_threshold_ratio):
                current_line_words.append(curr_word)
            else:
                lines.append(self._finalize_line(current_line_words))
                current_line_words = [curr_word]

        if current_line_words:
            lines.append(self._finalize_line(current_line_words))

        # Final spatial sort (Top-to-Bottom, then Left-to-Right)
        lines = sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))

        logger.info(f"[Phase 3] Reconstructed {len(lines)} lines.")
        return lines

    def _finalize_line(self, line_words: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merges fragments and creates line metadata."""
        # Sort words in line by X-left
        sorted_line_words = sorted(line_words, key=lambda w: _get_rect(w["bbox"])[0])
        
        # Horizontal fragment merging (Phase 3 spec: 0.3x char width)
        merged_text = ""
        if sorted_line_words:
            merged_text = sorted_line_words[0]["text"]
            for i in range(1, len(sorted_line_words)):
                prev_w = sorted_line_words[i-1]
                curr_w = sorted_line_words[i]
                
                p_r = _get_rect(prev_w["bbox"])
                c_r = _get_rect(curr_w["bbox"])
                
                # Estimated char width
                char_w = (p_r[2] - p_r[0]) / max(len(prev_w["text"]), 1)
                dist = c_r[0] - p_r[2]
                
                if dist < (0.3 * char_w):
                    merged_text += curr_w["text"] # Merge without space
                else:
                    merged_text += " " + curr_w["text"] # Standard join
        
        # Line-level bbox (Rect for now, but derived from all polygons)
        all_xs = []
        all_ys = []
        for w in sorted_line_words:
            for p in w["bbox"]:
                all_xs.append(p[0])
                all_ys.append(p[1])
        
        bbox = [min(all_xs), min(all_ys), max(all_xs), max(all_ys)]
        
        # min() confidence aggregation (Phase 3 spec)
        min_conf = min(w["confidence"] for w in sorted_line_words)
        
        return {
            "text": merged_text,
            "words": sorted_line_words,
            "bbox": bbox,
            "confidence": round(min_conf, 4)
        }

def get_line_reconstructor() -> LineReconstructor:
    return LineReconstructor()
