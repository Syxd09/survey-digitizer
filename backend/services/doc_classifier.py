"""
Hydra v12.5 — Document Classifier
===================================
Heuristic-based document type detection.
Routes the pipeline based on OCR text signals + image features.
No ML model — pure signal analysis for zero-latency classification.
"""

import re
import cv2
import numpy as np
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# ─── Document Types ──────────────────────────────────────────────────────────

DOC_TYPES = {
    "code_screenshot": {
        "description": "IDE / terminal / code editor screenshot",
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
        "signals": [
            r"\bName\b", r"\bAddress\b", r"\bDate\b", r"\bSignature\b",
            r"\bPhone\b", r"\bEmail\b", r"\bAge\b", r"\bGender\b",
            r"\bYes\b.*\bNo\b", r"\bcheck\b", r"\btick\b",
        ],
    },
    "invoice": {
        "description": "Invoice / receipt / financial document",
        "signals": [
            r"\bTotal\b", r"\bAmount\b", r"\bInvoice\b", r"\bReceipt\b",
            r"\$\s*\d+", r"\bTax\b", r"\bSubtotal\b", r"\bQty\b",
            r"\bUnit\s*Price\b", r"\bPayment\b",
        ],
    },
    "handwritten": {
        "description": "Handwritten note / document",
        "signals": [],  # Detected via image features, not text
    },
    "table": {
        "description": "Document dominated by tabular data",
        "signals": [
            r"\bRow\b", r"\bColumn\b", r"\bHeader\b",
        ],
    },
    "general": {
        "description": "General text document",
        "signals": [],
    },
}


class DocumentClassifier:
    """
    Classifies a document image before the pipeline runs.
    Uses a combination of:
    1. OCR text signal matching (fast, high-precision)
    2. Image feature analysis (edge density, line detection for tables)
    """

    def classify(self, image: np.ndarray, ocr_texts: List[str]) -> Dict[str, Any]:
        """
        Classify document type from image + preliminary OCR text.

        Args:
            image: BGR numpy array
            ocr_texts: List of text strings from a fast OCR pass

        Returns:
            {
                "type": "code_screenshot",
                "confidence": 0.95,
                "signals_matched": ["Pylance", "Ln", "Col"],
                "hints": {"has_dark_bg": True, "has_table_lines": False}
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

            # Score = fraction of signals matched, weighted by total matches
            scores[doc_type] = len(matches) / len(config["signals"]) if config["signals"] else 0
            matched_signals[doc_type] = matches

        # ─── Image Feature Analysis ──────────────────────────────────────
        hints = self._analyze_image_features(image)

        # Handwriting boost from image features
        if hints.get("handwriting_density", 0) > 0.15:
            scores["handwritten"] = 0.7
        
        # Table boost from detected grid lines
        if hints.get("has_table_lines", False):
            scores["table"] = max(scores.get("table", 0), 0.5)
            # Survey forms have table lines + survey signals
            if scores.get("survey_form", 0) > 0:
                scores["survey_form"] = max(scores["survey_form"] * 1.5, 0.65)

        # Dark background boost for code screenshots
        if hints.get("has_dark_bg", False):
            scores["code_screenshot"] = scores.get("code_screenshot", 0) * 1.5

        # ─── Decision ────────────────────────────────────────────────────
        if not any(s > 0 for s in scores.values()):
            best_type = "general"
            confidence = 0.3
        else:
            best_type = max(scores, key=scores.get)
            confidence = min(scores[best_type], 1.0)

        result = {
            "type": best_type,
            "confidence": round(confidence, 3),
            "signals_matched": matched_signals.get(best_type, []),
            "hints": hints,
            "all_scores": {k: round(v, 3) for k, v in scores.items()},
        }
        
        logger.info(f"[CLASSIFIER] Document type: {best_type} (confidence={confidence:.2f})")
        return result

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
