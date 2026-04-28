"""
Phase 10 — API Layer (Orchestration logic)
=========================================
Unifies all 15 phases into a single deterministic pipeline.
"""

import asyncio
import base64
import io
import logging
import hashlib
import uuid
import cv2
from typing import Any, Dict, List, Optional
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PIL import Image as PILImage
import numpy as np

# Import all Phase services
from services.document_processor import get_document_processor
from services.ocr_engine import get_ocr_engine
from services.line_reconstructor import get_line_reconstructor
from services.extraction_engine import get_extraction_engine
from services.validator import get_validator
from services.confidence_engine import get_confidence_engine
from services.decision_engine import get_decision_engine
from services.db_service import get_db_service
from services.observability import get_observability_service
from services.template_service import get_template_service
from services.cache_service import get_cache_service
from services.storage import StorageService
from services.grid_detector import get_grid_detector

logger = logging.getLogger(__name__)

class ExtractionOrchestrator:
    """The master controller for the v2.0 OCR Pipeline."""

    def __init__(self, executor: ThreadPoolExecutor):
        self.executor = executor
        
        # Initialise services
        self.doc_processor = get_document_processor()
        self.ocr_engine = get_ocr_engine()
        self.line_reconstructor = get_line_reconstructor()
        self.extraction_engine = get_extraction_engine()
        self.validator = get_validator()
        self.confidence_engine = get_confidence_engine()
        self.decision_engine = get_decision_engine()
        self.db = get_db_service()
        self.obs = get_observability_service()
        self.template_service = get_template_service()
        self.cache = get_cache_service()
        self.storage = StorageService()
        self.grid_detector = get_grid_detector()

    async def digitize(self, image_b64: str, request_id: str = None) -> Dict[str, Any]:
        """
        Executes the full 15-phase pipeline.
        """
        if not request_id:
            request_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        
        try:
            # 1. Magic Byte Validation (Phase 15)
            pil_img = self._decode_and_validate_image(image_b64)
            
            # 2. Run Pipeline in ThreadPool (CPU/Network bound)
            result = await loop.run_in_executor(
                self.executor,
                self._run_pipeline,
                pil_img,
                request_id
            )
            
            return result

        except Exception as exc:
            logger.error(f"[ORCH] Pipeline failed for {request_id}: {exc}", exc_info=True)
            return self._error_result(str(exc), request_id)

    def _run_pipeline(self, pil_img: PILImage.Image, request_id: str) -> Dict[str, Any]:
        """Synchronous execution of the pipeline phases."""
        
        # 0. Idempotency Check (Phase 9 Spec)
        img_bytes = io.BytesIO()
        pil_img.save(img_bytes, format='JPEG')
        img_hash = hashlib.md5(img_bytes.getvalue()).hexdigest()
        
        existing_id = self.db.check_idempotency(img_hash)
        if existing_id:
            logger.info(f"[ORCH] Serving result from idempotency cache: {existing_id}")
            cached = self.db.get_request(existing_id)
            if cached: return cached
        
        diag = {
            "request_id": request_id,
            "image_hash": img_hash,
            "processed_at": datetime.now().isoformat(),
            "phases": {},
            "metrics": {}
        }
        t_start = time.time()

        # PHASE 1: Preprocessing
        logger.info(f"[{request_id}] Phase 1: Preprocessing")
        t_p1 = time.time()
        # Convert PIL to BGR for OpenCV
        img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        processed_img_bgr, p1_diag = self.doc_processor.process_document(img_bgr)
        diag.update(p1_diag)
        diag["phases"]["1_preprocessing"] = p1_diag["quality"]["status"]
        diag["metrics"]["p1_preprocessing_ms"] = int((time.time() - t_p1) * 1000)
        self.db.save_stage_trace(request_id, "preprocessing", diag["phases"]["1_preprocessing"], diag["metrics"]["p1_preprocessing_ms"])

        # Phase 1 Guardrail (Stop if REJECT)
        if p1_diag["quality"]["status"] == "REJECT":
            logger.warning(f"[{request_id}] Phase 1 REJECTED image. Stopping pipeline.")
            diag["decision"] = {"status": "REJECT", "reason": p1_diag["quality"].get("rejection_reason", "Quality check failed")}
            self.db.save_request(request_id, diag, image_hash=img_hash)
            return diag

        # PHASE 2: OCR
        logger.info(f"[{request_id}] Phase 2: OCR Execution")
        t_p2 = time.time()
        # Need bytes for GCV
        _, img_encoded = cv2.imencode(".jpg", processed_img_bgr)
        img_bytes = img_encoded.tobytes()
        
        # Phase 14: Cache Check
        words = self.cache.get_ocr(img_bytes)
        if words:
            logger.info(f"[{request_id}] OCR Cache HIT")
        else:
            logger.info(f"[{request_id}] OCR Cache MISS. Calling engine.")
            words = self.ocr_engine.execute_ocr(img_bytes)
            self.cache.set_ocr(img_bytes, words)
            
        diag["phases"]["2_ocr"] = f"SUCCESS ({len(words)} words)"
        diag["metrics"]["p2_ocr_ms"] = int((time.time() - t_p2) * 1000)
        self.db.save_stage_trace(request_id, "ocr", "SUCCESS", diag["metrics"]["p2_ocr_ms"])

        # PHASE 3: Line Reconstruction
        logger.info(f"[{request_id}] Phase 3: Line Reconstruction")
        t_p3 = time.time()
        lines = self.line_reconstructor.reconstruct_lines(words)
        diag["phases"]["3_reconstruction"] = f"SUCCESS ({len(lines)} lines)"
        diag["metrics"]["p3_reconstruction_ms"] = int((time.time() - t_p3) * 1000)
        self.db.save_stage_trace(request_id, "reconstruction", "SUCCESS", diag["metrics"]["p3_reconstruction_ms"])

        # PHASE 4: Extraction (Dynamic Grid + Template Fallback)
        logger.info(f"[{request_id}] Phase 4: Field Extraction")
        t_p4 = time.time()
        
        # Phase 13: Dynamic Template Lookup (used for metadata fallback)
        template = self.template_service.get_template()
        
        # Phase 4.3: Dynamic Grid Detection (NEW)
        logger.info(f"[{request_id}] Phase 4.3: Dynamic Grid Detection")
        grid_result = self.grid_detector.detect_grid(processed_img_bgr)
        diag["grid_detection"] = grid_result.get("diagnostics", {})
        diag["grid_detection"]["success"] = grid_result.get("success", False)
        
        if grid_result.get("success"):
            logger.info(
                f"[{request_id}] Grid detected: "
                f"{len(grid_result['rows'])} rows × "
                f"{len(grid_result['option_columns'])} option columns. "
                f"Using dynamic extraction."
            )
            extracted_fields = self.extraction_engine.extract_fields_dynamic(
                img_bgr=processed_img_bgr,
                grid_result=grid_result,
                template=template,
                lines=lines,
                all_words=words,
            )
            diag["extraction_method"] = "dynamic_grid"
        else:
            logger.warning(
                f"[{request_id}] Grid detection failed. "
                f"Falling back to template-based extraction."
            )
            extracted_fields = self.extraction_engine.extract_fields(
                lines, template, processed_img_bgr, all_words=words
            )
            diag["extraction_method"] = "template_fallback"
        
        diag["phases"]["4_extraction"] = f"SUCCESS ({len(extracted_fields)} fields, method={diag['extraction_method']})"
        diag["metrics"]["p4_extraction_ms"] = int((time.time() - t_p4) * 1000)
        self.db.save_stage_trace(request_id, "extraction", "SUCCESS", diag["metrics"]["p4_extraction_ms"])

        # PHASE 5, 6 & 7: Parallel Validation & Confidence (Phase 14)
        logger.info(f"[{request_id}] Phase 5, 6 & 7: Parallel Validation & Scoring")
        t_fields_start = time.time()
        
        def process_field_task(field):
            return self._process_single_field(field, diag, processed_img_bgr)

        validated_fields = list(self.executor.map(process_field_task, extracted_fields))
        
        diag["fields"] = validated_fields
        diag["phases"]["5_6_7_logic"] = "SUCCESS"
        diag["metrics"]["p5_6_7_ms"] = int((time.time() - t_fields_start) * 1000)
        self.db.save_stage_trace(request_id, "logic", "SUCCESS", diag["metrics"]["p5_6_7_ms"])

        # PHASE 8: Decision Engine
        logger.info(f"[{request_id}] Phase 8: Decision Routing")
        decision = self.decision_engine.decide(validated_fields)
        diag["decision"] = decision
        diag["fields"] = validated_fields # Ensure fields are in diag for persistence
        diag["questions"] = validated_fields # Frontend/Survey compatibility alias
        diag["phases"]["8_decision"] = decision["status"]
        self.db.save_stage_trace(request_id, "decision", decision["status"], 0)

        # PHASE 9: Storage
        logger.info(f"[{request_id}] Phase 9: Persistence")
        # Persist trace metadata for debug bundle retrieval
        diag["trace"] = {
            "file_path": "",  # Updated by observability save below
            "processed_at": diag["processed_at"] if "processed_at" in diag else datetime.now().isoformat()
        }
        self.db.save_request(request_id, diag, image_hash=img_hash)
        
        # Phase 13/Workbench Sync: Ensure JSON storage is updated
        # This is CRITICAL for the Workbench station which polls JSON storage
        try:
            self.storage.update_scan_results("default", request_id, diag, diag.get("metrics", {}))
        except Exception as store_exc:
            logger.warning(f"[{request_id}] JSON Storage sync failed: {store_exc}")

        diag["phases"]["9_storage"] = "SUCCESS"

        # PHASE 12: Observability (Trace)
        logger.info(f"[{request_id}] Phase 12: Saving Trace")
        
        # Generate Debug Overlay
        debug_img = self.obs.generate_debug_overlay(processed_img_bgr, diag)
        
        # Save trace data and images
        processed_pil = PILImage.fromarray(cv2.cvtColor(processed_img_bgr, cv2.COLOR_BGR2RGB))
        debug_pil = PILImage.fromarray(cv2.cvtColor(debug_img, cv2.COLOR_BGR2RGB))
        
        self.obs.save_trace(request_id, diag, {
            "preprocessed": processed_pil,
            "debug_overlay": debug_pil
        })
        
        diag["metrics"]["total_ms"] = int((time.time() - t_start) * 1000)
        return diag

    def _decode_and_validate_image(self, image_b64: str) -> PILImage.Image:
        """Phase 15 Security: Magic byte validation and decoding."""
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        raw = base64.b64decode(image_b64)
        
        # Verify Magic Bytes (Phase 15.1)
        # JPEG: FF D8 FF
        # PNG: 89 50 4E 47
        if not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG')):
            logger.error("Security violation: Rejected non-image file upload via magic byte check.")
            raise ValueError("Invalid file format. Only JPEG and PNG are allowed.")
            
        return PILImage.open(io.BytesIO(raw)).convert("RGB")

    def _process_single_field(self, field: Dict[str, Any], diag: Dict[str, Any], img_bgr: np.ndarray) -> Dict[str, Any]:
        """Helper for Phase 14 parallel field processing."""
        # Combined Phase 5 & 6 Validation (Hard/Soft)
        val_res = self.validator.validate_field(
            field_id=field["id"],
            raw_value=field["raw_value"] or "",
            field_config=field
        )
        
        # PHASE 7: Confidence Scoring
        conf_res = self.confidence_engine.compute_field_confidence(
            ocr_conf=field.get("confidence", 0.5),
            quality_status=diag.get("quality", {}).get("status", "PASS"),
            validation_status=val_res["status"],
            extraction_method=field.get("strategy", "anchor"),
            pattern_match=(len(val_res["warnings"]) == 0),
            visual_diff=field.get("visual_diff")
        )
        
        # PHASE 11: Snippet Extraction
        snippet_b64 = self._extract_snippet(img_bgr, field.get("bbox"))

        field.update({
            "cleaned_value": val_res["cleaned"],
            "status": val_res["status"],
            "errors": val_res["errors"],
            "warnings": val_res["warnings"],
            "confidence": conf_res["score"],
            "signals": conf_res["signals"],
            "snippet": snippet_b64
        })
        return field

    def _extract_snippet(self, img_bgr: np.ndarray, bbox: Optional[List]) -> Optional[str]:
        """Phase 11: Extracts a small crop of the image for human review."""
        if not bbox or not isinstance(bbox[0], (int, float)): # Rect format [x1,y1,x2,y2]
            return None
            
        h, w = img_bgr.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # Phase 11: Dynamic padding max(20% of dimension, 30px)
        bw = x2 - x1
        bh = y2 - y1
        pad_x = max(int(bw * 0.2), 30)
        pad_y = max(int(bh * 0.2), 30)
        
        x1_p, y1_p = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2_p, y2_p = min(w, x2 + pad_x), min(h, y2 + pad_y)
        
        crop = img_bgr[y1_p:y2_p, x1_p:x2_p]
        if crop.size == 0: return None
        
        _, encoded = cv2.imencode(".jpg", crop)
        return base64.b64encode(encoded).decode("utf-8")

    def _error_result(self, message: str, request_id: str) -> Dict[str, Any]:
        return {
            "request_id": request_id,
            "success": False,
            "error": message,
            "status": "REJECT",
            "decision": {"status": "REJECT", "reason": message}
        }

    # Backward compatibility helpers
    async def digitize_survey(self, image_b64: str) -> Dict[str, Any]:
        """Survey-specific alias for the main pipeline."""
        res = await self.digitize(image_b64)
        # Map v2 structure to old v1 structure if needed by frontend
        if "fields" in res:
            res["questions"] = res["fields"]
        return res
    def correct_field(self, request_id: str, field_id: str, new_value: str, user_id: str = "manual_review"):
        """Phase 11: Orchestrates manual correction and status re-evaluation."""
        logger.info(f"[{request_id}] Correcting field '{field_id}' to '{new_value}' by {user_id}")

        # 1. Update the database (persists value and logs audit trail)
        self.db.update_field(request_id, field_id, new_value, corrected_by=user_id)

        # 2. Re-evaluate overall status using Phase 8 logic
        current_fields = self.db.get_field_results(request_id)

        # 3. Run Decision Engine on updated fields
        new_decision = self.decision_engine.decide(current_fields)

        # 4. Update overall status in DB
        final_status = new_decision["status"]
        if final_status == "AUTO_ACCEPT":
            final_status = "MANUALLY_APPROVED"

        self.db.update_request_status(request_id, final_status)

        # 5. Sync with StorageService (JSON) for Export consistency
        try:
            # We assume 'default' dataset for manual corrections from API
            # In a multi-tenant setup, we'd pass dataset_id here.
            dataset_id = "default"
            path = self.storage._scan_path(dataset_id, request_id)
            if self.storage._read_json(path):
                # Update the JSON directly to reflect corrections
                # This ensures ExcelExportService (which reads JSON) sees the changes
                from services.storage import _read_json, _write_json
                data = _read_json(path)
                data["status"] = "corrected"
                
                # Update field value in extractedData
                questions = data.get("extractedData", {}).get("questions", [])
                for q in questions:
                    if q.get("id") == field_id or q.get("field_id") == field_id:
                        q["selected"] = new_value
                        q["status"] = "CORRECTED"
                
                _write_json(path, data)
                logger.info(f"[{request_id}] Synced correction to storage JSON")
        except Exception as sync_exc:
            logger.warning(f"[{request_id}] Failed to sync correction to JSON storage: {sync_exc}")

        return {
            "success": True,
            "new_status": final_status,
            "decision": new_decision
        }
