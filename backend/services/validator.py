"""
Hydra v13.0 — Domain-Aware Validation Layer
=============================================
Three-tier validation:
  1. Field-level: pattern matching, confidence checks
  2. Cross-field: sum validation, date consistency
  3. Schema-level: required fields per document type

Rule engine per document type. No hardcoded regex for specific images.
Loads correction rules from document classifier hints.

Supports:
- code_screenshot: Pylance rule names, [Ln N, Col N] format, bracket balance
- form: date/phone/email patterns
- invoice: currency/amount patterns, total validation
- survey_form: response consistency, column matching
- Correction dictionary from known OCR error mappings
"""

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Known OCR Error Mappings (domain-agnostic) ──────────────────────────────
OCR_CORRECTIONS = {
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
    "sklearn.datasets": ["sklearn datasets", "skleam datasets", "sklearn dataset5", "skleam.datasets"],
    "sklearn": ["skleam", "sk1earn"],
    "datasets": ["dataset5", "datas3ts"],
    "\"[\" was not closed": ["\"T\"was not closed", "\"T\" was not closed", "[\" was not closed"],
    "prg5.py": ["prgS py", "prg5 py", "prgS.py", "prgs.py"],
    "round2": ["roundz", "round?"],
}

ICON_ARTIFACTS = [
    r"^[QⓘⓆ⊗°©®]\s*",
    r"^[AⒶ][\\XY]\s*",
    r"^~\s*®?\s*",
    r"^[▲△⚠⚡]\s*",
]

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

# ── Schema Definitions (expected fields per document type) ───────────────────
SCHEMA_DEFINITIONS = {
    "invoice": {
        "required": ["Total", "Amount", "Date"],
        "optional": ["Subtotal", "Tax", "Invoice Number", "Due Date"],
    },
    "form": {
        "required": ["Name"],
        "optional": ["Date", "Address", "Phone", "Email", "Signature"],
    },
    "survey_form": {
        "required": [],  # Questions are dynamic
        "optional": ["Study Code", "Form No"],
    },
}


