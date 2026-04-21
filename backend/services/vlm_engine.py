"""
Hydra v12.5 — VLM Engine
=========================
Structured document extraction via Pix2Struct.
Falls back gracefully to OCR-only if model unavailable.

Pix2Struct is trained on screenshots and UI content — unlike Donut
which is trained on scanned forms only.
"""

import torch
import logging
import json
import re
from PIL import Image
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class VLMEngine:
    def __init__(self):
        self.device = "cpu"  # Pix2Struct is faster on CPU for inference
        self.model = None
        self.processor = None
        self._load_model()

    def _load_model(self):
        """Load Pix2Struct for document VQA."""
        try:
            if torch.backends.mps.is_available():
                self.device = "mps"
        except Exception:
            pass

        try:
            from transformers import Pix2StructForConditionalGeneration, Pix2StructProcessor

            model_name = "google/pix2struct-docvqa-base"
            logger.info(f"[VLM] Loading {model_name} on {self.device}...")

            self.processor = Pix2StructProcessor.from_pretrained(model_name)
            self.model = Pix2StructForConditionalGeneration.from_pretrained(model_name)
            
            # Use CPU for Pix2Struct — MPS has compatibility issues with some ops
            self.model.to("cpu")
            self.model.eval()
            self.device = "cpu"
            
            logger.info("[VLM] Pix2Struct loaded successfully.")
        except Exception as exc:
            logger.warning(f"[VLM] Pix2Struct load failed: {exc}. Trying Donut fallback...")
            self._load_donut_fallback()

    def _load_donut_fallback(self):
        """Fallback to Donut if Pix2Struct unavailable."""
        try:
            from transformers import DonutProcessor, VisionEncoderDecoderModel

            model_name = "naver-clova-ix/donut-base-finetuned-docvqa"
            logger.info(f"[VLM] Loading fallback {model_name}...")

            self.processor = DonutProcessor.from_pretrained(model_name)
            self.model = VisionEncoderDecoderModel.from_pretrained(model_name)
            self.model.to("cpu")
            self.model.eval()
            self.device = "cpu"
            self._is_donut = True
            logger.info("[VLM] Donut fallback loaded.")
        except Exception as exc:
            logger.error(f"[VLM] All VLM models failed: {exc}")
            self.model = None
            self._is_donut = False

    @property
    def _is_pix2struct(self) -> bool:
        if self.model is None:
            return False
        return "Pix2Struct" in type(self.model).__name__

    def extract_structured(
        self, image: Image.Image, doc_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Extract structured content from the document.
        Returns a dictionary with extracted fields.

        For code_screenshot: extracts error entries with message, rule, location.
        For form: extracts key-value pairs.
        For general: extracts text blocks.
        """
        if self.model is None:
            return {"status": "vlm_unavailable", "entries": []}

        # Build type-aware prompt
        prompt = self._build_prompt(doc_type)

        try:
            raw_output = self._run_inference(image, prompt)
            parsed = self._parse_output(raw_output, doc_type)
            return parsed
        except Exception as exc:
            logger.warning(f"[VLM] Extraction failed: {exc}")
            return {"status": "error", "raw": str(exc), "entries": []}

    def query(self, image: Image.Image, question: str) -> str:
        """
        Simple VQA query for backward compatibility.
        """
        if self.model is None:
            return "[VLM_NOT_AVAILABLE]"

        try:
            return self._run_inference(image, question)
        except Exception as exc:
            return f"[ERROR: {exc}]"

    def _build_prompt(self, doc_type: str) -> str:
        """Build a structured extraction prompt based on document type."""
        prompts = {
            "code_screenshot": (
                "What are all the error messages shown? "
                "For each error, what is the message text, the rule name, and the line and column number?"
            ),
            "form": (
                "What are all the form fields and their values? "
                "List each field label and its corresponding filled value."
            ),
            "invoice": (
                "What are the line items, quantities, prices, and totals shown?"
            ),
            "general": (
                "What is all the text content shown in this image?"
            ),
        }
        return prompts.get(doc_type, prompts["general"])

    def _run_inference(self, image: Image.Image, prompt: str) -> str:
        """Run model inference with the given prompt."""
        if self._is_pix2struct:
            return self._run_pix2struct(image, prompt)
        elif hasattr(self, '_is_donut') and self._is_donut:
            return self._run_donut(image, prompt)
        else:
            return "[NO_MODEL]"

    def _run_pix2struct(self, image: Image.Image, prompt: str) -> str:
        """Run Pix2Struct inference."""
        inputs = self.processor(
            images=image,
            text=prompt,
            return_tensors="pt",
        )
        # Move to CPU explicitly
        inputs = {k: v.to("cpu") for k, v in inputs.items()}

        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=512,
            )

        result = self.processor.decode(generated[0], skip_special_tokens=True)
        return result.strip()

    def _run_donut(self, image: Image.Image, prompt: str) -> str:
        """Run Donut inference (fallback)."""
        task_prompt = f"<s_docvqa><s_question>{prompt}</s_question><s_answer>"
        
        pixel_values = self.processor(image, return_tensors="pt").pixel_values
        pixel_values = pixel_values.to("cpu")

        decoder_input_ids = self.processor.tokenizer(
            task_prompt, add_special_tokens=False, return_tensors="pt"
        ).input_ids.to("cpu")

        with torch.no_grad():
            outputs = self.model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                max_length=512,
                pad_token_id=self.processor.tokenizer.pad_token_id,
                eos_token_id=self.processor.tokenizer.eos_token_id,
                num_beams=1,
                use_cache=True,
            )

        seq = self.processor.batch_decode(outputs)[0]
        seq = seq.replace(self.processor.tokenizer.eos_token, "")
        seq = seq.replace(self.processor.tokenizer.pad_token, "")

        answer_match = re.search(r"<s_answer>(.*)", seq)
        if answer_match:
            return answer_match.group(1).replace("</s_answer>", "").strip()
        return seq.strip()

    def _parse_output(self, raw: str, doc_type: str) -> Dict[str, Any]:
        """
        Parse VLM raw output into structured format.
        The VLM output is free text — we extract structure from it.
        """
        result = {"status": "ok", "raw": raw, "entries": []}

        if doc_type == "code_screenshot":
            # Try to extract error entries from the raw text
            entries = self._parse_code_errors(raw)
            result["entries"] = entries
        
        return result

    def _parse_code_errors(self, raw: str) -> List[Dict]:
        """Extract error entries from VLM output text."""
        entries = []

        # Pattern: look for line/col references
        lines = raw.split("\n") if "\n" in raw else [raw]
        
        for line in lines:
            entry = {}
            
            # Extract location [Ln N, Col N]
            loc_match = re.search(r"\[?Ln\s*(\d+),?\s*Col\s*(\d+)\]?", line)
            if loc_match:
                entry["location"] = f"[Ln {loc_match.group(1)}, Col {loc_match.group(2)}]"
            
            # Extract Pylance rule
            rule_match = re.search(r"Pylance\((\w+)\)", line)
            if rule_match:
                entry["rule"] = f"Pylance({rule_match.group(1)})"
            elif "Pylance" in line:
                entry["rule"] = "Pylance"

            if entry:
                entry["raw_line"] = line.strip()
                entries.append(entry)

        return entries


def get_vlm():
    return VLMEngine()
