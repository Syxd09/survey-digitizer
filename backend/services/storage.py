import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class MockDocument:
    def __init__(self, data=None, exists=False):
        self._data = data or {}
        self.exists = exists
    def to_dict(self): return self._data
    def get(self): return self
    def set(self, data, merge=False): return None
    def update(self, data): return None
    def collection(self, name): return MockCollection()

class MockCollection:
    def document(self, id=None): return MockDocument(exists=False)
    def add(self, data): return (None, MockDocument())

class MockFirestore:
    def collection(self, name): return MockCollection()
    def ArrayUnion(self, values): return values

class StorageService:
    def __init__(self, project_id: str):
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(options={'projectId': project_id})
            self.db = firestore.client()
            self.is_mock = False
        except Exception as e:
            logger.warning(f"STORAGE_FALLBACK: Could not initialize Firebase ({str(e)}). Entering Mock Mode.")
            self.db = MockFirestore()
            self.is_mock = True

    def get_scan_status(self, dataset_id: str, scan_id: str) -> Optional[str]:
        """Check if scan exists and return its status."""
        doc = self.db.collection('datasets').document(dataset_id).collection('scans').document(scan_id).get()
        if doc.exists:
            status = doc.to_dict().get('status')
            # If status is not in the DB, it's considered 'unknown'
            return status if status else 'unknown'
        return None

    def create_form_entry(self, dataset_id: str, user_id: str, scan_id: str, image_url: str) -> str:
        """Create initial 'Scan' entry with UPLOADED status."""
        scan_ref = self.db.collection('datasets').document(dataset_id).collection('scans').document(scan_id)
        
        scan_data = {
            "datasetId": dataset_id,
            "userId": user_id,
            "scanId": scan_id,
            "status": "uploaded",
            "confidence": 0.0,
            "imageUrl": image_url,
            "createdAt": datetime.datetime.now(datetime.UTC),
            "lifecycle": [{"stage": "UPLOADED", "timestamp": datetime.datetime.now(datetime.UTC)}]
        }
        scan_ref.set(scan_data)
        return scan_id

    def update_status(self, dataset_id: str, scan_id: str, status: str, metadata: Optional[Dict] = None):
        """Update scan status and append to lifecycle audit log."""
        scan_ref = self.db.collection('datasets').document(dataset_id).collection('scans').document(scan_id)
        
        update_data = {
            "status": status.lower(),
            "lastUpdatedAt": datetime.datetime.now(datetime.UTC),
            "lifecycle": firestore.ArrayUnion([{
                "stage": status.upper(),
                "timestamp": datetime.datetime.now(datetime.UTC),
                "metadata": metadata or {}
            }])
        }
        scan_ref.update(update_data)

    def update_scan_results(self, dataset_id: str, scan_id: str, results: Dict[str, Any], diagnostics: Dict[str, Any]):
        """Perform validation gating and save result with trust scores."""
        scan_ref = self.db.collection('datasets').document(dataset_id).collection('scans').document(scan_id)
        
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

        update_data = {
            "status": status,
            "exportAllowed": export_allowed,
            "confidence": round(avg_confidence, 4),
            "nullRate": round(null_rate, 4),
            "extractedData": results,
            "diagnostics": diagnostics,
            "processedAt": datetime.datetime.now(datetime.UTC),
            "logicVersion": results.get("logic_version", "v1.0"),
            "lifecycle": firestore.ArrayUnion([{
                "stage": "VALIDATED",
                "timestamp": datetime.datetime.now(datetime.UTC),
                "metadata": {"status": status, "export_allowed": export_allowed}
            }])
        }
        
        scan_ref.update(update_data)

    def log_error(self, scan_id: str, stage: str, error_msg: str):
        """Dedicated error logging collection."""
        self.db.collection('error_logs').add({
            "scanId": scan_id,
            "stage": stage,
            "error": error_msg,
            "timestamp": datetime.datetime.now(datetime.UTC)
        })

    def log_activity(self, title: str, description: str, log_type: str = "primary"):
        log_ref = self.db.collection('activities').document()
        log_ref.set({
            "title": title,
            "description": description,
            "type": log_type,
            "createdAt": datetime.datetime.now(datetime.UTC)
        })

    def mark_failed(self, dataset_id: str, scan_id: str, error_msg: str):
        scan_ref = self.db.collection('datasets').document(dataset_id).collection('scans').document(scan_id)
        scan_ref.update({
            "status": "failed",
            "error": error_msg,
            "processedAt": datetime.datetime.now(datetime.UTC),
            "lifecycle": firestore.ArrayUnion([{
                "stage": "FAILED",
                "timestamp": datetime.datetime.now(datetime.UTC),
                "metadata": {"reason": error_msg}
            }])
        })
        self.log_error(scan_id, "PROCESSING", error_msg)
