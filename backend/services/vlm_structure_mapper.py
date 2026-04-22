"""
Hydra v13.0 — VLM Structure Mapper
====================================
THE critical module that reverses the pipeline:

    OLD: OCR → structure → VLM decorates
    NEW: VLM → structure → OCR fills values

This module takes:
  1. VLM skeleton (structure, fields, table info)
  2. OCR ensemble regions (bbox + text + confidence)

And produces:
  - Structured entries where VLM defines WHAT exists
  - OCR provides the EXACT text for each slot

Matching strategies:
  - Spatial alignment: OCR bboxes map to VLM field positions
  - Fuzzy label matching: VLM field labels fuzzy-match against OCR text
  - Row reconstruction: for tables, OCR text in each row is grouped by column
"""

import hashlib
import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from rapidfuzz import fuzz, process as rfprocess

logger = logging.getLogger(__name__)


class VLMStructureMapper:
    """
    Maps OCR text INTO VLM-defined document structure.
    VLM is the authority for WHAT fields exist.
    OCR is the authority for WHAT the text says.
    """

    # Minimum fuzzy match score to consider OCR text as matching a VLM field
    LABEL_MATCH_THRESHOLD = 55
    # Minimum fuzzy match score for high-confidence label match
    HIGH_CONFIDENCE_THRESHOLD = 80

    def map_ocr_to_structure(
        self,
        vlm_skeleton: Dict[str, Any],
        ocr_regions: List[Dict],
        doc_type: str,
    ) -> List[Dict]:
        """
        Map OCR ensemble regions into VLM-defined structure.

        Returns list of structured entries:
        [
            {
                "question": "VLM-defined label",
                "selected": "OCR-derived text",
                "confidence": 0.85,
                "source": "vlm+ocr",
                "vlm_label": "Q1",
                "vlm_answer": "Not True",        # VLM's guess
                "ocr_text": "Not True",           # OCR's reading
                "agreement": True,                # VLM and OCR agree
            }
        ]
        """
        if not vlm_skeleton or vlm_skeleton.get("status") != "ok":
            # VLM failed → fall back to OCR-only
            return self._ocr_only_fallback(ocr_regions, doc_type)

        vlm_fields = vlm_skeleton.get("fields", [])
        vlm_table = vlm_skeleton.get("table")

        if not vlm_fields and not vlm_table:
            return self._ocr_only_fallback(ocr_regions, doc_type)

        # ── Strategy selection based on document type ────────────────────
        if doc_type == "survey_form" and vlm_table:
            return self._map_survey_form(vlm_skeleton, ocr_regions)
        elif doc_type == "form":
            return self._map_form(vlm_fields, ocr_regions)
        elif doc_type == "invoice":
            return self._map_invoice(vlm_fields, vlm_table, ocr_regions)
        elif doc_type == "code_screenshot":
            return self._map_code_screenshot(vlm_fields, ocr_regions)
        else:
            return self._map_generic(vlm_fields, ocr_regions)

    # ═══════════════════════════════════════════════════════════════════════
    # Document-Type-Specific Mapping Strategies
    # ═══════════════════════════════════════════════════════════════════════

    def _map_survey_form(
        self,
        vlm_skeleton: Dict,
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """
        Survey form mapping:
        VLM defines the questions + expected column structure.
        OCR provides the exact text for each question and its answer.
        """
        vlm_fields = vlm_skeleton.get("fields", [])
        vlm_table = vlm_skeleton.get("table", {})
        columns = vlm_table.get("columns", []) if vlm_table else []

        entries = []
        used_ocr_indices = set()

        for field in vlm_fields:
            vlm_label = field.get("label", "")
            vlm_text = field.get("text", "")
            vlm_answer = field.get("vlm_answer")

            # Find the OCR region(s) that best match this question's text
            best_match, best_score, best_idx = self._find_best_ocr_match(
                vlm_text, ocr_regions, used_ocr_indices
            )

            if best_match and best_score > self.LABEL_MATCH_THRESHOLD:
                used_ocr_indices.add(best_idx)
                ocr_text = best_match["text"]
                ocr_conf = best_match.get("conf", 0.5)

                # Determine selected answer
                selected = vlm_answer if vlm_answer else self._infer_selection(
                    best_match, ocr_regions, columns, used_ocr_indices
                )

                # Agreement check
                agreement = (
                    vlm_answer and selected and
                    fuzz.ratio(vlm_answer.lower(), selected.lower()) > 70
                )

                entries.append({
                    "question": f"{vlm_label}. {ocr_text}" if vlm_label.startswith("Q") else ocr_text,
                    "selected": selected or "[UNMARKED]",
                    "confidence": round(self._compute_confidence(
                        ocr_conf, best_score, agreement
                    ), 4),
                    "source": "vlm+ocr",
                    "vlm_label": vlm_label,
                    "vlm_answer": vlm_answer,
                    "ocr_text": ocr_text,
                    "agreement": agreement,
                    "status": "✅ OK" if agreement or (ocr_conf > 0.7) else "⚠️ Review",
                    "imageHash": hashlib.md5(f"{vlm_label}_{vlm_text}".encode()).hexdigest()
                })
            else:
                # VLM says this field exists, but OCR couldn't find matching text
                entries.append({
                    "question": f"{vlm_label}. {vlm_text}",
                    "selected": vlm_answer or "[NOT_FOUND]",
                    "confidence": 0.3,
                    "source": "vlm_only",
                    "vlm_label": vlm_label,
                    "vlm_answer": vlm_answer,
                    "ocr_text": None,
                    "agreement": False,
                    "status": "⚠️ VLM-only",
                    "imageHash": hashlib.md5(f"vlm_{vlm_label}_{vlm_text}".encode()).hexdigest()
                })

        # ── Collect orphan OCR regions (OCR found text VLM didn't define) ──
        orphans = self._collect_orphans(ocr_regions, used_ocr_indices)
        for orphan in orphans:
            entries.append({
                "question": f"[Unmapped] {orphan['text'][:50]}",
                "selected": orphan["text"],
                "confidence": round(orphan.get("conf", 0.4), 4),
                "source": "ocr_only",
                "vlm_label": None,
                "vlm_answer": None,
                "ocr_text": orphan["text"],
                "agreement": False,
                "status": "ℹ️ OCR-only",
            })

        return entries

    def _map_form(
        self,
        vlm_fields: List[Dict],
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """Map form fields: VLM defines labels, OCR provides values."""
        entries = []
        used_indices = set()

        for field in vlm_fields:
            label = field.get("label", field.get("text", ""))
            vlm_value = field.get("vlm_answer", field.get("text", ""))

            # Find OCR region matching this label
            match, score, idx = self._find_best_ocr_match(
                label, ocr_regions, used_indices
            )

            if match and score > self.LABEL_MATCH_THRESHOLD:
                used_indices.add(idx)
                # The value is typically in a nearby OCR region (to the right or below)
                value_region = self._find_adjacent_value(
                    match, ocr_regions, used_indices
                )
                ocr_value = value_region["text"] if value_region else vlm_value
                if value_region:
                    used_indices.add(ocr_regions.index(value_region))

                entries.append({
                    "question": label,
                    "selected": ocr_value,
                    "confidence": round(match.get("conf", 0.5), 4),
                    "source": "vlm+ocr",
                    "vlm_label": label,
                    "vlm_answer": vlm_value,
                    "ocr_text": ocr_value,
                    "agreement": fuzz.ratio(
                        str(vlm_value).lower(), str(ocr_value).lower()
                    ) > 70 if vlm_value and ocr_value else False,
                    "status": "✅ OK",
                    "imageHash": hashlib.md5(f"form_{label}".encode()).hexdigest()
                })
            else:
                entries.append({
                    "question": label,
                    "selected": vlm_value or "[NOT_FOUND]",
                    "confidence": 0.3,
                    "source": "vlm_only",
                    "vlm_label": label,
                    "vlm_answer": vlm_value,
                    "ocr_text": None,
                    "agreement": False,
                    "status": "⚠️ VLM-only",
                })

        # ── Collect orphan OCR regions not matched to any VLM field ───────
        orphans = self._collect_orphans(ocr_regions, used_indices)
        for orphan in orphans:
            entries.append({
                "question": f"[Detected] {orphan['text'][:60]}",
                "selected": orphan["text"],
                "confidence": round(orphan.get("conf", 0.4), 4),
                "source": "ocr_only",
                "vlm_label": None,
                "vlm_answer": None,
                "ocr_text": orphan["text"],
                "agreement": False,
                "status": "ℹ️ OCR-only",
                "imageHash": hashlib.md5(f"form_orphan_{orphan['text'][:20]}".encode()).hexdigest()
            })

        return entries

    def _map_invoice(
        self,
        vlm_fields: List[Dict],
        vlm_table: Optional[Dict],
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """Map invoice: header fields + line items."""
        # Re-use form mapping for header fields
        entries = self._map_form(vlm_fields, ocr_regions)

        # Mark financial fields for cross-validation
        for entry in entries:
            label_lower = entry["question"].lower()
            if any(kw in label_lower for kw in ("total", "subtotal", "tax", "amount")):
                entry["field_type"] = "financial"

        return entries

    def _map_code_screenshot(
        self,
        vlm_fields: List[Dict],
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """Map code errors: VLM defines error entries, OCR provides exact text."""
        entries = []
        used_indices = set()

        for field in vlm_fields:
            text = field.get("text", "")
            match, score, idx = self._find_best_ocr_match(
                text, ocr_regions, used_indices
            )

            if match and score > self.LABEL_MATCH_THRESHOLD:
                used_indices.add(idx)
                entries.append({
                    "question": field.get("label", "Error"),
                    "selected": match["text"],
                    "confidence": round(match.get("conf", 0.5), 4),
                    "source": "vlm+ocr",
                    "vlm_label": field.get("label"),
                    "vlm_answer": text,
                    "ocr_text": match["text"],
                    "agreement": score > self.HIGH_CONFIDENCE_THRESHOLD,
                    "status": "✅ OK" if score > self.HIGH_CONFIDENCE_THRESHOLD else "⚠️ Review",
                })
            else:
                entries.append({
                    "question": field.get("label", "Error"),
                    "selected": text,
                    "confidence": 0.3,
                    "source": "vlm_only",
                    "vlm_label": field.get("label"),
                    "vlm_answer": text,
                    "ocr_text": None,
                    "agreement": False,
                    "status": "⚠️ VLM-only",
                })

        return entries

    def _map_generic(
        self,
        vlm_fields: List[Dict],
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """
        Universal document mapper — handles any document type.
        
        Strategy:
          1. If VLM produced meaningful fields, map OCR into them (form-style)
          2. Always collect orphan OCR regions
          3. When VLM is weak (few fields vs many OCR regions), switch to
             OCR-primary mode with smart spatial grouping
        """
        vlm_field_count = len(vlm_fields)
        ocr_region_count = len(ocr_regions)

        # ── Detect weak VLM: too few fields vs OCR regions ───────────────
        vlm_is_weak = (
            vlm_field_count < max(3, ocr_region_count * 0.3)
        )

        if vlm_is_weak and ocr_region_count > 0:
            logger.info(
                f"[MAPPER] VLM weak ({vlm_field_count} fields vs {ocr_region_count} OCR regions) "
                f"— switching to OCR-primary mode with smart grouping"
            )
            return self._ocr_primary_with_vlm_hints(vlm_fields, ocr_regions)

        # ── Normal VLM-driven mapping (with orphan collection) ───────────
        return self._map_form(vlm_fields, ocr_regions)

    def _ocr_primary_with_vlm_hints(
        self,
        vlm_fields: List[Dict],
        ocr_regions: List[Dict],
    ) -> List[Dict]:
        """
        OCR-primary extraction enriched with VLM hints.
        Used when VLM is too weak to be the sole authority.
        
        Groups OCR regions into logical entries using spatial proximity,
        detects label:value pairs, and annotates with any VLM matches.
        """
        entries = []
        used_indices = set()

        # ── Phase 1: Match whatever VLM fields exist ─────────────────────
        for field in vlm_fields:
            label = field.get("label", field.get("text", ""))
            vlm_value = field.get("vlm_answer", field.get("text", ""))

            match, score, idx = self._find_best_ocr_match(
                label, ocr_regions, used_indices
            )

            if match and score > self.LABEL_MATCH_THRESHOLD:
                used_indices.add(idx)
                value_region = self._find_adjacent_value(
                    match, ocr_regions, used_indices
                )
                ocr_value = value_region["text"] if value_region else vlm_value
                if value_region:
                    try:
                        vi = ocr_regions.index(value_region)
                        used_indices.add(vi)
                    except ValueError:
                        pass

                entries.append({
                    "question": label,
                    "selected": ocr_value,
                    "confidence": round(match.get("conf", 0.5), 4),
                    "source": "vlm+ocr",
                    "vlm_label": label,
                    "vlm_answer": vlm_value,
                    "ocr_text": ocr_value,
                    "agreement": fuzz.ratio(
                        str(vlm_value).lower(), str(ocr_value).lower()
                    ) > 70 if vlm_value and ocr_value else False,
                    "status": "✅ OK",
                    "imageHash": hashlib.md5(f"generic_{label}".encode()).hexdigest()
                })

        # ── Phase 2: Smart grouping of remaining OCR regions ─────────────
        remaining = [
            (i, r) for i, r in enumerate(ocr_regions)
            if i not in used_indices
        ]

        if not remaining:
            return entries

        # Sort by reading order (top-to-bottom, left-to-right)
        remaining.sort(key=lambda x: (x[1].get("bbox", (0, 0, 0, 0))[1], x[1].get("bbox", (0, 0, 0, 0))[0]))

        # Group into lines by vertical proximity
        lines = self._group_into_lines(remaining)

        # Detect label:value pairs within each line
        for line_group in lines:
            line_entries = self._detect_label_value_pairs(line_group)
            entries.extend(line_entries)

        return entries

    def _group_into_lines(
        self,
        indexed_regions: List[Tuple[int, Dict]],
    ) -> List[List[Tuple[int, Dict]]]:
        """
        Group OCR regions into lines based on vertical proximity.
        Regions on the same horizontal band become one line group.
        """
        if not indexed_regions:
            return []

        lines = []
        current_line = [indexed_regions[0]]

        for idx_region in indexed_regions[1:]:
            _, region = idx_region
            _, prev_region = current_line[-1]

            prev_bbox = prev_region.get("bbox", (0, 0, 0, 0))
            curr_bbox = region.get("bbox", (0, 0, 0, 0))

            prev_y_mid = (prev_bbox[1] + prev_bbox[3]) / 2
            curr_y_mid = (curr_bbox[1] + curr_bbox[3]) / 2
            prev_h = max(prev_bbox[3] - prev_bbox[1], 1)

            # Same line if vertical midpoints are within 60% of line height
            if abs(curr_y_mid - prev_y_mid) < prev_h * 0.6:
                current_line.append(idx_region)
            else:
                lines.append(current_line)
                current_line = [idx_region]

        if current_line:
            lines.append(current_line)

        return lines

    def _detect_label_value_pairs(
        self,
        line_group: List[Tuple[int, Dict]],
    ) -> List[Dict]:
        """
        Within a line group, detect label:value pairs.
        
        Heuristics:
          - If line has 2 regions and left one looks like a label → pair them
          - If line has 1 region, it's a standalone text entry
          - If line has 3+ regions, join them as a single text entry
        """
        entries = []

        # Sort by X within the line
        line_group.sort(key=lambda x: x[1].get("bbox", (0, 0, 0, 0))[0])

        regions = [r for _, r in line_group]
        texts = [r.get("text", "").strip() for r in regions]
        confs = [r.get("conf", 0.5) for r in regions]

        if len(regions) == 0:
            return entries

        if len(regions) == 1:
            # Single region — standalone entry
            text = texts[0]
            if len(text) < 2:
                return entries

            # Check if it contains a colon (inline label:value)
            if ":" in text and not text.endswith(":"):
                parts = text.split(":", 1)
                label = parts[0].strip()
                value = parts[1].strip()
                if label and value:
                    entries.append({
                        "question": label,
                        "selected": value,
                        "confidence": round(confs[0], 4),
                        "source": "ocr_structured",
                        "vlm_label": None,
                        "vlm_answer": None,
                        "ocr_text": text,
                        "agreement": False,
                        "status": "✅ OK",
                        "imageHash": hashlib.md5(f"ocr_kv_{label}".encode()).hexdigest()
                    })
                    return entries

            entries.append({
                "question": self._infer_field_label(text),
                "selected": text,
                "confidence": round(confs[0], 4),
                "source": "ocr_detected",
                "vlm_label": None,
                "vlm_answer": None,
                "ocr_text": text,
                "agreement": False,
                "status": "ℹ️ OCR-detected",
                "imageHash": hashlib.md5(f"ocr_{text[:30]}".encode()).hexdigest()
            })

        elif len(regions) == 2:
            left_text = texts[0]
            right_text = texts[1]

            # Heuristic: if left text looks like a label (short, ends with colon,
            # or is title-case), treat as label:value pair
            is_label = (
                len(left_text) < 40 and (
                    left_text.endswith(":") or
                    left_text.endswith("?") or
                    left_text[0].isupper() or
                    len(left_text.split()) <= 4
                )
            )

            if is_label:
                label = left_text.rstrip(":?")
                entries.append({
                    "question": label,
                    "selected": right_text,
                    "confidence": round(max(confs), 4),
                    "source": "ocr_structured",
                    "vlm_label": None,
                    "vlm_answer": None,
                    "ocr_text": f"{left_text} {right_text}",
                    "agreement": False,
                    "status": "✅ OK",
                    "imageHash": hashlib.md5(f"ocr_pair_{label}".encode()).hexdigest()
                })
            else:
                # Two standalone text blocks on same line
                combined = f"{left_text} {right_text}"
                entries.append({
                    "question": self._infer_field_label(combined),
                    "selected": combined,
                    "confidence": round(np.mean(confs), 4),
                    "source": "ocr_detected",
                    "vlm_label": None,
                    "vlm_answer": None,
                    "ocr_text": combined,
                    "agreement": False,
                    "status": "ℹ️ OCR-detected",
                    "imageHash": hashlib.md5(f"ocr_{combined[:30]}".encode()).hexdigest()
                })

        else:
            # 3+ regions — join as one text block
            combined = " ".join(t for t in texts if t)
            if len(combined.strip()) < 2:
                return entries

            # Check if first element is a label
            if len(texts[0]) < 40 and (texts[0].endswith(":") or texts[0].endswith("?")):
                label = texts[0].rstrip(":?")
                value = " ".join(texts[1:])
                entries.append({
                    "question": label,
                    "selected": value,
                    "confidence": round(np.mean(confs), 4),
                    "source": "ocr_structured",
                    "vlm_label": None,
                    "vlm_answer": None,
                    "ocr_text": combined,
                    "agreement": False,
                    "status": "✅ OK",
                    "imageHash": hashlib.md5(f"ocr_multi_{label}".encode()).hexdigest()
                })
            else:
                entries.append({
                    "question": self._infer_field_label(combined),
                    "selected": combined,
                    "confidence": round(np.mean(confs), 4),
                    "source": "ocr_detected",
                    "vlm_label": None,
                    "vlm_answer": None,
                    "ocr_text": combined,
                    "agreement": False,
                    "status": "ℹ️ OCR-detected",
                    "imageHash": hashlib.md5(f"ocr_{combined[:30]}".encode()).hexdigest()
                })

        return entries

    def _infer_field_label(self, text: str) -> str:
        """
        Generate a meaningful label for an OCR-detected text region.
        Uses content analysis to create descriptive labels.
        """
        text = text.strip()

        # If text contains a colon, use the part before it
        if ":" in text:
            before_colon = text.split(":")[0].strip()
            if 2 < len(before_colon) < 50:
                return before_colon

        # If it looks like a heading (short, title-case)
        if len(text) < 60 and text[0].isupper():
            return text[:50]

        # Use first N chars as label
        return text[:50] if len(text) > 50 else text

    # ═══════════════════════════════════════════════════════════════════════
    # Core Matching Algorithms
    # ═══════════════════════════════════════════════════════════════════════

    def _find_best_ocr_match(
        self,
        vlm_text: str,
        ocr_regions: List[Dict],
        used_indices: set,
    ) -> Tuple[Optional[Dict], float, int]:
        """
        Find the OCR region whose text best matches VLM's field text.
        Uses fuzzy matching (partial ratio for substring tolerance).
        """
        if not vlm_text or not ocr_regions:
            return None, 0.0, -1

        best_match = None
        best_score = 0.0
        best_idx = -1

        for i, region in enumerate(ocr_regions):
            if i in used_indices:
                continue

            ocr_text = region.get("text", "")
            if not ocr_text:
                continue

            # Use partial ratio — handles substring matches
            # e.g., VLM: "What is your name?" matches OCR: "your name"
            score = fuzz.partial_ratio(vlm_text.lower(), ocr_text.lower())

            # Bonus for exact ratio (full string match)
            exact_score = fuzz.ratio(vlm_text.lower(), ocr_text.lower())
            combined = score * 0.6 + exact_score * 0.4

            if combined > best_score:
                best_score = combined
                best_match = region
                best_idx = i

        return best_match, best_score, best_idx

    def _find_adjacent_value(
        self,
        label_region: Dict,
        all_regions: List[Dict],
        used_indices: set,
    ) -> Optional[Dict]:
        """
        Find the OCR region to the RIGHT of or BELOW the label.
        Forms typically have: Label [gap] Value
        """
        if "bbox" not in label_region:
            return None

        lx1, ly1, lx2, ly2 = label_region["bbox"]
        label_h = ly2 - ly1
        label_w = lx2 - lx1

        candidates = []
        for i, region in enumerate(all_regions):
            if i in used_indices or region is label_region:
                continue
            if "bbox" not in region:
                continue

            rx1, ry1, rx2, ry2 = region["bbox"]

            # Right-adjacent: same Y band, to the right
            y_overlap = max(0, min(ly2, ry2) - max(ly1, ry1))
            if y_overlap > label_h * 0.3 and rx1 > lx1:
                gap = rx1 - lx2
                if 0 <= gap < label_w * 3:
                    candidates.append((region, gap, "right"))

            # Below: similar X, below Y
            x_overlap_ratio = max(0, min(lx2, rx2) - max(lx1, rx1)) / max(label_w, 1)
            if x_overlap_ratio > 0.3 and ry1 > ly2:
                gap = ry1 - ly2
                if 0 <= gap < label_h * 3:
                    candidates.append((region, gap + 1000, "below"))

        if not candidates:
            return None

        # Prefer right-adjacent, then below, sorted by gap distance
        candidates.sort(key=lambda c: c[1])
        return candidates[0][0]

    def _infer_selection(
        self,
        question_region: Dict,
        all_regions: List[Dict],
        columns: List[str],
        used_indices: set,
    ) -> Optional[str]:
        """
        For survey forms: infer which column's answer is selected.
        Looks for marks/text to the right of the question.
        """
        if "bbox" not in question_region or not columns:
            return None

        # This is a simplified heuristic — the survey_extractor handles
        # this much better with grid analysis. Return None to let
        # the existing survey_extractor logic handle it.
        return None

    def _compute_confidence(
        self, ocr_conf: float, match_score: float, agreement: bool
    ) -> float:
        """
        Compute final confidence from multiple signals:
        - OCR engine confidence
        - Fuzzy match score (VLM ↔ OCR)
        - VLM-OCR agreement
        """
        base = ocr_conf * 0.5 + (match_score / 100.0) * 0.3
        if agreement:
            base += 0.2
        return min(base, 1.0)

    def _collect_orphans(
        self,
        ocr_regions: List[Dict],
        used_indices: set,
    ) -> List[Dict]:
        """
        Collect OCR regions that weren't mapped to any VLM field.
        These are "orphan" text blocks — OCR found them but VLM didn't define them.
        
        Filter out noise (very short text, low confidence).
        """
        orphans = []
        for i, region in enumerate(ocr_regions):
            if i in used_indices:
                continue
            text = region.get("text", "").strip()
            conf = region.get("conf", 0.0)
            # Skip noise
            if len(text) < 3 or conf < 0.3:
                continue
            orphans.append(region)
        return orphans

    def _ocr_only_fallback(
        self,
        ocr_regions: List[Dict],
        doc_type: str,
    ) -> List[Dict]:
        """
        Fallback when VLM skeleton is unavailable.
        Structure OCR regions into basic entries.
        """
        logger.warning("[MAPPER] VLM skeleton unavailable — falling back to OCR-only")
        entries = []

        # Sort by reading order (top-to-bottom, left-to-right)
        sorted_regions = sorted(
            ocr_regions,
            key=lambda r: (r.get("bbox", (0, 0, 0, 0))[1], r.get("bbox", (0, 0, 0, 0))[0])
        )

        for i, region in enumerate(sorted_regions):
            text = region.get("text", "").strip()
            if not text or len(text) < 2:
                continue
            entries.append({
                "question": f"Field {i + 1}",
                "selected": text,
                "confidence": round(region.get("conf", 0.5), 4),
                "source": "ocr_only",
                "vlm_label": None,
                "vlm_answer": None,
                "ocr_text": text,
                "agreement": False,
                "status": "ℹ️ OCR-only (no VLM)",
                "imageHash": hashlib.md5(f"ocr_{i}_{text}".encode()).hexdigest()
            })

        return entries


def get_structure_mapper():
    return VLMStructureMapper()
