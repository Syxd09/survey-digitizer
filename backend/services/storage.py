import datetime
import json
import os
import uuid
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _read_json(filepath: str) -> Any:
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: str, data: Any):
    _ensure_dir(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


class StorageService:
    def __init__(self, project_id: str = "local"):
        self.data_dir = DATA_DIR
        _ensure_dir(self.data_dir)
        self.is_mock = False
        logger.info(f"[STORAGE] Using local JSON file storage at: {self.data_dir}")

    def _dataset_dir(self, dataset_id: str) -> str:
        return os.path.join(self.data_dir, "datasets", dataset_id)

    def _scan_path(self, dataset_id: str, scan_id: str) -> str:
        return os.path.join(self._dataset_dir(dataset_id), "scans", f"{scan_id}.json")

    def _error_log_path(self) -> str:
        return os.path.join(self.data_dir, "error_logs.json")

    def _activities_path(self) -> str:
        return os.path.join(self.data_dir, "activities.json")

    def get_scan_status(self, dataset_id: str, scan_id: str) -> Optional[str]:
        """Check if scan exists and return its status."""
        scan_data = _read_json(self._scan_path(dataset_id, scan_id))
        if scan_data:
            status = scan_data.get("status")
            return status if status else "unknown"
        return None

    def create_form_entry(self, dataset_id: str, user_id: str, scan_id: str, image_url: str) -> str:
        """Create initial 'Scan' entry with UPLOADED status."""
        scan_data = {
            "datasetId": dataset_id,
            "userId": user_id,
            "scanId": scan_id,
            "status": "uploaded",
            "confidence": 0.0,
            "imageUrl": image_url,
            "createdAt": datetime.datetime.now(datetime.UTC).isoformat(),
            "lifecycle": [{"stage": "UPLOADED", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}]
        }
        _write_json(self._scan_path(dataset_id, scan_id), scan_data)
        return scan_id

    def update_status(self, dataset_id: str, scan_id: str, status: str, metadata: Optional[Dict] = None):
        """Update scan status and append to lifecycle audit log."""
        scan_path = self._scan_path(dataset_id, scan_id)
        scan_data = _read_json(scan_path) or {}

        scan_data["status"] = status.lower()
        scan_data["lastUpdatedAt"] = datetime.datetime.now(datetime.UTC).isoformat()
        
        lifecycle = scan_data.get("lifecycle", [])
        lifecycle.append({
            "stage": status.upper(),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "metadata": metadata or {}
        })
        scan_data["lifecycle"] = lifecycle
        
        _write_json(scan_path, scan_data)

    def update_scan_results(self, dataset_id: str, scan_id: str, results: Dict[str, Any], diagnostics: Dict[str, Any]):
        """Perform validation gating and save result with trust scores."""
        scan_path = self._scan_path(dataset_id, scan_id)
        scan_data = _read_json(scan_path) or {}

        questions = results.get("questions", [])
        avg_confidence = diagnostics.get("avg_confidence", 0.0)
        null_rate = diagnostics.get("null_rate", 0.0)

        # 1. Validation Logic (Strict Gating)
        status = "good"
        export_allowed = True

        if avg_confidence < 0.4:
            status = "bad"
            export_allowed = False
        elif null_rate > 0.5:
            status = "bad"
            export_allowed = False

        # Check for ambiguity (Conflict)
        ambiguous = any(q.get("status") == "LOW_CONFIDENCE" for q in questions)
        if ambiguous and status == "good":
            status = "conflict"
            export_allowed = False

        scan_data.update({
            "status": status,
            "exportAllowed": export_allowed,
            "confidence": round(avg_confidence, 4),
            "nullRate": round(null_rate, 4),
            "extractedData": results,
            "diagnostics": diagnostics,
            "processedAt": datetime.datetime.now(datetime.UTC).isoformat(),
            "logicVersion": results.get("logic_version", "v1.0"),
        })

        lifecycle = scan_data.get("lifecycle", [])
        lifecycle.append({
            "stage": "VALIDATED",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "metadata": {"status": status, "export_allowed": export_allowed}
        })
        scan_data["lifecycle"] = lifecycle

        _write_json(scan_path, scan_data)

    def log_error(self, scan_id: str, stage: str, error_msg: str):
        """Dedicated error logging."""
        log_path = self._error_log_path()
        logs = _read_json(log_path) or []
        logs.append({
            "scanId": scan_id,
            "stage": stage,
            "error": error_msg,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
        })
        _write_json(log_path, logs)

    def log_activity(self, title: str, description: str, log_type: str = "primary"):
        activities_path = self._activities_path()
        activities = _read_json(activities_path) or []
        activities.append({
            "title": title,
            "description": description,
            "type": log_type,
            "createdAt": datetime.datetime.now(datetime.UTC).isoformat()
        })
        _write_json(activities_path, activities)

    def mark_failed(self, dataset_id: str, scan_id: str, error_msg: str):
        scan_path = self._scan_path(dataset_id, scan_id)
        scan_data = _read_json(scan_path) or {}

        scan_data["status"] = "failed"
        scan_data["error"] = error_msg
        scan_data["processedAt"] = datetime.datetime.now(datetime.UTC).isoformat()

        lifecycle = scan_data.get("lifecycle", [])
        lifecycle.append({
            "stage": "FAILED",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "metadata": {"reason": error_msg}
        })
        scan_data["lifecycle"] = lifecycle

        _write_json(scan_path, scan_data)
        self.log_error(scan_id, "PROCESSING", error_msg)

    # --- Additional helpers for metrics/export that used Firestore queries ---

    def get_all_scans(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Return all scan documents for a dataset."""
        scans_dir = os.path.join(self._dataset_dir(dataset_id), "scans")
        if not os.path.exists(scans_dir):
            return []
        results = []
        for fname in os.listdir(scans_dir):
            if fname.endswith(".json"):
                data = _read_json(os.path.join(scans_dir, fname))
                if data:
                    results.append(data)
        return results

    def get_scans_by_status(self, dataset_id: str, statuses: List[str]) -> List[Dict[str, Any]]:
        """Return scans matching given statuses."""
        all_scans = self.get_all_scans(dataset_id)
        return [s for s in all_scans if s.get("status") in statuses]
