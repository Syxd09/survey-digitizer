"""
Phase 9 — Storage & Data Model (PostgreSQL/Supabase)
====================================================
Production-grade persistence layer with:
- Request + Field schema with audit trail
- Stage trace table for pipeline observability
- Pagination, cursor-based listing
- Idempotency check by image hash
"""

import os
from sqlalchemy import create_engine, Column, String, Float, JSON, DateTime, ForeignKey, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List, Optional
import json
import logging
from config import settings

logger = logging.getLogger(__name__)


Base = declarative_base()


class RequestModel(Base):
    __tablename__ = "requests"

    request_id = Column(String, primary_key=True)
    image_hash = Column(String, unique=True, index=True)
    status = Column(String, default="PENDING")
    overall_conf = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    trace = Column(JSON)  # Stores file_path, timing, etc.

    fields = relationship("FieldModel", back_populates="request", cascade="all, delete-orphan")
    stage_traces = relationship("StageTraceModel", back_populates="request", cascade="all, delete-orphan")


class FieldModel(Base):
    __tablename__ = "fields"

    id = Column(String, primary_key=True)  # request_id:field_id
    request_id = Column(String, ForeignKey("requests.request_id"))
    field_id = Column(String)
    raw_text = Column(Text)
    cleaned_text = Column(Text)
    field_conf = Column(Float)
    bbox = Column(JSON)
    status = Column(String)  # VALID, NEEDS_REVIEW, CORRECTED

    # Phase 11: Audit trail columns
    corrected_by = Column(String, nullable=True)
    corrected_at = Column(DateTime, nullable=True)
    previous_value = Column(Text, nullable=True)

    request = relationship("RequestModel", back_populates="fields")


class StageTraceModel(Base):
    """Phase 12: Stage-level traceability for pipeline observability."""
    __tablename__ = "stage_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, ForeignKey("requests.request_id"), index=True)
    stage = Column(String)        # "preprocessing", "ocr", "extraction", etc.
    status = Column(String)       # "SUCCESS", "FAIL", "SKIPPED"
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("RequestModel", back_populates="stage_traces")


