"""
Hydra v13.0 — VLM Engine (Structure Authority)
================================================
The VLM is the CONTROLLER of document structure.
OCR provides text; VLM provides semantics.

Strategy:
  1. Multi-query extraction builds a "document skeleton"
  2. Skeleton defines: sections, fields, table structure
  3. OCR text is mapped INTO the skeleton by VLMStructureMapper

Models: Pix2Struct (primary) → Donut (fallback) → None (OCR-only)
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
        self.device = "cpu"
        self.model = None
        self.processor = None
        self._model_type = None  # "pix2struct" or "donut"
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
            self.model.to("cpu")
            self.model.eval()
            self.device = "cpu"
            self._model_type = "pix2struct"
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
            self._model_type = "donut"
            logger.info("[VLM] Donut fallback loaded.")
        except Exception as exc:
            logger.error(f"[VLM] All VLM models failed: {exc}")
            self.model = None
            self._model_type = None

    # ═══════════════════════════════════════════════════════════════════════
    # NEW: Skeleton Extraction (v13.0 — VLM as Structure Authority)
    # ═══════════════════════════════════════════════════════════════════════

    def extract_skeleton(
        self, image: Image.Image, doc_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Extract a document SKELETON — the structural blueprint.
        
        The skeleton defines:
          - sections: logical groups in the document
          - fields: labeled data slots (name, date, etc.)
          - table: column headers + expected row count
          - field_order: reading-order list of field labels
        
        OCR text is later mapped INTO this skeleton.
        """
        if self.model is None:
            return self._empty_skeleton("vlm_unavailable")

        try:
            skeleton = {}

            # Query 1: Document structure overview
            structure_raw = self._query(
                image,
                self._structure_prompt(doc_type)
            )
            skeleton["structure_raw"] = structure_raw

            # Query 2: Field/label extraction
            fields_raw = self._query(
                image,
                self._fields_prompt(doc_type)
            )
            skeleton["fields"] = self._parse_fields(fields_raw, doc_type)

            # Query 3: Table structure (if doc has tables)
            if doc_type in ("survey_form", "table", "invoice"):
                table_raw = self._query(
                    image,
                    self._table_prompt(doc_type)
                )
                skeleton["table"] = self._parse_table_structure(table_raw)
            else:
                skeleton["table"] = None

            # Query 4: Section headers
            sections_raw = self._query(
                image,
                "What are the main section headers or titles in this document?"
            )
            skeleton["sections"] = self._parse_sections(sections_raw)

            # Build field order from VLM understanding
            skeleton["field_order"] = [f["label"] for f in skeleton["fields"]]
            skeleton["status"] = "ok"
            skeleton["doc_type"] = doc_type

            logger.info(
                f"[VLM] Skeleton extracted: {len(skeleton['fields'])} fields, "
                f"{len(skeleton['sections'])} sections, "
                f"table={'yes' if skeleton['table'] else 'no'}"
            )
            return skeleton

        except Exception as exc:
            logger.warning(f"[VLM] Skeleton extraction failed: {exc}")
            return self._empty_skeleton(f"error: {exc}")

    # ═══════════════════════════════════════════════════════════════════════
    # Legacy: Single-query extraction (backward compat)
    # ═══════════════════════════════════════════════════════════════════════

    def extract_structured(
        self, image: Image.Image, doc_type: str = "general"
    ) -> Dict[str, Any]:
        """Legacy method — delegates to skeleton extraction."""
        skeleton = self.extract_skeleton(image, doc_type)
        return {
            "status": skeleton.get("status", "unknown"),
            "raw": skeleton.get("structure_raw", ""),
            "entries": skeleton.get("fields", []),
            "skeleton": skeleton,
        }

    def query(self, image: Image.Image, question: str) -> str:
        """Simple VQA query for backward compatibility."""
        if self.model is None:
            return "[VLM_NOT_AVAILABLE]"
        try:
            return self._query(image, question)
        except Exception as exc:
            return f"[ERROR: {exc}]"

    # ═══════════════════════════════════════════════════════════════════════
    # Prompt Builders (doc-type aware)
    # ═══════════════════════════════════════════════════════════════════════

    def _structure_prompt(self, doc_type: str) -> str:
        """Build a structural overview prompt."""
        prompts = {
            "survey_form": (
                "Describe the structure of this survey form. "
                "What are the column headers? How many questions are there? "
                "What type of response options are shown (checkmarks, circles, text)?"
            ),
            "form": (
                "Describe the layout of this form. "
                "What fields are present? Are they arranged in rows or columns? "
                "Which fields have been filled in?"
            ),
            "invoice": (
                "Describe the structure of this invoice. "
                "What are the line item columns? Is there a header section? "
                "What are the summary fields (subtotal, tax, total)?"
            ),
            "code_screenshot": (
                "What are all the error messages shown? "
                "For each error, what is the message text, the rule name, "
                "and the line and column number?"
            ),
            "table": (
                "Describe the table structure. "
                "How many columns and rows? What are the column headers?"
            ),
        }
        return prompts.get(doc_type, (
            "Describe the structure and layout of this document. "
            "What are the main sections and what type of content does each contain?"
        ))

    def _fields_prompt(self, doc_type: str) -> str:
        """Build a field extraction prompt."""
        prompts = {
            "survey_form": (
                "List every question in this survey with its number. "
                "For each question, state the text and which response option "
                "appears to be selected (circled, checked, or marked)."
            ),
            "form": (
                "List every form field label and its filled value. "
                "Format: Label: Value"
            ),
            "invoice": (
                "List every line item with quantity, description, unit price, "
                "and total. Also list subtotal, tax, and total."
            ),
            "code_screenshot": (
                "List each error/warning message with its rule name "
                "and location (line number, column number)."
            ),
        }
        return prompts.get(doc_type, (
            "What are all the labeled fields or data entries in this document? "
            "List each field label and its value."
        ))

    def _table_prompt(self, doc_type: str) -> str:
        """Build a table structure prompt."""
        return (
            "Describe the table in this document. "
            "What are the exact column headers from left to right? "
            "How many data rows are there?"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # Inference Runners
    # ═══════════════════════════════════════════════════════════════════════

    def _query(self, image: Image.Image, prompt: str) -> str:
        """Run a single VQA query."""
        if self._model_type == "pix2struct":
            return self._run_pix2struct(image, prompt)
        elif self._model_type == "donut":
            return self._run_donut(image, prompt)
        return "[NO_MODEL]"

    def _run_pix2struct(self, image: Image.Image, prompt: str) -> str:
        """Run Pix2Struct inference."""
        inputs = self.processor(
            images=image,
            text=prompt,
            return_tensors="pt",
        )
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

    # ═══════════════════════════════════════════════════════════════════════
    # Output Parsers
    # ═══════════════════════════════════════════════════════════════════════

    def _parse_fields(self, raw: str, doc_type: str) -> List[Dict]:
        """
        Parse VLM free-text output into structured field list.
        VLM output is natural language — we extract structure from it.
        
        v13.1: Much more aggressive extraction to avoid losing VLM output.
        """
        fields = []

        if not raw or raw.startswith("["):
            return fields

        # Survey-specific: numbered questions
        if doc_type == "survey_form":
            # Pattern: "1. Question text - Selected Option" or "1) Question text"
            q_pattern = re.compile(
                r'(?:^|\n)\s*(\d+)[.)]\s*(.+?)(?:\s*[-–—:]\s*(.+?))?(?=\n\s*\d+[.)]|\Z)',
                re.DOTALL
            )
            matches = q_pattern.findall(raw)
            if matches:
                for num, text, selected in matches:
                    fields.append({
                        "label": f"Q{num.strip()}",
                        "text": text.strip(),
                        "type": "question",
                        "vlm_answer": selected.strip() if selected else None,
                    })
                return fields

        # ── Strategy 1: "Label: Value" or "Label - Value" patterns ────────
        # Broadened: allow lowercase start, longer labels, more separators
        kv_pattern = re.compile(
            r'(?:^|\n)\s*([A-Za-z][A-Za-z0-9\s\./,#&()-]{1,60}?)\s*[:=–—]\s*(.+?)(?=\n|$)'
        )
        matches = kv_pattern.findall(raw)
        for label, value in matches:
            label = label.strip()
            value = value.strip()
            if label and value and len(label) > 1:
                fields.append({
                    "label": label,
                    "text": value,
                    "type": "field",
                    "vlm_answer": value,
                })

        # ── Strategy 2: Numbered items ("1. text", "2) text") ─────────────
        if not fields:
            num_pattern = re.compile(
                r'(?:^|\n)\s*(\d+)[.)]\s*(.+?)(?=\n\s*\d+[.)]|\Z)',
                re.DOTALL
            )
            matches = num_pattern.findall(raw)
            for num, text in matches:
                text = text.strip()
                if text and len(text) > 2:
                    # Check for inline answer separator
                    answer = None
                    for sep in [" - ", " – ", " — ", ": "]:
                        if sep in text:
                            parts = text.split(sep, 1)
                            text = parts[0].strip()
                            answer = parts[1].strip()
                            break
                    fields.append({
                        "label": f"Item_{num.strip()}",
                        "text": text,
                        "type": "item",
                        "vlm_answer": answer,
                    })

        # ── Strategy 3: Bullet points ("- text", "• text", "* text") ──────
        if not fields:
            bullet_pattern = re.compile(
                r'(?:^|\n)\s*[-•*]\s+(.+?)(?=\n|$)'
            )
            matches = bullet_pattern.findall(raw)
            for i, text in enumerate(matches):
                text = text.strip()
                if text and len(text) > 2:
                    fields.append({
                        "label": f"Item_{i+1}",
                        "text": text,
                        "type": "bullet",
                        "vlm_answer": None,
                    })

        # ── Strategy 4: Comma-separated items (common VLM output) ─────────
        if not fields and ", " in raw and raw.count(", ") >= 2:
            items = [item.strip() for item in raw.split(",") if item.strip()]
            if len(items) >= 3:
                for i, item in enumerate(items):
                    if len(item) > 1:
                        fields.append({
                            "label": f"Item_{i+1}",
                            "text": item,
                            "type": "list_item",
                            "vlm_answer": None,
                        })

        # ── Fallback: split by lines and treat each as a field ────────────
        if not fields:
            for i, line in enumerate(raw.strip().split("\n")):
                line = line.strip()
                if line and len(line) > 2:
                    # Try to detect inline key:value
                    vlm_answer = None
                    label = f"Field_{i+1}"
                    
                    if ": " in line:
                        parts = line.split(": ", 1)
                        if len(parts[0]) < 50:
                            label = parts[0].strip()
                            vlm_answer = parts[1].strip()
                    
                    fields.append({
                        "label": label,
                        "text": line,
                        "type": "text",
                        "vlm_answer": vlm_answer,
                    })

        return fields

    def _parse_table_structure(self, raw: str) -> Optional[Dict]:
        """
        Parse VLM description of table structure into structured dict.
        """
        if not raw:
            return None

        table = {
            "columns": [],
            "row_count": None,
            "raw_description": raw,
        }

        # Try to extract column headers
        # Pattern: "columns are: A, B, C" or "headers: A | B | C"
        col_patterns = [
            r'(?:column|header)s?\s*(?:are|:)\s*(.+?)(?:\.|$)',
            r'(?:left to right|columns?):\s*(.+?)(?:\.|$)',
        ]
        for pattern in col_patterns:
            match = re.search(pattern, raw, re.IGNORECASE)
            if match:
                col_text = match.group(1)
                # Split by comma, pipe, "and", or common separators
                cols = re.split(r'[,|]|\band\b', col_text)
                table["columns"] = [c.strip().strip('"\'') for c in cols if c.strip()]
                break

        # Try to extract row count
        row_match = re.search(r'(\d+)\s*(?:rows?|questions?|items?|entries)', raw, re.IGNORECASE)
        if row_match:
            table["row_count"] = int(row_match.group(1))

        return table if table["columns"] else None

    def _parse_sections(self, raw: str) -> List[str]:
        """Parse section headers from VLM output."""
        if not raw:
            return []

        sections = []
        # Split by newlines, bullets, or numbered items
        for line in re.split(r'[\n•\-]|\d+[.)]\s*', raw):
            line = line.strip().strip('"\'')
            if line and len(line) > 2 and len(line) < 100:
                sections.append(line)

        return sections[:10]  # Cap at 10 sections

    def _empty_skeleton(self, status: str) -> Dict[str, Any]:
        """Return empty skeleton with status."""
        return {
            "status": status,
            "fields": [],
            "table": None,
            "sections": [],
            "field_order": [],
            "structure_raw": "",
            "doc_type": "unknown",
        }



def get_vlm():
    return VLMEngine()

