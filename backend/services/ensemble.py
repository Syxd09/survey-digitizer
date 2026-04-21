"""
Hydra v12.5 — Ensemble Voting Engine
=====================================
Real character-level consensus using Levenshtein alignment.
Strategy:
  1. EasyOCR line-level reads become the SCAFFOLD
  2. Tesseract word-level reads PATCH garbled substrings via fuzzy matching
  3. PaddleOCR line-level reads cross-validate
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter
from rapidfuzz import fuzz, process as rfprocess

logger = logging.getLogger(__name__)


class EnsembleVoter:
    def __init__(self):
        self.iom_threshold = 0.35  # Intersection over Min Area

    def consolidate(
        self,
        paddle_res: List[Dict],
        easy_res: List[Dict],
        tess_res: List[Dict],
    ) -> List[Dict]:
        """
        Multi-engine consolidation using scaffold + patch strategy.

        1. Build line-level scaffolds from EasyOCR (longest reads)
        2. For each scaffold, find overlapping Tesseract words and patch errors
        3. Cross-validate with PaddleOCR if available
        """
        if not easy_res and not paddle_res and not tess_res:
            return []

        # ── Step 1: Build scaffolds from line-level engines ──────────────
        # EasyOCR and Paddle produce line-level reads; Tesseract is word-level
        line_engines = []
        for r in easy_res:
            line_engines.append({**r, "engine": "easy"})
        for r in paddle_res:
            line_engines.append({**r, "engine": "paddle"})

        word_engines = []
        for r in tess_res:
            word_engines.append({**r, "engine": "tesseract"})

        # If no line-level engines, reconstruct lines from Tesseract words
        if not line_engines:
            line_engines = self._reconstruct_lines_from_words(word_engines)

        # ── Step 2: Deduplicate line-level reads (EasyOCR ↔ Paddle) ──────
        scaffolds = self._deduplicate_lines(line_engines)

        # ── Step 3: Patch each scaffold with Tesseract words ─────────────
        results = []
        for scaffold in scaffolds:
            overlapping_words = self._find_overlapping_words(
                scaffold["bbox"], word_engines
            )
            patched_text, confidence = self._patch_with_words(
                scaffold["text"], scaffold["conf"], overlapping_words
            )

            results.append({
                "text": patched_text,
                "bbox": scaffold["bbox"],
                "conf": confidence,
                "engines": scaffold.get("engines", [scaffold["engine"]]),
                "raw_scaffold": scaffold["text"],
            })

        # Sort by Y then X for reading order
        results.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        return results

    # ─── Internal Methods ────────────────────────────────────────────────────

    def _deduplicate_lines(self, line_regions: List[Dict]) -> List[Dict]:
        """
        Merge line reads from different engines that cover the same region.
        When EasyOCR and Paddle both read the same line, cross-validate.
        """
        if not line_regions:
            return []

        # Sort by Y then X
        line_regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        
        merged = []
        used = set()

        for i, r in enumerate(line_regions):
            if i in used:
                continue

            group = [r]
            used.add(i)

            for j, other in enumerate(line_regions):
                if j in used:
                    continue
                if self._calculate_iom(r["bbox"], other["bbox"]) > self.iom_threshold:
                    group.append(other)
                    used.add(j)

            # Cross-validate group
            if len(group) == 1:
                merged.append(group[0])
            else:
                best = self._cross_validate_group(group)
                merged.append(best)

        return merged

    def _cross_validate_group(self, group: List[Dict]) -> Dict:
        """
        When multiple engines read the same region, pick the best.
        Priority: highest confidence × longest text.
        """
        # Score each candidate
        scored = []
        for r in group:
            # Penalize very short reads (likely truncated)
            length_score = min(len(r["text"]) / 20.0, 1.0)
            conf_score = r["conf"]
            scored.append((r, length_score * 0.4 + conf_score * 0.6))

        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]
        best["engines"] = [r["engine"] for r in group]
        best["conf"] = max(r["conf"] for r in group)
        return best

    def _find_overlapping_words(
        self, line_bbox: Tuple, words: List[Dict]
    ) -> List[Dict]:
        """
        Find Tesseract words that spatially overlap with a line scaffold.
        Uses vertical overlap (Y-axis) as primary criterion.
        """
        lx1, ly1, lx2, ly2 = line_bbox
        line_h = ly2 - ly1
        overlapping = []

        for w in words:
            wx1, wy1, wx2, wy2 = w["bbox"]

            # Vertical overlap check
            y_overlap = max(0, min(ly2, wy2) - max(ly1, wy1))
            if y_overlap < line_h * 0.3:
                continue

            # Horizontal containment: word must be within line's x-range (with margin)
            margin = line_h  # Allow some margin
            if wx1 >= lx1 - margin and wx2 <= lx2 + margin:
                overlapping.append(w)

        # Sort by X coordinate (left to right)
        overlapping.sort(key=lambda w: w["bbox"][0])
        return overlapping

    def _patch_with_words(
        self,
        scaffold_text: str,
        scaffold_conf: float,
        words: List[Dict],
    ) -> Tuple[str, float]:
        """
        Use Tesseract's high-confidence individual words to fix garbled
        substrings in the EasyOCR scaffold.

        Strategy:
        1. Split scaffold into tokens
        2. For each token, find the best matching Tesseract word
        3. If Tesseract word is high-confidence and similar, replace
        """
        if not words or not scaffold_text:
            return scaffold_text, scaffold_conf

        # Build Tesseract word pool (only high-confidence words)
        word_pool = {
            w["text"]: w["conf"]
            for w in words
            if w["conf"] > 0.6 and len(w["text"].strip()) > 0
        }

        if not word_pool:
            return scaffold_text, scaffold_conf

        # Try to reconstruct the full line from Tesseract words
        tess_reconstruction = " ".join(
            w["text"] for w in words if w["conf"] > 0.5 and len(w["text"].strip()) > 0
        )

        # Compare scaffold vs Tesseract reconstruction
        scaffold_score = fuzz.ratio(scaffold_text, tess_reconstruction)

        # If Tesseract reconstruction is very similar and longer, prefer it
        if scaffold_score > 80 and len(tess_reconstruction) >= len(scaffold_text) * 0.8:
            # Token-level patching: check each scaffold token
            patched_tokens = []
            scaffold_tokens = scaffold_text.split()
            tess_word_list = list(word_pool.keys())

            for s_token in scaffold_tokens:
                if len(s_token) <= 1:
                    patched_tokens.append(s_token)
                    continue

                # Find best fuzzy match in Tesseract words
                match = rfprocess.extractOne(
                    s_token, tess_word_list, scorer=fuzz.ratio, score_cutoff=60
                )

                if match:
                    matched_word, score, _ = match
                    tess_conf = word_pool[matched_word]

                    # Replace if: Tesseract word is high-confidence AND
                    # the scaffold token looks garbled (long concatenated string)
                    is_garbled = len(s_token) > 15 and not any(
                        c in s_token for c in " .,"
                    )
                    is_better = tess_conf > 0.85 and score < 95

                    if is_garbled or (is_better and score > 70):
                        patched_tokens.append(matched_word)
                    else:
                        patched_tokens.append(s_token)
                else:
                    patched_tokens.append(s_token)

            patched = " ".join(patched_tokens)
        else:
            patched = scaffold_text

        # ── Handle garbled concatenated substrings ───────────────────────
        # E.g. "PylancereporUndetinedvarable" → find words inside it
        patched = self._degarble_concatenations(patched, word_pool)

        avg_conf = np.mean(
            [scaffold_conf] + [w["conf"] for w in words if w["conf"] > 0.5]
        )
        return patched, float(avg_conf)

    def _degarble_concatenations(
        self, text: str, word_pool: Dict[str, float]
    ) -> str:
        """
        Find and break apart garbled concatenated substrings.
        E.g. "PylancereporUndetinedvarable" → multiple words were smashed together
        """
        tokens = text.split()
        result = []

        for token in tokens:
            if len(token) > 20:
                # This looks like concatenated garbage — try to break it apart
                # using known high-confidence Tesseract words
                broken = self._break_concatenation(token, word_pool)
                result.append(broken)
            else:
                result.append(token)

        return " ".join(result)

    def _break_concatenation(
        self, garbled: str, word_pool: Dict[str, float]
    ) -> str:
        """
        Try to decompose a garbled string into known words.
        Greedy left-to-right matching.
        """
        # Sort word pool by length (longest first for greedy matching)
        known_words = sorted(word_pool.keys(), key=len, reverse=True)
        remaining = garbled
        parts = []

        while remaining and len(remaining) > 2:
            best_match = None
            best_pos = -1
            best_len = 0

            for word in known_words:
                if len(word) < 3:
                    continue
                # Fuzzy substring search
                pos = remaining.lower().find(word.lower()[:3])
                if pos >= 0:
                    # Check if more of the word matches
                    end = min(pos + len(word) + 3, len(remaining))
                    substr = remaining[pos:end]
                    score = fuzz.partial_ratio(word, substr)
                    if score > 75 and len(word) > best_len:
                        best_match = word
                        best_pos = pos
                        best_len = len(word)

            if best_match and best_pos >= 0:
                # Add any prefix before the match
                if best_pos > 0:
                    parts.append(remaining[:best_pos])
                parts.append(best_match)
                remaining = remaining[best_pos + best_len:]
            else:
                parts.append(remaining)
                break

        if remaining and remaining not in parts:
            parts.append(remaining)

        return " ".join(p for p in parts if p.strip())

    def _reconstruct_lines_from_words(
        self, words: List[Dict]
    ) -> List[Dict]:
        """
        If no line-level engine is available, group Tesseract words into lines
        based on vertical proximity.
        """
        if not words:
            return []

        words_sorted = sorted(words, key=lambda w: (w["bbox"][1], w["bbox"][0]))
        lines = []
        current_line = [words_sorted[0]]

        for w in words_sorted[1:]:
            prev = current_line[-1]
            prev_y_mid = (prev["bbox"][1] + prev["bbox"][3]) / 2
            curr_y_mid = (w["bbox"][1] + w["bbox"][3]) / 2
            prev_h = prev["bbox"][3] - prev["bbox"][1]

            if abs(curr_y_mid - prev_y_mid) < prev_h * 0.6:
                current_line.append(w)
            else:
                lines.append(current_line)
                current_line = [w]

        if current_line:
            lines.append(current_line)

        # Convert word groups to line dicts
        result = []
        for line_words in lines:
            text = " ".join(w["text"] for w in line_words)
            bbox = (
                min(w["bbox"][0] for w in line_words),
                min(w["bbox"][1] for w in line_words),
                max(w["bbox"][2] for w in line_words),
                max(w["bbox"][3] for w in line_words),
            )
            conf = np.mean([w["conf"] for w in line_words])
            result.append({
                "text": text,
                "bbox": bbox,
                "conf": float(conf),
                "engine": "tesseract_reconstructed",
            })

        return result

    @staticmethod
    def _calculate_iom(boxA: Tuple, boxB: Tuple) -> float:
        """Intersection over Min Area."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        inter = max(0, xB - xA) * max(0, yB - yA)

        areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        min_area = min(areaA, areaB)

        if min_area == 0:
            return 0.0
        return inter / float(min_area)


def get_voter():
    return EnsembleVoter()
