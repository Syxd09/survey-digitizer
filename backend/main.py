"""
Survey Digitizer OCR API — v2.0 Production
=============================================

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
import os
import uuid
import time
import functools
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from config import settings
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Application state (populated in lifespan) ─────────────────────────────────

class AppState:
    orchestrator: Any = None
    db:           Any = None
    obs:          Any = None
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
    logger.info("[STARTUP] Initialising OCR pipeline v2.0 ...")

    # Thread pool for blocking OCR work (4 workers is a safe default;
    # increase to match your CPU core count for higher throughput)
    app_state.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocr")

    # ═ Pipeline v2.0 Initialisation ═

    from services.orchestrator import ExtractionOrchestrator
    from services.db_service import get_db_service
    from services.observability import get_observability_service
    from services.storage import StorageService
    from services.metrics import MetricsEngine
    from services.export import ExcelExportService

    app_state.db = get_db_service()
    app_state.obs = get_observability_service()
    app_state.orchestrator = ExtractionOrchestrator(app_state.executor)
    app_state.storage = StorageService()
    app_state.metrics = MetricsEngine(app_state.storage)
    app_state.exporter = ExcelExportService(app_state.storage)

    logger.info("[STARTUP] All services ready — accepting requests")
    logger.info("═" * 60)

    yield   # ← application runs here

    logger.info("[SHUTDOWN] Shutting down thread pool ...")
    app_state.executor.shutdown(wait=True)
    logger.info("[SHUTDOWN] Done")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Survey Digitizer OCR API",
    version="2.0.0",
    description="High-accuracy OCR pipeline for survey forms (v2.0)",
    lifespan=lifespan,
)


# Phase 15: File size limit middleware (10MB default)
_MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={"status": "error", "code": "payload_too_large", "message": f"File too large. Max {_MAX_UPLOAD_BYTES // (1024*1024)}MB."}
            )
    return await call_next(request)

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Phase 15 Security: X-API-Key check
    _skip = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
    if request.method == "OPTIONS" or request.url.path in _skip:
        return await call_next(request)
    
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key != settings.API_KEY:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "code": "unauthorized", "message": "Invalid or missing X-API-Key"}
        )
    return await call_next(request)


# Phase 15: Configurable CORS origins (Outer-most middleware)
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
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
    scanId:            str
    questionId:        str
    originalQuestion:  Optional[str] = None
    correctedQuestion: Optional[str] = None
    originalAnswer:    Optional[str] = None
    correctedAnswer:   Optional[str] = None
    imageHash:         str = Field(..., description="dhash of the crop being corrected")

class ExportRequest(BaseModel):
    datasetId: str


# ── Health endpoints ──────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"status": "healthy", "version": "2.0.0", "engine": "PIPELINE_V2"}

@app.get("/health", tags=["Health"])
async def health():
    # Phase 14: Include cache connectivity status
    cache_ok = False
    try:
        from services.cache_service import get_cache_service
        cache_ok = get_cache_service().is_connected
    except Exception:
        pass

    return {
        "status":       "ok",
        "engine":       "PIPELINE_V2",
        "models_ready": app_state.orchestrator is not None,
        "cache_status":  "connected" if cache_ok else "disconnected",
    }


# ── Main processing endpoint ──────────────────────────────────────────────────

@app.post("/process", tags=["OCR"])
async def process_image(
    request: ProcessRequest,
    orchestrator = Depends(get_orchestrator),
):
    """
    V2.0 Pipeline: Returns detailed trace, confidence maps, and decision.
    """
    request_id = str(uuid.uuid4())
    try:
        result = await orchestrator.digitize(request.image, request_id)
        return {
            "success": True,
            "scanId": request_id,
            "requestId": request_id,
            "status": result.get("decision", {}).get("status"),
            "decision": result.get("decision"),
            "data": result,
            "traceLink": f"/scan/{request.datasetId}/{request_id}"
        }
    except Exception as exc:
        logger.error(f"[PROCESS] Pipeline failed for {request_id}: {exc}")
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


# ── Phase 15: Security & Rate Limiting ───────────────────────────────────────
from collections import defaultdict

rate_limit_store = defaultdict(list)

_RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "20"))

def rate_limit(requests_per_minute: int = _RATE_LIMIT_RPM):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Phase 15: Extract real client IP from FastAPI's DI kwargs
            # FastAPI injects Request as a kwarg matching the parameter name
            req = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            client_ip = "unknown"
            if req and hasattr(req, "client") and req.client:
                client_ip = req.client.host
            now = time.time()
            rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < 60]
            if len(rate_limit_store[client_ip]) >= requests_per_minute:
                logger.warning(f"[Phase 15] Rate limit exceeded for {client_ip}")
                raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
            rate_limit_store[client_ip].append(now)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


@app.post("/process-survey", tags=["OCR"])
@rate_limit(requests_per_minute=20)
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
            await run_in_threadpool(storage.create_form_entry, request.datasetId, request.userId, scan_id, "")
            await run_in_threadpool(storage.update_scan_results, request.datasetId, scan_id, result, diag)
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
def approve_survey(
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
    db               = Depends(lambda: app_state.db),
):
    """
    Phase 10/14: Fire-and-forget background processing.
    """
    request_id = str(uuid.uuid4())
    
    # 1. Initialise DB entry immediately
    await run_in_threadpool(db.save_request, request_id, {"status": "processing", "requestId": request_id})

    async def _bg_task():
        try:
            # 2. Execute full pipeline
            result = await orchestrator.digitize(request.image, request_id)
            
            # 3. Broadcast completion
            await ws_manager.broadcast({
                "type": "scan_complete",
                "scanId": request_id,
                "requestId": request_id,
                "status": result.get("decision", {}).get("status"),
                "data": result
            })
        except Exception as exc:
            logger.error(f"[INGEST] Background task failed for {request_id}: {exc}")
            # db update usually handled inside digitize error path, but double check
            await ws_manager.broadcast({
                "type": "scan_failed",
                "requestId": request_id,
                "error": str(exc)
            })

    background_tasks.add_task(_bg_task)
    return {"success": True, "scanId": request_id, "requestId": request_id, "status": "processing"}


# ── Scan status & listing endpoints ───────────────────────────────────────────

@app.get("/requests/{request_id}", tags=["Scans"])
def get_request_status(
    request_id: str,
    db = Depends(lambda: app_state.db),
):
    """Phase 10: Polling endpoint for background task status."""
    data = db.get_request(request_id)
    if not data:
        raise HTTPException(status_code=404, detail="Request not found")
    return data

@app.get("/scan/{dataset_id}/{scan_id}", tags=["Scans"])
def get_scan(
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

@app.get("/forms", tags=["Phase 9/11"])
def list_forms(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db = Depends(lambda: app_state.db)
):
    """Phase 9/11: List processed forms with cursor-based pagination."""
    requests = db.list_requests(status=status, limit=limit, offset=offset)
    return {
        "success": True,
        "count": len(requests),
        "limit": limit,
        "offset": offset,
        "data": requests
    }

@app.get("/list/{dataset_id}", tags=["Scans"])
def list_scans_alias(
    dataset_id: str,
    db = Depends(lambda: app_state.db),
):
    """Alias for /forms specifically formatted for the Vault frontend."""
    # Maps 'default-authority' (frontend) to 'default' (backend internal)
    ds_id = "default" if dataset_id == "default-authority" else dataset_id
    requests = db.list_requests(limit=100)
    # The frontend expects a flat array of status objects
    return requests

@app.get("/forms/{request_id}", tags=["Phase 9/11"])
def get_form_details(
    request_id: str,
    db = Depends(lambda: app_state.db)
):
    """Phase 11: Get full details for a form including field snippets and audit log."""
    data = db.get_request(request_id)
    if not data:
        raise HTTPException(status_code=404, detail="Form not found")
    return data

class CorrectionRequest(BaseModel):
    fieldId: str
    value: str
    userId: str = "human_editor"

@app.patch("/forms/{request_id}/correct", tags=["Phase 11"])
def correct_field(
    request_id: str,
    correction: CorrectionRequest,
    db = Depends(lambda: app_state.db)
):
    """Phase 11: Manual correction endpoint. Triggers status re-evaluation."""
    try:
        orchestrator = app_state.orchestrator
        res = orchestrator.correct_field(request_id, correction.fieldId, correction.value, correction.userId)
        return res
    except Exception as e:
        logger.error(f"[API] Correction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Debug & Audit endpoints ──────────────────────────────────────────

@app.get("/debug/bundle/{request_id}", tags=["Review"])
def download_debug_bundle(
    request_id: str,
    db = Depends(lambda: app_state.db),
    obs = Depends(lambda: app_state.obs)
):
    """Generates and returns a ZIP debug bundle."""
    path = obs.generate_debug_bundle(request_id, db)
    if not path:
        raise HTTPException(status_code=404, detail="Trace not found")
    return FileResponse(path, filename=f"debug_{request_id}.zip")

@app.get("/debug/overlay/{request_id}", tags=["Review"])
def get_debug_overlay(request_id: str):
    """Phase 12: Serves the debug overlay image with bounding boxes."""
    from services.observability import DEBUG_DIR
    path = os.path.join(DEBUG_DIR, f"{request_id}_debug_overlay.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Overlay not found")
    return FileResponse(path)

@app.get("/image/original/{request_id}", tags=["Review"])
def get_original_image(request_id: str, db = Depends(lambda: app_state.db)):
    """Serves the original uploaded image."""
    data = db.get_request(request_id)
    if not data or "trace" not in data or "file_path" not in data["trace"]:
        raise HTTPException(status_code=404, detail="Image not found")
    path = data["trace"]["file_path"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path)

@app.get("/image/snippet", tags=["Review"])
def get_snippet(request_id: str, field_id: str, db = Depends(lambda: app_state.db)):
    """Phase 11: Serves a cropped snippet for a specific field."""
    # In a real app, we'd crop on the fly or serve pre-cropped images.
    # For now, let's assume we crop on the fly from the original.
    data = db.get_request(request_id)
    if not data or "trace" not in data or "file_path" not in data["trace"]:
        raise HTTPException(status_code=404, detail="Image not found")
        
    # Find field bbox
    field = next((f for f in data.get("fields", []) if f["id"] == field_id), None)
    if not field or not field.get("bbox"):
        raise HTTPException(status_code=404, detail="Field or bbox not found")
        
    import cv2
    img = cv2.imread(data["trace"]["file_path"])
    x1, y1, x2, y2 = [int(v) for v in field["bbox"]]
    # Add margin
    h, w = img.shape[:2]
    margin = 20
    x1 = max(0, x1 - margin)
    y1 = max(0, y1 - margin)
    x2 = min(w, x2 + margin)
    y2 = min(h, y2 + margin)
    
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return JSONResponse(status_code=400, content={"error": "Empty crop region"})
    _, buffer = cv2.imencode(".jpg", crop)
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# ── Feedback / active learning endpoint ──────────────────────────────────────

@app.post("/feedback", tags=["Learning"])
def register_feedback(
    request: FeedbackRequest,
):
    """
    Register a user correction so the LLM semantic refiner learns the pattern.
    Handles dual-edits (both question/label and answer/value).
    """
    from services.llm_semantic_refiner import get_semantic_refiner
    refiner = get_semantic_refiner()

    success = False
    messages = []

    # If the user corrected the extracted answer
    if request.originalAnswer and request.correctedAnswer and request.originalAnswer != request.correctedAnswer:
        refiner.add_correction(request.originalAnswer, request.correctedAnswer)
        messages.append("Answer pattern learned.")
        success = True

    # If the user corrected the question label
    if request.originalQuestion and request.correctedQuestion and request.originalQuestion != request.correctedQuestion:
        refiner.add_correction(request.originalQuestion, request.correctedQuestion)
        messages.append("Question pattern learned.")
        success = True

    return {
        "success": success,
        "message": " ".join(messages) if success else "No changes to learn or failed to save pattern.",
    }


# ── Metrics endpoint ──────────────────────────────────────────────────────────

@app.get("/metrics/{dataset_id}", tags=["Metrics"])
def get_dataset_metrics(
    dataset_id: str,
    metrics    = Depends(get_metrics),
):
    return metrics.get_dataset_summary(dataset_id)


# ── Export endpoint ───────────────────────────────────────────────────────────

@app.get("/export", tags=["Export"])
async def export_excel(
    dataset_id: str = "default-authority",
    exporter  = Depends(get_exporter),
):
    """
    Export validated scans for a dataset to an Excel workbook.
    Returns the file as a download.
    """
    try:
        loop      = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(
            app_state.executor,
            exporter.generate_excel,
            dataset_id,
        )
        return FileResponse(
            path=file_path,
            filename=f"{dataset_id}_export.xlsx",
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