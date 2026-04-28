"""
Phase 4.3 — Dynamic Grid Detection
===================================
Detects table/grid structure from scanned form images using morphological
line detection. Replaces all hardcoded bounding box positions.

Pipeline:
  1. Isolate horizontal & vertical lines via morphological kernels
  2. Find table boundary from combined line mask
  3. Segment rows from horizontal line projection
  4. Segment columns from vertical line projection
  5. Construct cell grid from row × column intersections
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)


class GridDetector:
    """Detects table grids dynamically using OpenCV morphological operations."""

    def __init__(self):
        self.h_scale = getattr(settings, "GRID_LINE_SCALE_HORIZONTAL", 15)
        self.v_scale = getattr(settings, "GRID_LINE_SCALE_VERTICAL", 15)
        self.min_row_height = getattr(settings, "GRID_MIN_ROW_HEIGHT", 20)
        self.min_col_width = getattr(settings, "GRID_MIN_COL_WIDTH", 30)
        self.line_cluster_gap = getattr(settings, "GRID_LINE_THRESHOLD", 8)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def detect_grid(self, img_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Full grid detection pipeline.

        Returns:
            Dict with:
                "success": bool
                "table_bbox": [x1, y1, x2, y2] or None
                "rows": list of (y1, y2) tuples
                "columns": list of (x1, x2) tuples
                "cells": list of dicts with row_index, col_index, bbox
                "question_columns": int (number of option columns, excluding question text col)
                "diagnostics": dict with debug info
        """
        h, w = img_bgr.shape[:2]
        diag = {"image_size": (w, h)}

        # Stage 1: Line isolation
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h_mask, v_mask = self._isolate_lines(gray, w, h)
        diag["h_lines_pixels"] = int(np.count_nonzero(h_mask))
        diag["v_lines_pixels"] = int(np.count_nonzero(v_mask))

        # Stage 2: Table boundary
        table_bbox = self._find_table_boundary(h_mask, v_mask, w, h)
        diag["table_bbox"] = table_bbox

        if table_bbox is None:
            logger.warning("[GridDetector] No table boundary found.")
            return {
                "success": False,
                "table_bbox": None,
                "rows": [],
                "columns": [],
                "cells": [],
                "question_columns": 0,
                "diagnostics": diag,
            }

        tx1, ty1, tx2, ty2 = table_bbox

        # Stage 3: Row segmentation
        h_mask_table = h_mask[ty1:ty2, tx1:tx2]
        row_boundaries = self._segment_axis(
            h_mask_table, axis="horizontal", length=(ty2 - ty1)
        )
        # Ensure table edges are included as boundaries
        row_boundaries = self._ensure_edge_boundaries(
            row_boundaries, 0, ty2 - ty1
        )
        # Convert to absolute coordinates
        rows = self._boundaries_to_ranges(row_boundaries, ty1, self.min_row_height)
        diag["raw_row_boundaries"] = len(row_boundaries)
        diag["rows_detected"] = len(rows)

        # Stage 4: Column segmentation
        v_mask_table = v_mask[ty1:ty2, tx1:tx2]
        col_boundaries = self._segment_axis(
            v_mask_table, axis="vertical", length=(tx2 - tx1)
        )
        # Ensure table edges are included as boundaries
        col_boundaries = self._ensure_edge_boundaries(
            col_boundaries, 0, tx2 - tx1
        )
        # Convert to absolute coordinates
        columns = self._boundaries_to_ranges(col_boundaries, tx1, self.min_col_width)
        diag["raw_col_boundaries"] = len(col_boundaries)
        diag["columns_detected"] = len(columns)

        if len(rows) < 1 or len(columns) < 2:
            logger.warning(
                f"[GridDetector] Insufficient grid structure: "
                f"{len(rows)} rows, {len(columns)} columns."
            )
            return {
                "success": False,
                "table_bbox": table_bbox,
                "rows": rows,
                "columns": columns,
                "cells": [],
                "question_columns": 0,
                "diagnostics": diag,
            }

        # Stage 5: Identify question column vs option columns
        # The question/text column is typically the widest (first or second column)
        question_col_idx, option_columns = self._identify_question_column(columns)
        diag["question_col_idx"] = question_col_idx
        diag["option_columns"] = len(option_columns)

        # Detect and skip header rows (first 1-2 rows are typically headers)
        header_rows, data_rows = self._split_header_data_rows(rows, img_bgr, columns)
        diag["header_rows"] = len(header_rows)
        diag["data_rows"] = len(data_rows)

        # Build cell grid
        cells = []
        for row_idx, (ry1, ry2) in enumerate(data_rows):
            for col_idx, (cx1, cx2) in enumerate(option_columns):
                cells.append({
                    "row_index": row_idx,
                    "col_index": col_idx,
                    "bbox": [cx1, ry1, cx2, ry2],
                    "row_range": (ry1, ry2),
                    "col_range": (cx1, cx2),
                })

        logger.info(
            f"[GridDetector] Detected grid: {len(data_rows)} data rows × "
            f"{len(option_columns)} option columns = {len(cells)} cells."
        )

        return {
            "success": True,
            "table_bbox": table_bbox,
            "rows": data_rows,
            "header_rows": header_rows,
            "columns": columns,
            "option_columns": option_columns,
            "cells": cells,
            "question_columns": len(option_columns),
            "question_col_idx": question_col_idx,
            "diagnostics": diag,
        }

    def generate_debug_overlay(
        self, img_bgr: np.ndarray, grid_result: Dict[str, Any]
    ) -> np.ndarray:
        """Draws detected grid lines and cell bboxes on a copy of the image."""
        overlay = img_bgr.copy()

        if not grid_result.get("success"):
            return overlay

        # Draw table boundary
        tb = grid_result["table_bbox"]
        if tb:
            cv2.rectangle(overlay, (tb[0], tb[1]), (tb[2], tb[3]), (255, 0, 0), 2)

        # Draw data row cells
        colors = [
            (0, 0, 255),    # Red
            (0, 165, 255),  # Orange
            (0, 255, 0),    # Green
            (255, 255, 0),  # Cyan
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Yellow
        ]

        for cell in grid_result.get("cells", []):
            bbox = cell["bbox"]
            color = colors[cell["col_index"] % len(colors)]
            cv2.rectangle(
                overlay, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2
            )

        # Draw header rows in gray
        for hy1, hy2 in grid_result.get("header_rows", []):
            cv2.rectangle(
                overlay,
                (tb[0], hy1),
                (tb[2], hy2),
                (128, 128, 128),
                1,
            )

        return overlay

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1: Line Isolation
    # ─────────────────────────────────────────────────────────────────────────

    def _isolate_lines(
        self, gray: np.ndarray, w: int, h: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Uses morphological operations to isolate horizontal and vertical lines.
        More robust than Hough for scanned documents with broken/thick lines.

        Uses a multi-scale approach for vertical lines to catch both:
        - Thick table borders (long vertical lines)
        - Thin internal cell dividers (short vertical lines)
        """
        # Adaptive threshold to handle uneven lighting in scans
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 5
        )

        # Horizontal lines: multi-scale approach
        h_scales = [self.h_scale, self.h_scale * 2]
        h_mask = np.zeros_like(binary)
        for scale in h_scales:
            h_kernel_len = max(w // scale, 30)
            h_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT, (h_kernel_len, 1)
            )
            h_pass = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
            h_mask = cv2.bitwise_or(h_mask, h_pass)

        # Vertical lines: multi-scale approach
        v_scales = [self.v_scale, self.v_scale * 2, self.v_scale * 3]
        v_mask = np.zeros_like(binary)
        for scale in v_scales:
            v_kernel_len = max(h // scale, 20)
            v_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT, (1, v_kernel_len)
            )
            v_pass = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
            v_mask = cv2.bitwise_or(v_mask, v_pass)

        # Clean up noise: dilate vertically then erode to connect broken segments
        v_cleanup_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
        v_mask = cv2.dilate(v_mask, v_cleanup_kernel, iterations=1)

        return h_mask, v_mask

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Table Boundary Detection
    # ─────────────────────────────────────────────────────────────────────────

    def _find_table_boundary(
        self,
        h_mask: np.ndarray,
        v_mask: np.ndarray,
        w: int,
        h: int,
    ) -> Optional[List[int]]:
        """Finds the bounding rectangle of the table from combined line masks."""
        combined = cv2.bitwise_or(h_mask, v_mask)

        # Dilate slightly to connect nearby broken lines
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        combined = cv2.dilate(combined, dilate_kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(
            combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            # Fallback: use bounding rect of all non-zero pixels
            nz = cv2.findNonZero(combined)
            if nz is not None:
                x, y, bw, bh = cv2.boundingRect(nz)
                return [x, y, x + bw, y + bh]
            return None

        # Find the largest contour by area (should be the main table)
        # Filter: must be at least 10% of image area to be a real table
        min_area = w * h * 0.05
        valid_contours = [c for c in contours if cv2.contourArea(c) > min_area]

        if not valid_contours:
            # Fallback: use bounding rect of all contours combined
            all_points = np.vstack(contours)
            x, y, bw, bh = cv2.boundingRect(all_points)
            if bw > w * 0.2 and bh > h * 0.05:  # Sanity check
                return [x, y, x + bw, y + bh]
            return None

        largest = max(valid_contours, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(largest)
        return [x, y, x + bw, y + bh]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3 & 4: Axis Segmentation (shared logic for rows and columns)
    # ─────────────────────────────────────────────────────────────────────────

    def _segment_axis(
        self,
        mask: np.ndarray,
        axis: str,
        length: int,
    ) -> List[int]:
        """
        Projects a line mask onto an axis and finds boundary positions.

        For horizontal lines → project onto Y-axis → row boundaries
        For vertical lines → project onto X-axis → column boundaries
        """
        if mask.size == 0:
            return []

        if axis == "horizontal":
            # Sum across each row (axis=1) to get Y-projection
            projection = np.sum(mask, axis=1).astype(np.float64)
        else:
            # Sum down each column (axis=0) to get X-projection
            projection = np.sum(mask, axis=0).astype(np.float64)

        # Normalize
        max_val = projection.max()
        if max_val == 0:
            return []
        projection = projection / max_val

        # Find peaks (positions where projection > threshold)
        threshold = 0.10  # 10% of max line presence
        peak_positions = np.where(projection > threshold)[0]

        if len(peak_positions) == 0:
            return []

        # Cluster nearby peaks
        boundaries = self._cluster_peaks(peak_positions, self.line_cluster_gap)

        return boundaries

    def _cluster_peaks(self, positions: np.ndarray, gap: int) -> List[int]:
        """Clusters nearby positions into single boundary lines."""
        if len(positions) == 0:
            return []

        clusters = []
        current_cluster = [positions[0]]

        for i in range(1, len(positions)):
            if positions[i] - positions[i - 1] <= gap:
                current_cluster.append(positions[i])
            else:
                # End of cluster — take median as the boundary position
                clusters.append(int(np.median(current_cluster)))
                current_cluster = [positions[i]]

        # Don't forget the last cluster
        clusters.append(int(np.median(current_cluster)))

        return clusters

    def _boundaries_to_ranges(
        self, boundaries: List[int], offset: int, min_size: int
    ) -> List[Tuple[int, int]]:
        """
        Converts boundary positions to (start, end) ranges.
        Filters out ranges smaller than min_size.

        Args:
            boundaries: List of boundary positions (local to table crop)
            offset: Offset to convert to absolute image coordinates
            min_size: Minimum range size in pixels
        """
        ranges = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i] + offset
            end = boundaries[i + 1] + offset
            if (end - start) >= min_size:
                ranges.append((start, end))
        return ranges

    def _ensure_edge_boundaries(
        self, boundaries: List[int], edge_start: int, edge_end: int
    ) -> List[int]:
        """
        Ensures the start and end edges of the table are included
        as boundary positions. If the first boundary is far from edge_start
        or the last is far from edge_end, adds them.
        """
        tolerance = 15  # pixels

        result = list(boundaries)

        # Add start edge if not already present
        if not result or result[0] > edge_start + tolerance:
            result.insert(0, edge_start)

        # Add end edge if not already present
        if not result or result[-1] < edge_end - tolerance:
            result.append(edge_end)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 5: Column Classification & Header Detection
    # ─────────────────────────────────────────────────────────────────────────

    def _identify_question_column(
        self, columns: List[Tuple[int, int]]
    ) -> Tuple[int, List[Tuple[int, int]]]:
        """
        Identifies which column is the question/text column (usually the widest)
        and returns the remaining option columns.

        Returns:
            (question_col_index, list_of_option_columns)
        """
        if len(columns) < 2:
            return 0, columns

        widths = [(cx2 - cx1, idx) for idx, (cx1, cx2) in enumerate(columns)]

        # The question column is typically:
        # 1. The first or second column
        # 2. Significantly wider than option columns
        # Find the widest among the first 2 columns
        first_two = widths[:2]
        question_idx = max(first_two, key=lambda x: x[0])[1]

        # Sometimes there's a narrow "S.No." column before the question column
        # If the first column is very narrow (<15% of table width) and second is wide,
        # treat first two as non-option columns
        total_width = columns[-1][1] - columns[0][0]
        first_width = columns[0][1] - columns[0][0]
        
        non_option_indices = set()
        
        if len(columns) > 3 and first_width < total_width * 0.08:
            # Very narrow first column = S.No. column
            non_option_indices.add(0)
            non_option_indices.add(1)  # Next one is the question column
        elif len(columns) > 2:
            # Just the question column
            non_option_indices.add(question_idx)
        
        # If we haven't identified non-option columns, use a width heuristic:
        # Option columns are roughly equal width; question column is wider
        if not non_option_indices:
            median_width = np.median([w for w, _ in widths])
            for w, idx in widths:
                # If column is > 2x the median width, it's likely a question column
                if w > median_width * 1.8 and idx < 3:
                    non_option_indices.add(idx)
                    break
            if not non_option_indices:
                non_option_indices.add(0)  # Default: first column

        option_columns = [
            columns[i] for i in range(len(columns))
            if i not in non_option_indices
        ]

        return question_idx, option_columns

    def _split_header_data_rows(
        self,
        rows: List[Tuple[int, int]],
        img_bgr: np.ndarray,
        columns: List[Tuple[int, int]],
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """
        Separates header rows from data rows.

        Heuristic: Header rows are at the top and typically shorter or contain
        text in option columns (column labels). Data rows contain marks/checkboxes.

        Simple approach: If the first row is significantly shorter than the
        median row height, or if the first 1-2 rows are before the main data
        starts, classify them as headers.
        """
        if len(rows) <= 1:
            return [], rows

        # Calculate row heights
        heights = [(ry2 - ry1) for ry1, ry2 in rows]
        median_height = np.median(heights)

        header_rows = []
        data_rows = []

        for i, (ry1, ry2) in enumerate(rows):
            row_height = ry2 - ry1
            if i < 2 and row_height < median_height * 0.6:
                # Short row at the top → likely a header
                header_rows.append((ry1, ry2))
            elif i == 0 and len(rows) > 3:
                # If many rows, first row is typically a header regardless of size
                # Check if first row has much text in option columns (header labels)
                # Simple heuristic: check pixel density in option columns of first row
                option_cols = [c for c in columns[1:]] if len(columns) > 1 else []
                if option_cols and self._row_has_text_in_options(
                    img_bgr, ry1, ry2, option_cols
                ):
                    header_rows.append((ry1, ry2))
                else:
                    data_rows.append((ry1, ry2))
            else:
                data_rows.append((ry1, ry2))

        # If we have no data rows, treat everything as data
        if not data_rows:
            return [], rows

        return header_rows, data_rows

    def _row_has_text_in_options(
        self,
        img_bgr: np.ndarray,
        ry1: int,
        ry2: int,
        option_cols: List[Tuple[int, int]],
    ) -> bool:
        """
        Checks if a row has significant text content in option columns.
        Header rows have labels (high density), data rows have marks (low/medium density).
        """
        total_density = 0.0
        for cx1, cx2 in option_cols:
            crop = img_bgr[ry1:ry2, cx1:cx2]
            if crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            density = np.count_nonzero(thresh) / float(thresh.size)
            total_density += density

        avg_density = total_density / max(len(option_cols), 1)
        # Header rows typically have >20% density (text labels)
        # Data rows with checkmarks have <15% in most cells
        return avg_density > 0.18


def get_grid_detector() -> GridDetector:
    return GridDetector()
