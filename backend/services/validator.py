"""
Phase 5 — Cleaning & Normalization
Phase 6 — Validation Layer
==================================
Refines extracted text and validates it against hard/soft rules.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process
from datetime import datetime
from services.llm_semantic_refiner import LLMSemanticRefiner

logger = logging.getLogger(__name__)

# Common OCR artifact mappings (Phase 5 spec)
OCR_ARTIFACT_MAP = {
    "O": "0", "o": "0", "D": "0", "U": "0", "Q": "0", "c": "0", "C": "0",
    "l": "1", "I": "1", "|": "1", "i": "1", "!": "1", "]": "1", "[": "1",
    "S": "5", "s": "5", "$": "5",
    "Z": "2", "z": "2",
    "B": "8", "&": "8",
    "G": "6", "b": "6",
    "T": "7", "t": "7",
    "A": "4", "a": "4", "H": "4",
    "g": "9", "q": "9", "P": "9",
    "E": "3", "J": "3"
}

class ContentValidator:
    """Implements Phase 5 & 6: Cleaning and Validation."""

    def __init__(self):
        # Common survey patterns
        self.patterns = {
            "date": re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),
            "email": re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$"),
            "number": re.compile(r"^-?\d*\.?\d+$")
        }
        self.llm_refiner = LLMSemanticRefiner()

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 5: Cleaning & Normalization
    # ═══════════════════════════════════════════════════════════════════════

    def clean_value(self, value: str, field_type: str = "text") -> str:
        """Applies generic and type-specific cleaning."""
        if not value:
            return ""

        # 1. Generic cleaning
        value = value.strip()
        value = re.sub(r"\s+", " ", value)

        # 2. Type-specific cleaning
        if field_type == "numeric":
            value = self._clean_numeric(value)
        elif field_type == "date":
            value = self._clean_date(value)
        elif field_type == "email":
            value = value.lower().replace(" ", "")

        return value

    def _clean_numeric(self, value: str) -> str:
        """Maps OCR artifacts to digits and removes non-numeric chars."""
        # Check if it has any actual digits. If not, it's probably not a number at all,
        # and aggressive mapping (e.g. 'Age' -> '4g9') will create false numbers.
        has_digits = any(c.isdigit() for c in value)
        
        cleaned = ""
        for char in value:
            if char.isdigit() or char == ".":
                cleaned += char
            elif has_digits and char in OCR_ARTIFACT_MAP:
                cleaned += OCR_ARTIFACT_MAP[char]
        
        # Remove anything that isn't a digit or dot
        cleaned = re.sub(r"[^\d.]", "", cleaned)
        return cleaned

    def _clean_date(self, value: str) -> str:
        """Standardises date separators."""
        # Replace common separators with /
        cleaned = re.sub(r"[.\-\s]", "/", value)
        return cleaned

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 6: Validation Layer
    # ═══════════════════════════════════════════════════════════════════════

    def validate_field(self, field_id: str, raw_value: str, field_config: Dict) -> Dict[str, Any]:
        """
        Validates value against hard and soft rules.
        
        Returns:
            Dict with "status", "original", "cleaned", "errors" (hard), "warnings" (soft)
        """
        errors = []
        warnings = []
        field_type = field_config.get("type", "text")
        required = field_config.get("required", False)

        # Phase 5: Cleaning
        cleaned_value = self.clean_value(raw_value, field_type)

        # 1. Check Required (Hard Error)
        if required and not cleaned_value:
            errors.append(f"Field '{field_id}' is required but empty.")
            return {
                "status": "REJECT", 
                "original": raw_value,
                "cleaned": cleaned_value,
                "errors": errors, 
                "warnings": warnings
            }

        if not cleaned_value:
            return {
                "status": "OK", 
                "original": raw_value,
                "cleaned": "",
                "errors": [], 
                "warnings": []
            }

        # 2. Type Validation (Soft Warning for OCR)
        if field_type == "numeric":
            if not self.patterns["number"].match(cleaned_value):
                warnings.append(f"Value '{cleaned_value}' is not a valid number.")
            else:
                # Range check (Soft)
                try:
                    num_val = float(cleaned_value)
                    min_v = field_config.get("min")
                    max_v = field_config.get("max")
                    if min_v is not None and num_val < min_v:
                        warnings.append(f"Value {num_val} is below minimum {min_v}.")
                    if max_v is not None and num_val > max_v:
                        warnings.append(f"Value {num_val} is above maximum {max_v}.")
                except ValueError:
                    warnings.append(f"Could not parse '{cleaned_value}' as float for range check.")

        elif field_type == "date":
            if not self.patterns["date"].match(cleaned_value):
                warnings.append(f"Value '{cleaned_value}' does not match date format DD/MM/YYYY.")

        # 3. Regex Pattern (Soft)
        regex_pattern = field_config.get("validation_regex")
        if regex_pattern:
            if not re.match(regex_pattern, cleaned_value):
                warnings.append(f"Value '{cleaned_value}' failed custom pattern validation.")

        # 4. Enum validation (Phase 6 spec: with fuzzy matching)
        allowed = field_config.get("allowed_values")
        if allowed and cleaned_value:
            # Try exact match first
            if cleaned_value in allowed:
                pass
            else:
                # Try fuzzy match with ratio which is better for mangled long strings than WRatio
                best_match, score, _ = process.extractOne(cleaned_value, allowed, scorer=fuzz.ratio)
                if score >= 70:  # Allow 30% character error rate for heavily garbled text
                    logger.info(f"[Phase 6] Fuzzy matched '{cleaned_value}' to '{best_match}' (score: {score})")
                    cleaned_value = best_match
                else:
                    # 5. Zero-Shot LLM Context Recovery Fallback
                    logger.warning(f"[Phase 6] Fuzzy match failed for '{cleaned_value}'. Attempting LLM Fallback.")
                    recovered_value = self.llm_refiner.refine_field_value(cleaned_value, allowed)
                    if recovered_value:
                        cleaned_value = recovered_value
                        logger.info(f"[Phase 6] LLM successfully recovered value to '{cleaned_value}'")
                    else:
                        warnings.append(f"Value '{cleaned_value}' not in allowed list and no close match found.")

        status = "OK"
        if errors:
            status = "REJECT"
        elif warnings:
            status = "NEEDS_REVIEW"

        return {
            "status": status,
            "original": raw_value,
            "cleaned": cleaned_value,
            "errors": errors,
            "warnings": warnings
        }


def get_validator():
    return ContentValidator()
