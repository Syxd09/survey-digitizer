"""
Hydra v13.0 — Document Classifier
===================================
Hardened heuristic-based document type detection.
Routes the pipeline based on OCR text signals + image features.

v13.0 improvements:
- Confidence threshold with fallback routing
- Visual-only classification fallback (when OCR fails)
- Multi-signal scoring with weighted confidence
- Handwriting detection via edge analysis
"""

import re
import cv2
import numpy as np
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ─── Document Types ──────────────────────────────────────────────────────────

DOC_TYPES = {
    "code_screenshot": {
        "description": "IDE / terminal / code editor screenshot",
        "weight": 1.0,
        "signals": [
            r"\bPylance\b", r"\bLn\s*\d+", r"\bCol\s*\d+", r"\berror\b",
            r"\bwarning\b", r"\bimport\b", r"\bdef\b", r"\bclass\b",
            r"\bsyntax\b", r"\bException\b", r"\bTraceback\b",
            r"\b\.py\b", r"\b\.js\b", r"\b\.ts\b", r"\b\.java\b",
            r"\bPROBLEMS\b", r"\bTERMINAL\b", r"\bCONSOLE\b", r"\bOUTPUT\b",
        ],
    },
    "survey_form": {
        "description": "Survey / questionnaire with table + checkmarks or circled responses",
        "weight": 1.2,  # Boost — primary use case
        "signals": [
            r"\bQuestionnaire\b", r"\bS\.?\s*No\b", r"\bQuestions?\b",
            r"\bNot\s*True\b", r"\bSomewhat\s*True\b", r"\bCertainly\s*True\b",
            r"\bStrongly\s*Agree\b", r"\bStrongly\s*Disagree\b",
            r"\bAgree\b", r"\bDisagree\b", r"\bNeutral\b",
            r"\bTrue\b", r"\bFalse\b",
            r"\bStudy\s*Code\b", r"\bForm\s*No\b",
            r"\bexperience\b", r"\bbasis\s*of\b",
            r"\binstruction\b", r"\bplease\s*read\b",
            r"\bNOTE\b", r"\bmark\s*the\b",
        ],
    },
    "form": {
        "description": "Generic form / application",
        "weight": 0.9,
        "signals": [
            r"\bName\b", r"\bAddress\b", r"\bDate\b", r"\bSignature\b",
            r"\bPhone\b", r"\bEmail\b", r"\bAge\b", r"\bGender\b",
            r"\bYes\b.*\bNo\b", r"\bcheck\b", r"\btick\b",
        ],
    },
    "invoice": {
        "description": "Invoice / receipt / financial document",
        "weight": 1.0,
        "signals": [
            r"\bTotal\b", r"\bAmount\b", r"\bInvoice\b", r"\bReceipt\b",
            r"\$\s*\d+", r"\bTax\b", r"\bSubtotal\b", r"\bQty\b",
            r"\bUnit\s*Price\b", r"\bPayment\b",
        ],
    },
    "handwritten": {
        "description": "Handwritten note / document",
        "weight": 1.0,
        "signals": [],  # Detected via image features, not text
    },
    "table": {
        "description": "Document dominated by tabular data",
        "weight": 0.8,
        "signals": [
            r"\bRow\b", r"\bColumn\b", r"\bHeader\b",
        ],
    },
    "general": {
        "description": "General text document",
        "weight": 0.5,
        "signals": [],
    },
}

# Minimum confidence to trust a classification
CONFIDENCE_THRESHOLD = 0.3
# Minimum signals needed for a confident classification
MIN_SIGNALS_FOR_CONFIDENCE = 2


