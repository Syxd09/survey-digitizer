"""
StorageService
==============
Local JSON file storage for scan documents.
Interface is backward-compatible with the original implementation.

Improvements vs original:
  - Atomic writes (write-to-temp + rename) to prevent corruption on crash
  - Typed exceptions instead of bare except
  - UTC timestamps use datetime.UTC (Python 3.11+) with a 3.10 fallback
  - get_scans_by_status accepts a set or list equally
"""

import datetime
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
)


def _now_iso() -> str:
    try:
        return datetime.datetime.now(datetime.UTC).isoformat()
    except AttributeError:
        # Python < 3.11
        return datetime.datetime.utcnow().replace(
            tzinfo=datetime.timezone.utc
        ).isoformat()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_json(filepath: str) -> Optional[Any]:
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(f"[STORAGE] Read error {filepath}: {exc}")
        return None


def _write_json(filepath: str, data: Any) -> None:
    """
    Atomic write: dump to a temp file in the same directory, then rename.
    Prevents partial-write corruption on crash or disk-full.
    """
    _ensure_dir(os.path.dirname(filepath))
    dir_name  = os.path.dirname(filepath)
    fd, tmp   = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        os.replace(tmp, filepath)   # atomic on POSIX; best-effort on Windows
    except OSError as exc:
        logger.error(f"[STORAGE] Write error {filepath}: {exc}")
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class StorageService:
    def __init__(self, project_id: str = "local"):
        self.data_dir = DATA_DIR
        _ensure_dir(self.data_dir)
        self.is_mock = False
        logger.info(f"[STORAGE] JSON storage at: {self.data_dir}")

    # ─────────────────────────────────────────────────────────────────────────
    # Path helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _dataset_dir(self, dataset_id: str) -> str:
        return os.path.join(self.data_dir, "datasets", dataset_id)

    def _scan_path(self, dataset_id: str, scan_id: str) -> str:
        return os.path.join(self._dataset_dir(dataset_id), "scans", f"{scan_id}.json")

    def _error_log_path(self) -> str:
        return os.path.join(self.data_dir, "error_logs.json")

    def _activities_path(self) -> str:
        return os.path.join(self.data_dir, "activities.json")

    # ─────────────────────────────────────────────────────────────────────────
    # Core CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def get_scan_status(self, dataset_id: str, scan_id: str) -> Optional[str]:
        data = _read_json(self._scan_path(dataset_id, scan_id))
        if data:
            return data.get("status", "unknown")
        return None

    def create_form_entry(
        self,
        dataset_id: str,
        user_id: str,
        scan_id: str,
        image_url: str,
    ) -> str:
        _write_json(
            self._scan_path(dataset_id, scan_id),
            {
                "datasetId": dataset_id,
                "userId":    user_id,
                "scanId":    scan_id,
                "status":    "uploaded",
                "confidence": 0.0,
                "imageUrl":  image_url,
                "createdAt": _now_iso(),
                "lifecycle": [{"stage": "UPLOADED", "timestamp": _now_iso()}],
            },
        )
        return scan_id

    def update_status(
        self,
        dataset_id: str,
        scan_id: str,
        status: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        path = self._scan_path(dataset_id, scan_id)
        data = _read_json(path) or {}
        data["status"]        = status.lower()
        data["lastUpdatedAt"] = _now_iso()
        lifecycle             = data.get("lifecycle", [])
        lifecycle.append({
            "stage":     status.upper(),
            "timestamp": _now_iso(),
            "metadata":  metadata or {},
        })
        data["lifecycle"] = lifecycle
        _write_json(path, data)

    def update_scan_results(
        self,
        dataset_id: str,
        scan_id: str,
        results: Dict[str, Any],
        diagnostics: Dict[str, Any],
    ) -> None:
        path      = self._scan_path(dataset_id, scan_id)
        data      = _read_json(path) or {}
        questions = results.get("questions", [])

        avg_conf  = diagnostics.get("avg_confidence", 0.0)
        null_rate = diagnostics.get("null_rate", 0.0)

        # Validation gating
        status         = "good"
        export_allowed = True

        if avg_conf < 0.4 or null_rate > 0.5:
            status         = "bad"
            export_allowed = False
        elif any(q.get("status") == "LOW_CONFIDENCE" for q in questions):
            status         = "conflict"
            export_allowed = False

        lifecycle = data.get("lifecycle", [])
        lifecycle.append({
            "stage":     "VALIDATED",
            "timestamp": _now_iso(),
            "metadata":  {"status": status, "export_allowed": export_allowed},
        })

        data.update({
            "status":        status,
            "exportAllowed": export_allowed,
            "confidence":    round(avg_conf, 4),
            "nullRate":      round(null_rate, 4),
            "extractedData": results,
            "diagnostics":   diagnostics,
            "processedAt":   _now_iso(),
            "logicVersion":  results.get("logic_version", "Hydra-v11.0"),
            "lifecycle":     lifecycle,
        })
        _write_json(path, data)

    def mark_failed(self, dataset_id: str, scan_id: str, error_msg: str) -> None:
        path = self._scan_path(dataset_id, scan_id)
        data = _read_json(path) or {}
        lifecycle = data.get("lifecycle", [])
        lifecycle.append({
            "stage":     "FAILED",
            "timestamp": _now_iso(),
            "metadata":  {"reason": error_msg},
        })
        data.update({
            "status":      "failed",
            "error":       error_msg,
            "processedAt": _now_iso(),
            "lifecycle":   lifecycle,
        })
        _write_json(path, data)
        self.log_error(scan_id, "PROCESSING", error_msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Logging helpers
    # ─────────────────────────────────────────────────────────────────────────

    def log_error(self, scan_id: str, stage: str, error_msg: str) -> None:
        path = self._error_log_path()
        logs = _read_json(path) or []
        logs.append({
            "scanId":    scan_id,
            "stage":     stage,
            "error":     error_msg,
            "timestamp": _now_iso(),
        })
        _write_json(path, logs)

    def log_activity(
        self,
        title: str,
        description: str,
        log_type: str = "primary",
    ) -> None:
        path       = self._activities_path()
        activities = _read_json(path) or []
        activities.append({
            "title":       title,
            "description": description,
            "type":        log_type,
            "createdAt":   _now_iso(),
        })
        _write_json(path, activities)

    # ─────────────────────────────────────────────────────────────────────────
    # Query helpers
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_scans(self, dataset_id: str) -> List[Dict[str, Any]]:
        scans_dir = os.path.join(self._dataset_dir(dataset_id), "scans")
        if not os.path.isdir(scans_dir):
            return []
        results = []
        for fname in os.listdir(scans_dir):
            if fname.endswith(".json"):
                doc = _read_json(os.path.join(scans_dir, fname))
                if doc:
                    results.append(doc)
        return results

    def get_scans_by_status(
        self,
        dataset_id: str,
        statuses: List[str],
    ) -> List[Dict[str, Any]]:
        status_set = set(statuses)
        return [s for s in self.get_all_scans(dataset_id)
                if s.get("status") in status_set]