class DatabaseService:
    def __init__(self, db_url: Optional[str] = None):

        self.db_url = db_url or os.getenv("DATABASE_URL")
        
        # If no URL provided, default to SQLite
        if not self.db_url:
            self.db_url = f"sqlite:///{settings.DB_PATH}"
            logger.info(f"[DB] No DATABASE_URL found. Using local SQLite: {settings.DB_PATH}")

        # Phase 15 Hardening: Pool settings for Supabase PgBouncer
        connect_args = {}
        if "sqlite" in self.db_url:
            connect_args = {"check_same_thread": False}

        try:
            # Phase 15 Hardening: Pool settings for Supabase PgBouncer
            engine_args = {
                "connect_args": connect_args
            }
            if "sqlite" not in self.db_url:
                engine_args["pool_size"] = 10
                engine_args["max_overflow"] = 20
            
            self.engine = create_engine(self.db_url, **engine_args)
            # Test connection
            with self.engine.connect() as conn:
                pass
            logger.info(f"[DB] Connected to {self.db_url.split('@')[-1] if '@' in self.db_url else 'SQLite'}")
        except Exception as e:
            if "sqlite" not in self.db_url:
                logger.warning(f"[DB] Failed to connect to primary DB ({e}). Falling back to SQLite.")
                self.db_url = f"sqlite:///{settings.DB_PATH}"
                self.engine = create_engine(
                    self.db_url,
                    connect_args={"check_same_thread": False}
                )
            else:
                logger.error(f"[DB] Critical error initialising database: {e}")
                raise e

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)


    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)

    # ── Idempotency ──────────────────────────────────────────────────────────

    def check_idempotency(self, image_hash: str) -> Optional[str]:
        session = self.SessionLocal()
        try:
            req = session.query(RequestModel).filter_by(image_hash=image_hash).first()
            return req.request_id if req else None
        finally:
            session.close()

    # ── Request CRUD ─────────────────────────────────────────────────────────

    def save_request(self, request_id: str, data: dict, image_hash: Optional[str] = None):
        session = self.SessionLocal()
        try:
            # Upsert logic
            req = session.query(RequestModel).filter_by(request_id=request_id).first()
            if not req:
                req = RequestModel(request_id=request_id)
                session.add(req)

            if image_hash:
                req.image_hash = image_hash

            req.status = data.get("status") or data.get("decision", {}).get("status", req.status)
            req.overall_conf = data.get("overall_conf") or data.get("decision", {}).get("overall_confidence", req.overall_conf)
            req.trace = data.get("trace", req.trace)

            # Sync fields
            if "fields" in data:
                # Remove old fields
                session.query(FieldModel).filter_by(request_id=request_id).delete()
                for f in data["fields"]:
                    field = FieldModel(
                        id=f"{request_id}:{f['id']}",
                        request_id=request_id,
                        field_id=f["id"],
                        raw_text=f.get("raw_value") or f.get("raw_text"),
                        cleaned_text=f.get("cleaned_value") or f.get("cleaned_text"),
                        field_conf=f.get("confidence") or f.get("field_conf", 0.0),
                        bbox=f.get("bbox"),
                        status=f.get("status", "VALID")
                    )
                    session.add(field)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_request(self, request_id: str) -> Optional[dict]:
        session = self.SessionLocal()
        try:
            req = session.query(RequestModel).filter_by(request_id=request_id).first()
            if not req:
                return None

            return {
                "request_id": req.request_id,
                "status": req.status,
                "overall_conf": req.overall_conf,
                "created_at": req.created_at.isoformat(),
                "trace": req.trace,
                "fields": [
                    {
                        "id": f.field_id,
                        "raw_text": f.raw_text,
                        "cleaned_text": f.cleaned_text,
                        "field_conf": f.field_conf,
                        "bbox": f.bbox,
                        "status": f.status,
                        "corrected_by": f.corrected_by,
                        "corrected_at": f.corrected_at.isoformat() if f.corrected_at else None,
                        "previous_value": f.previous_value,
                    } for f in req.fields
                ]
            }
        finally:
            session.close()

    def list_requests(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[dict]:
        """Phase 9/11: Paginated request listing with optional status filter."""
        session = self.SessionLocal()
        try:
            query = session.query(RequestModel)
            if status:
                query = query.filter_by(status=status)

            results = query.order_by(RequestModel.created_at.desc()).offset(offset).limit(limit).all()
            return [
                {
                    "request_id": r.request_id,
                    "status": r.status,
                    "overall_conf": r.overall_conf,
                    "created_at": r.created_at.isoformat()
                } for r in results
            ]
        finally:
            session.close()

    # ── Field Operations ─────────────────────────────────────────────────────

    def update_field(self, request_id: str, field_id: str, cleaned_text: str, corrected_by: str = "system"):
        """Phase 11: Update field with full audit trail (old value, who, when)."""
        session = self.SessionLocal()
        try:
            field = session.query(FieldModel).filter_by(request_id=request_id, field_id=field_id).first()
            if field:
                # Preserve old value for audit
                field.previous_value = field.cleaned_text
                field.cleaned_text = cleaned_text
                field.status = "CORRECTED"
                field.corrected_by = corrected_by
                field.corrected_at = datetime.utcnow()
                session.commit()
                logger.info(
                    f"[DB] Field {field_id} corrected by {corrected_by}: "
                    f"'{field.previous_value}' → '{cleaned_text}'"
                )
            else:
                logger.warning(f"[DB] Field {field_id} not found for request {request_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"[DB] Failed to update field {field_id}: {e}")
            raise
        finally:
            session.close()

    def get_field_results(self, request_id: str) -> List[dict]:
        """Phase 11: Get all field results for re-evaluation by DecisionEngine."""
        session = self.SessionLocal()
        try:
            fields = session.query(FieldModel).filter_by(request_id=request_id).all()
            return [
                {
                    "id": f.field_id,
                    "raw_value": f.raw_text,
                    "cleaned_value": f.cleaned_text,
                    "confidence": f.field_conf,
                    "bbox": f.bbox,
                    "status": f.status,
                } for f in fields
            ]
        finally:
            session.close()

    # ── Request Status ───────────────────────────────────────────────────────

    def update_request_status(self, request_id: str, status: str):
        """Phase 11: Update overall request status after correction re-evaluation."""
        session = self.SessionLocal()
        try:
            req = session.query(RequestModel).filter_by(request_id=request_id).first()
            if req:
                req.status = status
                session.commit()
                logger.info(f"[DB] Request {request_id} status → {status}")
            else:
                logger.warning(f"[DB] Request {request_id} not found for status update")
        finally:
            session.close()

    # ── Stage Tracing ────────────────────────────────────────────────────────

    def save_stage_trace(self, request_id: str, stage: str, status: str, duration_ms: int):
        """Phase 12: Persist pipeline stage execution trace."""
        session = self.SessionLocal()
        try:
            trace = StageTraceModel(
                request_id=request_id,
                stage=stage,
                status=status,
                duration_ms=duration_ms,
            )
            session.add(trace)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[DB] Failed to save stage trace: {e}")
        finally:
            session.close()

    def get_stage_traces(self, request_id: str) -> List[dict]:
        """Phase 12: Retrieve all stage traces for a request."""
        session = self.SessionLocal()
        try:
            traces = session.query(StageTraceModel).filter_by(request_id=request_id).order_by(StageTraceModel.id).all()
            return [
                {
                    "stage": t.stage,
                    "status": t.status,
                    "duration_ms": t.duration_ms,
                    "created_at": t.created_at.isoformat(),
                } for t in traces
            ]
        finally:
            session.close()
