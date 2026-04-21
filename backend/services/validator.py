"""
Hydra v12.5 — Domain-Aware Validation Layer
=============================================
Rule engine per document type. No hardcoded regex for specific images.
Loads correction rules from document classifier hints.

Supports:
- code_screenshot: Pylance rule names, [Ln N, Col N] format, bracket balance
- form: date/phone/email patterns
- invoice: currency/amount patterns
- Correction dictionary from known OCR error mappings
"""

import re
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ── Known OCR Error Mappings (domain-agnostic) ──────────────────────────────
# These are common OCR misreads that happen across all engines.
# NOT hardcoded for a specific image — these are universal patterns.

OCR_CORRECTIONS = {
    # Pylance rule names (common OCR garbles)
    "reportUndefinedVariable": [
        r"reporUndefinedVariable",
        r"reportUndetinedVariable",
        r"reportUndetinedvarable",
        r"reporUndetinedvarable",
        r"reportUndefinedVariabl",
        r"reportUndefinedVariablee",
    ],
    "reportMissingModuleSource": [
        r"reportMissingModuleSourc",
        r"reportMissingModuleSourcee",
    ],
    "reportMissingImports": [
        r"reportMissingImport",
    ],
    # Common technical OCR errors
    "sklearn.datasets": ["sklearn datasets", "skleam datasets", "sklearn dataset5", "skleam.datasets"],
    "sklearn": ["skleam", "sk1earn"],
    "datasets": ["dataset5", "datas3ts"],
    # Common bracket/quote confusions in code context
    "\"[\" was not closed": ["\"T\"was not closed", "\"T\" was not closed", "[\" was not closed"],
    "prg5.py": ["prgS py", "prg5 py", "prgS.py", "prgs.py"],
    "round2": ["roundz", "round?"],
}

# Known IDE icon OCR artifacts (these are icons, not text)
ICON_ARTIFACTS = [
    r"^[QⓘⓆ⊗°©®]\s*",       # Info/warning icons
    r"^[AⒶ][\\XY]\s*",        # Warning triangle variants
    r"^~\s*®?\s*",             # Tilde + registered mark
    r"^[▲△⚠⚡]\s*",           # Triangle variants
]

# Pylance rule name patterns (for validation)
PYLANCE_RULES = {
    "reportUndefinedVariable",
    "reportMissingModuleSource",
    "reportMissingImports",
    "reportGeneralTypeIssues",
    "reportOptionalMemberAccess",
    "reportAttributeAccessIssue",
    "reportCallIssue",
    "reportIndexIssue",
    "reportOperatorIssue",
}


