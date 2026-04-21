from typing import Dict, Any, List
from .storage import StorageService
import numpy as np

class MetricsEngine:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def get_dataset_summary(self, dataset_id: str) -> Dict[str, Any]:
        """Aggregate performance and quality metrics for a given dataset."""
        scans = self.storage.get_all_scans(dataset_id)
        
        durations = []
        confidences = []
        null_rates = []
        status_counts = {"good": 0, "partial": 0, "bad": 0, "conflict": 0, "failed": 0, "uploaded": 0, "processing": 0}
        
        total_count = 0
        
        for data in scans:
            total_count += 1
            
            status = data.get("status", "unknown").lower()
            if status in status_counts:
                status_counts[status] += 1
            
            # Extract duration from diagnostics
            diag = data.get("diagnostics", {})
            dur = diag.get("processing_duration")
            if dur: durations.append(dur)
            
            conf = data.get("confidence")
            if conf is not None: confidences.append(conf)
            
            nr = data.get("nullRate")
            if nr is not None: null_rates.append(nr)

        summary = {
            "total_forms": total_count,
            "avg_processing_time": round(np.mean(durations), 2) if durations else 0,
            "avg_confidence": round(np.mean(confidences), 4) if confidences else 0,
            "avg_null_rate": round(np.mean(null_rates), 4) if null_rates else 0,
            "throughput_fpm": round(60 / np.mean(durations), 2) if durations else 0,
            "status_distribution": status_counts,
            "failure_rate": round(status_counts["failed"] / total_count, 4) if total_count > 0 else 0,
            "conflict_rate": round(status_counts["conflict"] / total_count, 4) if total_count > 0 else 0
        }
        
        return summary