class DocumentClassifier:
    """
    Classifies a document image before the pipeline runs.
    
    v13.0 hardening:
    - If confidence < threshold → fallback to "general"
    - If no OCR text → visual-only classification
    - Multi-signal weighted scoring
    """

    def classify(self, image: np.ndarray, ocr_texts: List[str]) -> Dict[str, Any]:
        """
        Classify document type from image + preliminary OCR text.

        Args:
            image: BGR numpy array
            ocr_texts: List of text strings from a fast OCR pass

        Returns:
            {
                "type": "survey_form",
                "confidence": 0.85,
                "signals_matched": [...],
                "hints": {...},
                "fallback": False,
            }
        """
        combined_text = " ".join(ocr_texts)

        # ─── Text Signal Scoring ─────────────────────────────────────────
        scores = {}
        matched_signals = {}

        for doc_type, config in DOC_TYPES.items():
            if not config["signals"]:
                scores[doc_type] = 0.0
                matched_signals[doc_type] = []
                continue

            matches = []
            for pattern in config["signals"]:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    matches.append(pattern)

            # Weighted score
            raw_score = len(matches) / len(config["signals"]) if config["signals"] else 0
            weight = config.get("weight", 1.0)
            scores[doc_type] = raw_score * weight
            matched_signals[doc_type] = matches

        # ─── Image Feature Analysis ──────────────────────────────────────
        hints = self._analyze_image_features(image)

        # Handwriting boost from image features
        if hints.get("handwriting_density", 0) > 0.15:
            scores["handwritten"] = max(scores.get("handwritten", 0), 0.7)

        # Table boost from detected grid lines
        if hints.get("has_table_lines", False):
            scores["table"] = max(scores.get("table", 0), 0.5)
            # Survey forms have table lines + survey signals
            if scores.get("survey_form", 0) > 0:
                scores["survey_form"] = max(scores["survey_form"] * 1.5, 0.65)

        # Dark background boost for code screenshots
        if hints.get("has_dark_bg", False):
            scores["code_screenshot"] = scores.get("code_screenshot", 0) * 1.5

        # ─── Visual-Only Fallback ────────────────────────────────────────
        # If OCR produced no useful text, rely on image features only
        if not ocr_texts or all(len(t.strip()) < 2 for t in ocr_texts):
            logger.warning("[CLASSIFIER] No OCR text available — using visual-only classification")
            return self._classify_visual_only(image, hints)

        # ─── Decision ────────────────────────────────────────────────────
        if not any(s > 0 for s in scores.values()):
            best_type = "general"
            confidence = 0.3
        else:
            best_type = max(scores, key=scores.get)
            confidence = min(scores[best_type], 1.0)

        # ─── Confidence Safety Check ─────────────────────────────────────
        fallback = False
        original_type = None
        matched_count = len(matched_signals.get(best_type, []))

        if confidence < CONFIDENCE_THRESHOLD and best_type != "general":
            logger.warning(
                f"[CLASSIFIER] Low confidence ({confidence:.2f}) for '{best_type}' — "
                f"only {matched_count} signals matched. Falling back to 'general'."
            )
            original_type = best_type
            best_type = "general"
            fallback = True

        elif matched_count < MIN_SIGNALS_FOR_CONFIDENCE and best_type not in ("general", "handwritten"):
            # Not enough signals — reduce confidence
            confidence *= 0.7
            logger.info(
                f"[CLASSIFIER] Only {matched_count} signals for '{best_type}' — "
                f"reducing confidence to {confidence:.2f}"
            )

        result = {
            "type": best_type,
            "confidence": round(confidence, 3),
            "signals_matched": matched_signals.get(best_type, []),
            "hints": hints,
            "all_scores": {k: round(v, 3) for k, v in scores.items()},
            "fallback": fallback,
        }

        if original_type:
            result["original_type"] = original_type

        logger.info(
            f"[CLASSIFIER] Document type: {best_type} "
            f"(confidence={confidence:.2f}, signals={matched_count})"
        )
        return result

    def _classify_visual_only(
        self, image: np.ndarray, hints: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Visual-only classification when OCR text is unavailable.
        Uses image features: dark background, table lines, edge density.
        """
        if hints is None:
            hints = self._analyze_image_features(image)

        # Decision tree based on visual features
        if hints.get("has_dark_bg", False):
            doc_type = "code_screenshot"
            confidence = 0.6
        elif hints.get("has_table_lines", False):
            # Could be survey or generic table
            doc_type = "table"
            confidence = 0.5
        elif hints.get("handwriting_density", 0) > 0.15:
            doc_type = "handwritten"
            confidence = 0.6
        else:
            doc_type = "general"
            confidence = 0.3

        logger.info(
            f"[CLASSIFIER] Visual-only: {doc_type} (confidence={confidence:.2f})"
        )

        return {
            "type": doc_type,
            "confidence": round(confidence, 3),
            "signals_matched": [],
            "hints": hints,
            "all_scores": {},
            "fallback": True,
            "visual_only": True,
        }

    def _analyze_image_features(self, img: np.ndarray) -> Dict[str, Any]:
        """Extract structural features from the image."""
        hints = {}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        # Dark background detection
        hints["has_dark_bg"] = float(np.mean(gray)) < 80

        # Edge density (high = handwriting)
        edges = cv2.Canny(gray, 50, 150)
        hints["handwriting_density"] = round(float(np.mean(edges > 0)), 4)

        # Table line detection via Hough
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=100, maxLineGap=10)
        if lines is not None:
            horizontal = sum(1 for l in lines if abs(l[0][1] - l[0][3]) < 5)
            vertical = sum(1 for l in lines if abs(l[0][0] - l[0][2]) < 5)
            hints["has_table_lines"] = horizontal >= 3 and vertical >= 2
            hints["h_lines"] = horizontal
            hints["v_lines"] = vertical
        else:
            hints["has_table_lines"] = False

        return hints


def get_classifier():
    return DocumentClassifier()
