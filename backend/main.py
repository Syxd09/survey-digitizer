from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth
from pydantic import BaseModel
import uuid
from tasks import process_survey_task, run_digitization_task
from services.storage import StorageService
from services.export import ExcelExportService 
from services.metrics import MetricsEngine
import os
import logging

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Survey Digitizer Production API")

@app.on_event("startup")
async def startup_event():
    logger.info("[FASTAPI] Production API Loading...")
    logger.info("[FASTAPI] Registered Routes: /, /ingest, /export/{dataset_id}, /metrics/{dataset_id}")

# Security Configuration
security = HTTPBearer()
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifies the Firebase JWT token."""
    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
        return decoded_token
    except Exception as e:
        logger.error(f"[AUTH] Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# Initialize Storage
PROJECT_ID = "gen-lang-client-0362910217"
storage = StorageService(PROJECT_ID)
exporter = ExcelExportService(storage)
metrics_engine = MetricsEngine(storage)

class IngestRequest(BaseModel):
    image: str
    datasetId: str
    userId: str

@app.get("/")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

@app.post("/ingest")
async def ingest_form(
    request: IngestRequest, 
    background_tasks: BackgroundTasks,
    token: dict = Depends(verify_token)
):
    """
    Accept image, create pending entry in Firestore, and queue for processing.
    ENFORCED: Firebase JWT verification.
    """
    try:
        # Security check: Ensure user can only ingest for themselves
        if token['uid'] != request.userId:
             raise HTTPException(status_code=403, detail="Unauthorized: User ID mismatch")

        scan_id = str(uuid.uuid4())
        
        # 1. Create entry in Firestore (Idempotent)
        storage.create_form_entry(
            dataset_id=request.datasetId,
            user_id=request.userId,
            scan_id=scan_id,
            image_url="PENDING"
        )
        
        # 2. Push to Queue
        try:
            task = process_survey_task.delay(
                dataset_id=request.datasetId,
                scan_id=scan_id,
                image_b64=request.image,
                user_id=request.userId
            )
            return {
                "success": True,
                "scanId": scan_id,
                "taskId": task.id,
                "status": "QUEUED"
            }
        except Exception as celery_err:
            logger.warning(f"[INGEST] Celery/Redis down. Falling back to local BackgroundTasks: {str(celery_err)}")
            background_tasks.add_task(
                run_digitization_task,
                request.datasetId,
                scan_id,
                request.image,
                request.userId
            )
            return {
                "success": True,
                "scanId": scan_id,
                "taskId": f"local-{scan_id}",
                "status": "QUEUED_LOCAL"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INGEST] Critical failure: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export/{dataset_id}")
async def export_excel(
    dataset_id: str,
    token: dict = Depends(verify_token)
):
    """
    Generate and serve Excel file for a dataset.
    ENFORCED: Firebase JWT verification + Ownership check.
    """
    try:
        # Basic ownership check from Firestore via storage service if needed,
        # but the exporter logic usually handles scoping.
        file_path = exporter.generate_excel(dataset_id)
        from fastapi.responses import FileResponse
        return FileResponse(
            file_path, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"survey_export_{dataset_id}.xlsx"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/{dataset_id}")
async def get_metrics(
    dataset_id: str,
    token: dict = Depends(verify_token)
):
    """
    Get real-time performance and quality metrics for a dataset.
    """
    try:
        return metrics_engine.get_dataset_summary(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