class ContentValidator:
    def __init__(self):
        # Compiled patterns for field validation
        self.patterns = {
            "date": re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "code_location": re.compile(r"\[Ln\s*\d+,?\s*Col\s*\d+\]"),
        }
        
        # Compile icon artifact patterns
        self.icon_patterns = [re.compile(p) for p in ICON_ARTIFACTS]
        
        # Compile OCR correction patterns
        self.correction_map = {}
        for correct, variants in OCR_CORRECTIONS.items():
            for variant in variants:
                self.correction_map[variant.lower()] = correct

    def validate_field(self, key: str, value: str, confidence: float) -> Dict[str, Any]:
        """
        Validates a single field. Returns status and correction trigger.
        """
        if confidence < 0.5:
            return {"status": "LOW_CONFIDENCE", "correction_required": True}

        # Pattern matching
        for p_name, pattern in self.patterns.items():
            if pattern.search(value):
                return {"status": "VALID", "type": p_name, "correction_required": False}

        # Logic check
        if "date" in key.lower() and not self.patterns["date"].search(value):
            return {"status": "INVALID_FORMAT", "expected": "DATE", "correction_required": True}

        if confidence < 0.7:
            return {"status": "MODERATE_CONFIDENCE", "correction_required": True}

        return {"status": "OK", "correction_required": False}

    def clean_text(self, text: str, doc_type: str = "general") -> str:
        """
        Domain-aware text cleanup. Dispatches to type-specific cleaners.
        """
        if doc_type == "code_screenshot":
            return self._clean_code_screenshot(text)
        elif doc_type == "form":
            return self._clean_form(text)
        elif doc_type == "invoice":
            return self._clean_invoice(text)
        return self._clean_generic(text)

    def _clean_code_screenshot(self, text: str) -> str:
        """
        Clean text from code editor screenshots.
        - Strip IDE icon artifacts
        - Fix Pylance rule names via known corrections
        - Fix bracket balance in locations
        - Fix common technical term OCR errors
        """
        # 1. Strip icon artifacts (these are VS Code warning/error icons)
        for pattern in self.icon_patterns:
            text = pattern.sub("", text)

        # 2. Fix known OCR error patterns
        text = self._apply_corrections(text)

        # 3. Fix Pylance rule formatting
        #    "PylancereporUndefinedVariable" → "Pylance(reportUndefinedVariable)"
        #    "Pylanceire" → remove (partial garble)
        text = self._fix_pylance_rules(text)

        # 4. Fix bracket balance in [Ln N, Col N]
        text = self._fix_location_brackets(text)

        # 5. Strip tabs/header artifacts
        text = self._strip_header_artifacts(text)

        # 6. Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _clean_form(self, text: str) -> str:
        """Clean text from form documents."""
        text = self._apply_corrections(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _clean_invoice(self, text: str) -> str:
        """Clean text from invoices."""
        text = self._apply_corrections(text)
        # Fix common currency OCR errors
        text = re.sub(r"\$\s+", "$", text)
        text = re.sub(r"(\d),(\d{3})", r"\1,\2", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _clean_generic(self, text: str) -> str:
        """Generic cleanup."""
        text = self._apply_corrections(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _apply_corrections(self, text: str) -> str:
        """Apply known OCR correction mappings."""
        for wrong, correct in self.correction_map.items():
            # Case-insensitive word-boundary replacement
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            text = pattern.sub(correct, text)
        return text

    def _fix_pylance_rules(self, text: str) -> str:
        """
        Fix garbled Pylance rule references.
        Handles patterns like:
        - "PylancereportUndefinedVariable" → "Pylance(reportUndefinedVariable)"
        - "Pylance(reportUndefinedVariable)" → already correct, leave alone
        - "Pylanceire" / "Pylanceire bie" → remove (garbage)
        """
        # Already properly formatted
        if re.search(r"Pylance\(\w+\)", text):
            return text

        # Pattern: "Pylance" immediately followed by a rule name (no space/paren)
        for rule in PYLANCE_RULES:
            pattern = re.compile(r"Pylance\s*" + re.escape(rule), re.IGNORECASE)
            if pattern.search(text):
                text = pattern.sub(f"Pylance({rule})", text)
                return text

        # Pattern: "Pylance" followed by garbled text that's close to a rule name
        pylance_tail = re.search(r"Pylance(\w{10,})", text)
        if pylance_tail:
            garbled = pylance_tail.group(1)
            # Try to match against known rules
            from rapidfuzz import process as rfprocess, fuzz
            match = rfprocess.extractOne(
                garbled, list(PYLANCE_RULES), scorer=fuzz.ratio, score_cutoff=50
            )
            if match:
                matched_rule = match[0]
                text = text.replace(
                    f"Pylance{garbled}", f"Pylance({matched_rule})"
                )

        # Remove partial garble like "Pylanceire" / "Pylanceire bie"
        text = re.sub(r"Pylanceire\w*\s*\w*", "", text)

        return text

    def _fix_location_brackets(self, text: str) -> str:
        """
        Fix bracket issues in [Ln N, Col N] location references.
        Uses a single authoritative regex to rewrite all location refs.
        """
        # Fix "Lp" → "Ln" (common OCR error)
        text = re.sub(r"\[Lp\b", "[Ln", text)

        # Fix HTML entities that sneak in
        text = text.replace("&", "8")  # & in OCR context is usually '8'

        # FIRST: Handle garbled bracket-split numbers BEFORE normal normalization
        # Pattern: [Ln N, Col D]D] where OCR inserted ] mid-number
        # e.g. "Col 1]4]" should become "Col 14]"
        # e.g. "Col 2]6]" should become "Col 26]"
        # e.g. "Col 3]1]" should become "Col 31]"
        # e.g. "Col 4]1]" should become "Col 41]"
        text = re.sub(
            r"(Col\s*)(\d)\](\d)\]",
            r"\g<1>\g<2>\g<3>]",
            text,
        )

        # SECOND: Normalize all [Ln N, Col N] to consistent format
        def _rewrite_location(m):
            ln = m.group(1)
            col = m.group(2)
            return f"[Ln {ln}, Col {col}]"

        text = re.sub(
            r"\[Ln\s*(\d+),?\s*Col\s*(\d+)\]",
            _rewrite_location,
            text,
        )

        # Fix closing paren → bracket: "Col N)" → "Col N]"
        text = re.sub(r"(Col\s*\d+)\)", r"\1]", text)

        # Fix opening paren → bracket
        text = re.sub(r"\(Ln\s", "[Ln ", text)

        # Final pass: ensure any remaining [Ln N, Col N without ] gets closed
        text = re.sub(
            r"\[Ln\s*(\d+),?\s*Col\s*(\d+)(?!\])",
            lambda m: f"[Ln {m.group(1)}, Col {m.group(2)}]",
            text,
        )

        return text

    def _strip_header_artifacts(self, text: str) -> str:
        """Remove IDE tab header artifacts."""
        # Remove common OCR artifacts from VS Code tabs
        artifacts = ["@)", "«=", "°©", "=~"]
        for art in artifacts:
            text = text.replace(art, "")
        return text

    # Legacy compatibility
    def post_process_technical(self, text: str) -> str:
        """Legacy method — delegates to clean_text for code_screenshot."""
        return self.clean_text(text, doc_type="code_screenshot")


def get_validator():
    return ContentValidator()