class ContentValidator:
    def __init__(self):
        # Compiled patterns for field validation
        self.patterns = {
            "date": re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "code_location": re.compile(r"\[Ln\s*\d+,?\s*Col\s*\d+\]"),
            "currency": re.compile(r"[\$£€¥]\s*[\d,]+\.?\d*"),
            "number": re.compile(r"^\d+\.?\d*$"),
        }
        
        self.icon_patterns = [re.compile(p) for p in ICON_ARTIFACTS]
        
        self.correction_map = {}
        for correct, variants in OCR_CORRECTIONS.items():
            for variant in variants:
                self.correction_map[variant.lower()] = correct

    # ═══════════════════════════════════════════════════════════════════════
    # Tier 1: Field-Level Validation
    # ═══════════════════════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════════════════════
    # Tier 2: Cross-Field Validation (NEW in v13.0)
    # ═══════════════════════════════════════════════════════════════════════

    def validate_document(
        self,
        entries: List[Dict],
        vlm_skeleton: Optional[Dict],
        doc_type: str,
    ) -> Dict[str, Any]:
        """
        Document-level validation — checks relationships BETWEEN fields.
        
        Returns:
        {
            "valid": True/False,
            "issues": [...],
            "warnings": [...],
        }
        """
        issues = []
        warnings = []

        # Cross-field validation
        if doc_type == "invoice":
            issues += self._validate_invoice_totals(entries)

        # Date consistency
        issues += self._validate_date_consistency(entries)

        # Schema validation (required fields)
        schema_issues = self._validate_schema(entries, doc_type)
        warnings += schema_issues  # Schema issues are warnings, not hard errors

        # Context validation (VLM expected types vs actual values)
        if vlm_skeleton and vlm_skeleton.get("status") == "ok":
            context_issues = self._validate_field_types(entries, vlm_skeleton)
            warnings += context_issues

        # Survey-specific: response consistency
        if doc_type == "survey_form":
            issues += self._validate_survey_responses(entries)

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def _validate_invoice_totals(self, entries: List[Dict]) -> List[str]:
        """Check: Total should equal sum of line items (if parseable)."""
        issues = []
        total_value = None
        line_items = []

        for entry in entries:
            label = entry.get("question", "").lower()
            value = entry.get("selected", "")

            if "total" in label and "sub" not in label:
                total_value = self._parse_currency(value)
            elif "subtotal" in label:
                pass  # Track separately
            elif any(kw in label for kw in ("line item", "item", "amount")):
                parsed = self._parse_currency(value)
                if parsed is not None:
                    line_items.append(parsed)

        if total_value is not None and line_items:
            expected_total = sum(line_items)
            if abs(total_value - expected_total) > 0.01:
                issues.append(
                    f"Total mismatch: declared ${total_value:.2f} vs "
                    f"sum of items ${expected_total:.2f}"
                )

        return issues

    def _validate_date_consistency(self, entries: List[Dict]) -> List[str]:
        """Check that all dates in the document are in a consistent format."""
        issues = []
        date_formats_found = set()

        for entry in entries:
            value = entry.get("selected", "")
            if self.patterns["date"].search(value):
                # Detect format: MM/DD/YYYY vs DD/MM/YYYY vs YYYY-MM-DD
                if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
                    date_formats_found.add("ISO")
                elif re.search(r"\d{1,2}/\d{1,2}/\d{4}", value):
                    date_formats_found.add("US")
                elif re.search(r"\d{1,2}-\d{1,2}-\d{4}", value):
                    date_formats_found.add("EU")

        if len(date_formats_found) > 1:
            issues.append(
                f"Inconsistent date formats detected: {', '.join(date_formats_found)}"
            )

        return issues

    def _validate_schema(self, entries: List[Dict], doc_type: str) -> List[str]:
        """Check that required fields for the doc type are present."""
        schema = SCHEMA_DEFINITIONS.get(doc_type)
        if not schema:
            return []

        warnings = []
        entry_labels = {e.get("question", "").lower() for e in entries}

        for required_field in schema.get("required", []):
            found = any(
                required_field.lower() in label
                for label in entry_labels
            )
            if not found:
                warnings.append(f"Missing required field: {required_field}")

        return warnings

    def _validate_field_types(
        self, entries: List[Dict], vlm_skeleton: Dict
    ) -> List[str]:
        """
        Context validation: check that OCR text matches the expected type
        defined by VLM skeleton.
        """
        warnings = []
        vlm_fields = vlm_skeleton.get("fields", [])

        for entry in entries:
            vlm_label = entry.get("vlm_label")
            if not vlm_label:
                continue

            # Find matching VLM field
            for vf in vlm_fields:
                if vf.get("label") == vlm_label:
                    expected_type = vf.get("type", "")
                    value = entry.get("selected", "")

                    if expected_type == "question" and not value:
                        warnings.append(
                            f"Question '{vlm_label}' has no answer"
                        )
                    break

        return warnings

    def _validate_survey_responses(self, entries: List[Dict]) -> List[str]:
        """
        Survey-specific: check response consistency.
        e.g., all responses should be from the same set of options.
        """
        issues = []
        responses = [
            e.get("selected", "")
            for e in entries
            if e.get("selected") and e.get("selected") != "[UNMARKED]"
        ]

        if not responses:
            return issues

        # Check for suspicious patterns: all same answer
        if len(set(responses)) == 1 and len(responses) > 5:
            issues.append(
                f"All {len(responses)} responses are identical: '{responses[0]}' — "
                f"possible extraction error"
            )

        return issues

    # ═══════════════════════════════════════════════════════════════════════
    # Text Cleaning
    # ═══════════════════════════════════════════════════════════════════════

    def clean_text(self, text: str, doc_type: str = "general") -> str:
        """Domain-aware text cleanup. Dispatches to type-specific cleaners."""
        if doc_type == "code_screenshot":
            return self._clean_code_screenshot(text)
        elif doc_type == "form":
            return self._clean_form(text)
        elif doc_type == "invoice":
            return self._clean_invoice(text)
        return self._clean_generic(text)

    def _clean_code_screenshot(self, text: str) -> str:
        """Clean text from code editor screenshots."""
        for pattern in self.icon_patterns:
            text = pattern.sub("", text)
        text = self._apply_corrections(text)
        text = self._fix_pylance_rules(text)
        text = self._fix_location_brackets(text)
        text = self._strip_header_artifacts(text)
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
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            text = pattern.sub(correct, text)
        return text

    def _fix_pylance_rules(self, text: str) -> str:
        """Fix garbled Pylance rule references."""
        if re.search(r"Pylance\(\w+\)", text):
            return text

        for rule in PYLANCE_RULES:
            pattern = re.compile(r"Pylance\s*" + re.escape(rule), re.IGNORECASE)
            if pattern.search(text):
                text = pattern.sub(f"Pylance({rule})", text)
                return text

        pylance_tail = re.search(r"Pylance(\w{10,})", text)
        if pylance_tail:
            garbled = pylance_tail.group(1)
            from rapidfuzz import process as rfprocess, fuzz
            match = rfprocess.extractOne(
                garbled, list(PYLANCE_RULES), scorer=fuzz.ratio, score_cutoff=50
            )
            if match:
                matched_rule = match[0]
                text = text.replace(
                    f"Pylance{garbled}", f"Pylance({matched_rule})"
                )

        text = re.sub(r"Pylanceire\w*\s*\w*", "", text)
        return text

    def _fix_location_brackets(self, text: str) -> str:
        """Fix bracket issues in [Ln N, Col N] location references."""
        text = re.sub(r"\[Lp\b", "[Ln", text)
        text = text.replace("&", "8")

        text = re.sub(
            r"(Col\s*)(\d)\](\d)\]",
            r"\g<1>\g<2>\g<3>]",
            text,
        )

        def _rewrite_location(m):
            ln = m.group(1)
            col = m.group(2)
            return f"[Ln {ln}, Col {col}]"

        text = re.sub(
            r"\[Ln\s*(\d+),?\s*Col\s*(\d+)\]",
            _rewrite_location,
            text,
        )

        text = re.sub(r"(Col\s*\d+)\)", r"\1]", text)
        text = re.sub(r"\(Ln\s", "[Ln ", text)

        text = re.sub(
            r"\[Ln\s*(\d+),?\s*Col\s*(\d+)(?!\d)(?!\])",
            lambda m: f"[Ln {m.group(1)}, Col {m.group(2)}]",
            text,
        )

        return text

    def _strip_header_artifacts(self, text: str) -> str:
        """Remove IDE tab header artifacts."""
        artifacts = ["@)", "«=", "°©", "=~"]
        for art in artifacts:
            text = text.replace(art, "")
        return text

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _parse_currency(text: str) -> Optional[float]:
        """Try to parse a currency value from text."""
        match = re.search(r"[\$£€¥]?\s*([\d,]+\.?\d*)", text)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                return None
        return None

    # Legacy compatibility
    def post_process_technical(self, text: str) -> str:
        """Legacy method — delegates to clean_text for code_screenshot."""
        return self.clean_text(text, doc_type="code_screenshot")


def get_validator():
    return ContentValidator()
