from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Survey Digitizer OCR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProcessRequest(BaseModel):
    image: str
    datasetId: str
    userId: str
    returnRaw: bool = False

@app.get("/")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok", "engine": "LOCAL_OCR"}

@app.post("/process")
async def process_image(request: ProcessRequest):
    """Process image directly and return OCR results."""
    try:
        from services.orchestrator import ExtractionOrchestrator
        orchestrator = ExtractionOrchestrator()
        
        result = await orchestrator.digitize(request.image)
        
        questions = result.get("questions", [])
        return {
            "success": True,
            "scanId": str(uuid.uuid4()),
            "questions": questions,
            "total": len(questions),
            "avgConfidence": sum(q.get("confidence", 0) for q in questions) / max(1, len(questions)),
            "diagnostics": result.get("diagnostics", {})
        }
    except Exception as e:
        logger.error(f"[PROCESS] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest")
async def ingest_form(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Ingest form and process in background."""
    scan_id = str(uuid.uuid4())
    
    async def process_task():
        try:
            from services.orchestrator import ExtractionOrchestrator
            orchestrator = ExtractionOrchestrator()
            result = await orchestrator.digitize(request.image)
            logger.info(f"[TASK] Processed {scan_id}: {len(result.get('questions', []))} questions")
        except Exception as e:
            logger.error(f"[TASK] Failed: {e}")
    
    background_tasks.add_task(process_task)
    
    return {
        "success": True,
        "scanId": scan_id,
        "taskId": f"bg-{scan_id}",
        "status": "PROCESSING"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
