from celery_app import celery_app
from services.processor import SurveyProcessor
from services.storage import StorageService
import base64
import io
from PIL import Image as PILImage
import os
import time

import asyncio
from services.orchestrator import ExtractionOrchestrator

# Initialize services
orchestrator = ExtractionOrchestrator()
# User Logic Version
LOGIC_VERSION = "Hydra-v2.0"
# Use project id
project_id = "gen-lang-client-0362910217"
storage = StorageService(project_id)

def run_digitization_task(dataset_id: str, scan_id: str, image_b64: str, user_id: str):
    """
    Standalone digitization logic that can be run by Celery or directly by FastAPI.
    """
    start_time = time.time()
    try:
        # 1. Idempotency Check
        current_status = storage.get_scan_status(dataset_id, scan_id)
        if current_status and current_status not in ["failed", "uploaded"]:
            print(f"[IDEMPOTENCY] Skipping scan_id {scan_id}. Current status: {current_status}")
            return {"status": "skipped", "reason": "already_processed", "scan_id": scan_id}

        # 2. Update Status: PROCESSING
        storage.update_status(dataset_id, scan_id, "PROCESSING")

        # 3. Process Image with Hydra AI Orchestrator
        result = asyncio.run(orchestrator.digitize(image_b64))
        result["logic_version"] = LOGIC_VERSION
        
        # 4. Validation Metrics
        questions = result.get("questions", [])
        null_count = sum(1 for q in questions if q.get("selected") is None)
        null_rate = null_count / len(questions) if questions else 0
        avg_conf = sum(q.get("confidence", 0) for q in questions) / len(questions) if questions else 0
        
        duration = time.time() - start_time
        diagnostics = result.get("diagnostics", {})
        diagnostics.update({
            "null_rate": null_rate,
            "avg_confidence": avg_conf,
            "processing_duration": round(duration, 2),
            "logic_version": LOGIC_VERSION,
            "timestamp": time.time()
        })

        # 5. Save to Firestore with VALIDATED status gate
        storage.update_scan_results(dataset_id, scan_id, result, diagnostics)
        
        return {
            "status": "success", 
            "scan_id": scan_id, 
            "duration": round(duration, 2),
            "logic_version": LOGIC_VERSION
        }
    except Exception as exc:
        storage.mark_failed(dataset_id, scan_id, str(exc))
        storage.log_activity("CRITICAL_FAILURE", f"Scan {scan_id} failed: {str(exc)}", "outline")
        raise exc

@celery_app.task(
    bind=True, 
    max_retries=3, 
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True
)
def process_survey_task(self, dataset_id: str, scan_id: str, image_b64: str, user_id: str):
    """
    Asynchronous task wrapper for Celery.
    """
    return run_digitization_task(dataset_id, scan_id, image_b64, user_id)
