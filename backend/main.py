"""
Survey Digitizer OCR API — Hydra v11.0 PRODUCTION
===================================================

Key architectural decisions
────────────────────────────
1. Models loaded ONCE at startup via FastAPI lifespan context.
   No model loading happens inside request handlers.

2. All CPU-bound OCR work dispatched to a ThreadPoolExecutor via
   asyncio.run_in_executor() — the uvicorn event loop is never blocked.

3. ExtractionOrchestrator is injected via FastAPI dependency, ensuring
   every handler gets the same pre-warmed singleton.

4. Structured JSON error responses on all failure paths.
"""

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Application state (populated in lifespan) ─────────────────────────────────

class AppState:
    orchestrator: Any = None
    storage:      Any = None
    metrics:      Any = None
    exporter:     Any = None
    executor:     Optional[ThreadPoolExecutor] = None


app_state = AppState()


# ── WebSocket Connection Manager ─────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time push updates."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients."""
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


ws_manager = ConnectionManager()


# ── FastAPI lifespan — runs once at startup, tears down at shutdown ───────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load all heavy models here.  Everything inside this context runs once.
    Request handlers read from app_state which is already fully initialised
    by the time the first request arrives.
    """
    logger.info("═" * 60)
    logger.info("[STARTUP] Initialising Hydra OCR pipeline ...")

    # Thread pool for blocking OCR work (4 workers is a safe default;
    # increase to match your CPU core count for higher throughput)
    app_state.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocr")

    # Load the processor in a thread so the event loop stays responsive
    loop = asyncio.get_event_loop()
    try:
        from services.processor import SurveyProcessor
        processor = await loop.run_in_executor(app_state.executor, SurveyProcessor)
        logger.info("[STARTUP] SurveyProcessor ready")
    except Exception as exc:
        logger.critical(f"[STARTUP] Processor init failed: {exc}")
        raise RuntimeError("OCR engine failed to initialise") from exc

    from services.orchestrator import ExtractionOrchestrator
    from services.storage      import StorageService
    from services.metrics      import MetricsEngine
    from services.export       import ExcelExportService

    app_state.orchestrator = ExtractionOrchestrator(processor, app_state.executor)
    app_state.storage      = StorageService()
    app_state.metrics      = MetricsEngine(app_state.storage)
    app_state.exporter     = ExcelExportService(app_state.storage)

    logger.info("[STARTUP] All services ready — accepting requests")
    logger.info("═" * 60)

    yield   # ← application runs here

    logger.info("[SHUTDOWN] Shutting down thread pool ...")
    app_state.executor.shutdown(wait=True)
    logger.info("[SHUTDOWN] Done")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Survey Digitizer OCR API",
    version="11.0.0",
    description="Local high-accuracy OCR for survey forms (Hydra v11)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Dependency ────────────────────────────────────────────────────────────────

def get_orchestrator():
    if app_state.orchestrator is None:
        raise HTTPException(status_code=503, detail="OCR engine not ready")
    return app_state.orchestrator

def get_storage():
    if app_state.storage is None:
        raise HTTPException(status_code=503, detail="Storage not ready")
    return app_state.storage

def get_metrics():
    if app_state.metrics is None:
        raise HTTPException(status_code=503, detail="Metrics not ready")
    return app_state.metrics

def get_exporter():
    if app_state.exporter is None:
        raise HTTPException(status_code=503, detail="Exporter not ready")
    return app_state.exporter


# ── Pydantic models ───────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    image:     str = Field(..., description="Base64-encoded image (with or without data-URI prefix)")
    datasetId: str = Field("default", description="Dataset to associate this scan with")
    userId:    str = Field("anon",    description="User submitting the scan")
    returnRaw: bool = False

class IngestRequest(BaseModel):
    image:     str
    datasetId: str = "default"
    userId:    str = "anon"

class FeedbackRequest(BaseModel):
    scanId:        str
    questionId:    str
    correctedText: str
    imageHash:     str = Field(..., description="dhash of the crop being corrected")

class ExportRequest(BaseModel):
    datasetId: str


# ── Health endpoints ──────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"status": "healthy", "version": "11.0.0", "engine": "LOCAL_HYDRA_V11"}

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status":       "ok",
        "engine":       "LOCAL_HYDRA_V11",
        "models_ready": app_state.orchestrator is not None,
    }


# ── Main processing endpoint ──────────────────────────────────────────────────

@app.post("/process", tags=["OCR"])
async def process_image(
    request:      ProcessRequest,
    orchestrator = Depends(get_orchestrator),
    storage      = Depends(get_storage),
):
    """
    Synchronous endpoint: process image and return OCR results immediately.
    Uses run_in_executor internally so the event loop stays non-blocking.
    """
    scan_id = str(uuid.uuid4())

    try:
        result    = await orchestrator.digitize(request.image)
        questions = result.get("questions", [])
        diag      = result.get("diagnostics", {})

        # Persist result
        try:
            storage.create_form_entry(request.datasetId, request.userId, scan_id, "")
            storage.update_scan_results(request.datasetId, scan_id, result, diag)
        except Exception as store_exc:
            logger.warning(f"[PROCESS] Storage write failed (non-fatal): {store_exc}")

        return {
            "success":      True,
            "scanId":       scan_id,
            "questions":    questions,
            "total":        len(questions),
            "avgConfidence": diag.get("avg_confidence", 0),
            "nullRate":     diag.get("null_rate", 1.0),
            "diagnostics":  diag,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[PROCESS] Unhandled error for scan {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Survey processing endpoint ────────────────────────────────────────────

class SurveyProcessRequest(BaseModel):
    image:     str = Field(..., description="Base64-encoded image")
    datasetId: str = Field("default", description="Dataset to associate this scan with")
    userId:    str = Field("anon", description="User submitting the scan")

class ApproveRequest(BaseModel):
    scanId:    str
    datasetId: str = "default"
    questions: list = Field(..., description="Reviewed/edited survey questions")
    corrections: Optional[list] = Field(None, description="List of dicts containing {originalText, correctedText} to train the LLM")


@app.post("/process-survey", tags=["OCR"])
async def process_survey(
    request:      SurveyProcessRequest,
    orchestrator = Depends(get_orchestrator),
    storage      = Depends(get_storage),
):
    """
    Process image specifically as a survey form.
    Returns structured survey data with question numbers, text, and selected answers.
    """
    scan_id = str(uuid.uuid4())

    try:
        result    = await orchestrator.digitize_survey(request.image)
        questions = result.get("questions", [])
        survey    = result.get("survey_data", {})
        diag      = result.get("diagnostics", {})

        # Persist
        try:
            storage.create_form_entry(request.datasetId, request.userId, scan_id, "")
            storage.update_scan_results(request.datasetId, scan_id, result, diag)
        except Exception as store_exc:
            logger.warning(f"[SURVEY] Storage write failed (non-fatal): {store_exc}")

        return {
            "success":       True,
            "scanId":        scan_id,
            "questions":     questions,
            "survey_data":   survey,
            "total":         len(questions),
            "avgConfidence": diag.get("avg_confidence", 0),
            "diagnostics":   diag,
        }
    except Exception as exc:
        logger.error(f"[SURVEY] Error for scan {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/approve-survey", tags=["OCR"])
async def approve_survey(
    request: ApproveRequest,
    storage = Depends(get_storage),
):
    """
    Save reviewed/edited survey results after human approval.
    """
    try:
        # 1. Update storage with approved results
        result = {
            "questions": request.questions,
            "status": "approved",
        }
        storage.update_scan_results(
            request.datasetId, request.scanId, result,
            {"approved": True, "status": "approved"}
        )
        
        # 2. Add corrections to Active Learning Memory
        if request.corrections:
            from services.llm_semantic_refiner import get_semantic_refiner
            refiner = get_semantic_refiner()
            for c in request.corrections:
                orig = c.get("originalText")
                corr = c.get("correctedText")
                if orig and corr:
                    refiner.add_correction(orig, corr)

        return {"success": True, "scanId": request.scanId, "status": "approved"}
    except Exception as exc:
        logger.error(f"[APPROVE] Failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Background ingest endpoint ────────────────────────────────────────────────

@app.post("/ingest", tags=["OCR"])
async def ingest_form(
    request:          IngestRequest,
    background_tasks: BackgroundTasks,
    orchestrator     = Depends(get_orchestrator),
    storage          = Depends(get_storage),
):
    """
    Fire-and-forget: accept the image, return a scanId immediately,
    process in the background.
    """
    scan_id = str(uuid.uuid4())

    try:
        storage.create_form_entry(request.datasetId, request.userId, scan_id, "")
        storage.update_status(request.datasetId, scan_id, "processing")
    except Exception as exc:
        logger.warning(f"[INGEST] Storage init failed: {exc}")

    async def _bg_task():
        try:
            # Always use survey pipeline to ensure LLM refinement is applied
            result = await orchestrator.digitize_survey(request.image)
            diag   = result.get("diagnostics", {})
            storage.update_scan_results(request.datasetId, scan_id, result, diag)
            logger.info(
                f"[INGEST] {scan_id} done — "
                f"{len(result.get('questions', []))} fields"
            )

            # Push real-time update to all connected WebSocket clients
            from services.storage import _read_json
            scan_data = _read_json(storage._scan_path(request.datasetId, scan_id))
            await ws_manager.broadcast({
                "type": "scan_complete",
                "scanId": scan_id,
                "data": scan_data
            })
        except Exception as exc:
            logger.error(f"[INGEST] Background task failed for {scan_id}: {exc}")
            try:
                storage.mark_failed(request.datasetId, scan_id, str(exc))
                await ws_manager.broadcast({
                    "type": "scan_failed",
                    "scanId": scan_id,
                    "error": str(exc)
                })
            except Exception:
                pass

    background_tasks.add_task(_bg_task)
    return {"success": True, "scanId": scan_id, "status": "PROCESSING"}


# ── Scan status & listing endpoints ───────────────────────────────────────────

@app.get("/scan/{dataset_id}/{scan_id}", tags=["Scans"])
async def get_scan(
    dataset_id: str,
    scan_id:    str,
    storage    = Depends(get_storage),
):
    status = storage.get_scan_status(dataset_id, scan_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    from services.storage import _read_json
    data = _read_json(storage._scan_path(dataset_id, scan_id))
    return data or {"scanId": scan_id, "status": status}

@app.get("/list/{dataset_id}", tags=["Scans"])
async def list_scans(
    dataset_id: str,
    storage    = Depends(get_storage),
):
    """
    Retrieve all scans associated with a specific dataset.
    Used by the Vault and Workbench for history and batch processing.
    """
    return storage.get_all_scans(dataset_id)


# ── Feedback / active learning endpoint ──────────────────────────────────────

@app.post("/feedback", tags=["Learning"])
async def register_feedback(
    request:     FeedbackRequest,
    orchestrator = Depends(get_orchestrator),
):
    """
    Register a user correction so Hydra learns the pattern.
    imageHash identifies the visual crop; correctedText is the ground truth.
    """
    success = orchestrator.register_correction(request.imageHash, request.correctedText)
    return {
        "success": success,
        "message": "Pattern learned." if success else "Failed to save pattern.",
    }


# ── Metrics endpoint ──────────────────────────────────────────────────────────

@app.get("/metrics/{dataset_id}", tags=["Metrics"])
async def get_metrics(
    dataset_id: str,
    metrics    = Depends(get_metrics),
):
    return metrics.get_dataset_summary(dataset_id)


# ── Export endpoint ───────────────────────────────────────────────────────────

@app.post("/export", tags=["Export"])
async def export_excel(
    request:   ExportRequest,
    exporter  = Depends(get_exporter),
):
    """
    Export validated scans for a dataset to an Excel workbook.
    Returns the file as a download.
    """
    try:
        loop      = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(
            app_state.executor,
            exporter.generate_excel,
            request.datasetId,
        )
        return FileResponse(
            path=file_path,
            filename=f"{request.datasetId}_export.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        logger.error(f"[EXPORT] Failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time push channel. Replaces polling for scan status, vault, and metrics.
    
    Messages FROM server:
      - {"type": "scan_complete", "scanId": "...", "data": {...}}
      - {"type": "scan_failed", "scanId": "...", "error": "..."}
      - {"type": "vault_update", "data": [...]}
      - {"type": "metrics_update", "data": {...}}
      - {"type": "pong"}

    Messages FROM client:
      - {"type": "ping"} → keepalive
      - {"type": "request_vault"} → trigger vault refresh
      - {"type": "request_metrics"} → trigger metrics refresh
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "request_vault":
                try:
                    storage = app_state.storage
                    scans = storage.get_all_scans("default-authority")
                    await websocket.send_json({
                        "type": "vault_update",
                        "data": scans
                    })
                except Exception as e:
                    logger.warning(f"[WS] Vault fetch failed: {e}")

            elif msg_type == "request_metrics":
                try:
                    metrics_svc = app_state.metrics
                    m = metrics_svc.get_dataset_summary("default-authority")
                    await websocket.send_json({
                        "type": "metrics_update",
                        "data": m
                    })
                except Exception as e:
                    logger.warning(f"[WS] Metrics fetch failed: {e}")

            elif msg_type == "request_scan_status":
                try:
                    scan_id = data.get("scanId")
                    storage = app_state.storage
                    from services.storage import _read_json
                    scan_data = _read_json(storage._scan_path("default-authority", scan_id))
                    if scan_data:
                        await websocket.send_json({
                            "type": "scan_update",
                            "scanId": scan_id,
                            "data": scan_data
                        })
                except Exception as e:
                    logger.warning(f"[WS] Scan status fetch failed: {e}")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"[WS] Connection error: {e}")
        ws_manager.disconnect(websocket)


# ── Dev server entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,       # disable reload in production — it restarts models
        log_level="info",
    )