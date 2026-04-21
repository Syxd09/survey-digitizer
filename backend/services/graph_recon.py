"""
Hydra v12.5 — Graph-Based Layout Reconstruction
=================================================
Column-aware, document-type-aware layout intelligence.
Uses NetworkX for spatial relationship mapping.

Supports:
- Row extraction (horizontal alignment)
- Column detection (vertical alignment clustering)
- Key-value linking (for forms)
- Document-type-aware extraction strategies
"""

import networkx as nx
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class LayoutGraph:
    def __init__(self):
        self.G = nx.DiGraph()
        self.regions = []
        self.doc_type = "general"

    def build_graph(
        self,
        regions: List[Dict],
        doc_type: str = "general",
    ) -> nx.DiGraph:
        """
        Build a spatial relationship graph from OCR regions.
        Edges encode: horizontal alignment, vertical alignment, proximity.
        """
        self.G.clear()
        self.regions = regions
        self.doc_type = doc_type

        if not regions:
            return self.G

        for i, r in enumerate(regions):
            self.G.add_node(i, **r)

        # Build edges based on spatial relationships
        for i in range(len(regions)):
            for j in range(len(regions)):
                if i == j:
                    continue

                ri, rj = regions[i], regions[j]

                if self._is_horizontally_aligned(ri, rj):
                    dist = abs(rj["bbox"][0] - ri["bbox"][2])  # gap between boxes
                    self.G.add_edge(i, j, type="horizontal", dist=dist)
                elif self._is_vertically_aligned(ri, rj):
                    dist = abs(rj["bbox"][1] - ri["bbox"][3])
                    self.G.add_edge(i, j, type="vertical", dist=dist)

        return self.G

    def extract_structured(self) -> List[Dict]:
        """
        Extract structured output based on document type.
        Returns list of structured entries.
        """
        if self.doc_type == "code_screenshot":
            return self._extract_code_entries()
        elif self.doc_type == "form":
            return self._extract_form_fields()
        else:
            return self._extract_rows_generic()

    def _extract_code_entries(self) -> List[Dict]:
        """
        For code screenshots (like VS Code Problems panel):
        Each row is an error entry. Detect columns:
        - Icon column (leftmost, usually 1-2 chars)
        - Message column (middle, longest text)
        - Rule column (contains Pylance/ESLint/etc)
        - Location column (contains [Ln N, Col N])
        """
        rows = self._extract_rows()
        entries = []

        for row_indices in rows:
            if not row_indices:
                continue

            row_texts = []
            for idx in row_indices:
                node = self.G.nodes[idx]
                row_texts.append({
                    "text": node["text"],
                    "bbox": node["bbox"],
                    "conf": node["conf"],
                })

            # Sort by X position
            row_texts.sort(key=lambda t: t["bbox"][0])

            # Concatenate all text in reading order
            full_text = " ".join(t["text"] for t in row_texts)
            avg_conf = np.mean([t["conf"] for t in row_texts])
            bbox = (
                min(t["bbox"][0] for t in row_texts),
                min(t["bbox"][1] for t in row_texts),
                max(t["bbox"][2] for t in row_texts),
                max(t["bbox"][3] for t in row_texts),
            )

            entries.append({
                "text": full_text,
                "bbox": bbox,
                "conf": float(avg_conf),
                "type": "code_entry",
            })

        return entries

    def _extract_form_fields(self) -> List[Dict]:
        """
        For forms: detect label-value pairs.
        Labels are typically left-aligned, values right-aligned or below.
        """
        rows = self._extract_rows()
        fields = []

        for row_indices in rows:
            row_nodes = [self.G.nodes[i] for i in row_indices]
            row_nodes.sort(key=lambda n: n["bbox"][0])

            if len(row_nodes) >= 2:
                # First element is likely the label, rest is the value
                label = row_nodes[0]["text"]
                value = " ".join(n["text"] for n in row_nodes[1:])
                fields.append({
                    "label": label,
                    "value": value,
                    "conf": float(np.mean([n["conf"] for n in row_nodes])),
                    "type": "form_field",
                })
            elif len(row_nodes) == 1:
                fields.append({
                    "text": row_nodes[0]["text"],
                    "conf": float(row_nodes[0]["conf"]),
                    "type": "text_block",
                })

        return fields

    def _extract_rows_generic(self) -> List[Dict]:
        """Generic row extraction."""
        rows = self._extract_rows()
        entries = []

        for row_indices in rows:
            row_nodes = [self.G.nodes[i] for i in row_indices]
            row_nodes.sort(key=lambda n: n["bbox"][0])

            text = " ".join(n["text"] for n in row_nodes)
            conf = float(np.mean([n["conf"] for n in row_nodes]))
            bbox = (
                min(n["bbox"][0] for n in row_nodes),
                min(n["bbox"][1] for n in row_nodes),
                max(n["bbox"][2] for n in row_nodes),
                max(n["bbox"][3] for n in row_nodes),
            )

            entries.append({
                "text": text,
                "bbox": bbox,
                "conf": conf,
                "type": "text_row",
            })

        return entries

    def _extract_rows(self) -> List[List[int]]:
        """
        Group nodes into rows by Y-coordinate clustering.
        """
        if not self.regions:
            return []

        # Cluster by Y midpoint
        nodes_by_y = []
        for i in range(len(self.regions)):
            bbox = self.regions[i]["bbox"]
            y_mid = (bbox[1] + bbox[3]) / 2
            h = bbox[3] - bbox[1]
            nodes_by_y.append((i, y_mid, h))

        # Sort by Y
        nodes_by_y.sort(key=lambda x: x[1])

        # Greedy row clustering
        rows = []
        current_row = [nodes_by_y[0][0]]
        current_y = nodes_by_y[0][1]
        current_h = nodes_by_y[0][2]

        for i, (idx, y_mid, h) in enumerate(nodes_by_y[1:]):
            # Same row if Y midpoints are close relative to text height
            threshold = max(current_h, h) * 0.5
            if abs(y_mid - current_y) < threshold:
                current_row.append(idx)
            else:
                rows.append(current_row)
                current_row = [idx]
                current_y = y_mid
                current_h = h

        if current_row:
            rows.append(current_row)

        # Sort each row by X
        for row in rows:
            row.sort(key=lambda idx: self.regions[idx]["bbox"][0])

        return rows

    def detect_columns(self) -> List[Dict]:
        """
        Detect vertical column structure by clustering X coordinates.
        """
        if not self.regions:
            return []

        x_positions = []
        for i, r in enumerate(self.regions):
            x_mid = (r["bbox"][0] + r["bbox"][2]) / 2
            x_positions.append((i, x_mid))

        # Simple column detection: cluster x_mid values
        x_positions.sort(key=lambda x: x[1])

        columns = []
        current_col = [x_positions[0]]

        for i in range(1, len(x_positions)):
            prev_x = current_col[-1][1]
            curr_x = x_positions[i][1]

            if abs(curr_x - prev_x) < 50:  # Same column threshold
                current_col.append(x_positions[i])
            else:
                columns.append(current_col)
                current_col = [x_positions[i]]

        if current_col:
            columns.append(current_col)

        return [
            {
                "x_range": (
                    min(p[1] for p in col),
                    max(p[1] for p in col),
                ),
                "node_indices": [p[0] for p in col],
            }
            for col in columns
        ]

    # ─── Spatial Relationship Methods ─────────────────────────────────────

    def _is_horizontally_aligned(self, r1: Dict, r2: Dict) -> bool:
        """Two boxes on the same virtual line."""
        y1_mid = (r1["bbox"][1] + r1["bbox"][3]) / 2
        y2_mid = (r2["bbox"][1] + r2["bbox"][3]) / 2
        h1 = r1["bbox"][3] - r1["bbox"][1]
        h2 = r2["bbox"][3] - r2["bbox"][1]
        threshold = max(h1, h2) * 0.5
        return abs(y1_mid - y2_mid) < threshold

    def _is_vertically_aligned(self, r1: Dict, r2: Dict) -> bool:
        """Two boxes in the same column."""
        x1_mid = (r1["bbox"][0] + r1["bbox"][2]) / 2
        x2_mid = (r2["bbox"][0] + r2["bbox"][2]) / 2
        w1 = r1["bbox"][2] - r1["bbox"][0]
        return abs(x1_mid - x2_mid) < (w1 * 0.4)


def get_layout_graph():
    return LayoutGraph()
