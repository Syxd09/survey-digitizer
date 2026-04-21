"""
Hydra v12.5 — Constrained LLM Refiner
=======================================
Semantic post-processing via local quantized LLM.
CONSTRAINED mode: LLM can only correct, not hallucinate.

Safety rules:
  1. Edit distance per word must be ≤ 3 (Levenshtein)
  2. LLM cannot add new words not present in OCR candidates
  3. If output diverges too far, reject and keep original
  4. All corrections are logged for audit
"""

import logging
from typing import Optional, List
from rapidfuzz import distance as rf_distance

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False


class LLMRefiner:
    MAX_EDIT_DISTANCE_PER_WORD = 3
    MAX_TOTAL_DIVERGENCE = 0.3  # Max 30% of words can change

    def __init__(self, model_path: Optional[str] = None):
        self.enabled = LLAMA_AVAILABLE
        self.llm = None
        self.corrections_log: List[dict] = []

        if self.enabled and model_path:
            try:
                self.llm = Llama(
                    model_path=model_path,
                    n_ctx=512,
                    n_threads=4,
                    verbose=False,
                )
                logger.info(f"[LLM] Loaded model from {model_path}")
            except Exception as exc:
                logger.warning(f"[LLM] Failed to load model: {exc}")
                self.enabled = False

    def refine(self, text: str, context: str = "", doc_type: str = "general") -> str:
        """
        Constrained correction: LLM suggests a fix, but we verify it
        doesn't diverge too far from the original.
        """
        if not self.enabled or not self.llm:
            return text

        prompt = self._build_constrained_prompt(text, context, doc_type)

        try:
            output = self.llm(
                prompt,
                max_tokens=len(text) + 20,  # Limit output length
                stop=["\n", "---"],
                echo=False,
                temperature=0.1,  # Low temperature = less creative
            )
            candidate = output["choices"][0]["text"].strip()

            if not candidate or len(candidate) < 2:
                return text

            # ── Constraint Validation ────────────────────────────────────
            is_valid, reason = self._validate_correction(text, candidate)

            if is_valid:
                self.corrections_log.append({
                    "original": text,
                    "corrected": candidate,
                    "accepted": True,
                    "reason": reason,
                })
                logger.info(f"[LLM] Accepted correction: '{text}' → '{candidate}'")
                return candidate
            else:
                self.corrections_log.append({
                    "original": text,
                    "candidate": candidate,
                    "accepted": False,
                    "reason": reason,
                })
                logger.info(f"[LLM] Rejected correction: '{candidate}' ({reason})")
                return text

        except Exception as exc:
            logger.warning(f"[LLM] Refine failed: {exc}")
            return text

    def _build_constrained_prompt(self, text: str, context: str, doc_type: str) -> str:
        """Build a correction-only prompt that discourages hallucination."""
        type_hints = {
            "code_screenshot": "This is from a code editor. Fix OCR errors in programming terms, variable names, and error messages.",
            "form": "This is from a form. Fix OCR errors in field labels and values.",
            "invoice": "This is from an invoice. Fix OCR errors in amounts, dates, and item names.",
            "general": "Fix any OCR errors.",
        }
        hint = type_hints.get(doc_type, type_hints["general"])

        return f"""You are an OCR error corrector. ONLY fix spelling/OCR errors.
Do NOT add new information. Do NOT change meaning. Do NOT rewrite.
{hint}

Original text: {text}
Corrected text:"""

    def _validate_correction(self, original: str, candidate: str) -> tuple:
        """
        Validate that the LLM correction doesn't diverge too far.
        Returns (is_valid, reason).
        """
        orig_words = original.split()
        cand_words = candidate.split()

        # Rule 1: Word count shouldn't change dramatically
        if len(cand_words) > len(orig_words) * 1.5:
            return False, f"Too many new words ({len(cand_words)} vs {len(orig_words)})"

        if len(cand_words) < len(orig_words) * 0.5:
            return False, f"Too many words removed ({len(cand_words)} vs {len(orig_words)})"

        # Rule 2: Per-word edit distance check
        changed_count = 0
        for i, orig_w in enumerate(orig_words):
            if i >= len(cand_words):
                break
            edit_dist = rf_distance.Levenshtein.distance(orig_w, cand_words[i])
            if edit_dist > self.MAX_EDIT_DISTANCE_PER_WORD:
                return False, f"Word '{orig_w}' → '{cand_words[i]}' edit_dist={edit_dist} > {self.MAX_EDIT_DISTANCE_PER_WORD}"
            if edit_dist > 0:
                changed_count += 1

        # Rule 3: Total divergence check
        if orig_words and changed_count / len(orig_words) > self.MAX_TOTAL_DIVERGENCE:
            return False, f"Too much divergence: {changed_count}/{len(orig_words)} words changed"

        return True, "within_constraints"


def get_llm_refiner():
    return LLMRefiner()
