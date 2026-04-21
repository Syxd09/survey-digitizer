"""
MetricsEngine
=============
Aggregates performance and quality metrics from StorageService scan data.
"""

import logging
from typing import Any, Dict

import numpy as np

from .storage import StorageService

logger = logging.getLogger(__name__)


class MetricsEngine:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def get_dataset_summary(self, dataset_id: str) -> Dict[str, Any]:
        """Return aggregate stats for all scans in a dataset."""
        scans = self.storage.get_all_scans(dataset_id)

        durations:   list = []
        confidences: list = []
        null_rates:  list = []
        status_counts = {
            "good": 0, "partial": 0, "bad": 0,
            "conflict": 0, "failed": 0, "uploaded": 0, "processing": 0,
        }

        for doc in scans:
            status = doc.get("status", "unknown").lower()
            if status in status_counts:
                status_counts[status] += 1

            diag = doc.get("diagnostics", {})
            dur  = diag.get("processing_duration")
            if dur is not None:
                durations.append(float(dur))

            conf = doc.get("confidence")
            if conf is not None:
                confidences.append(float(conf))

            nr = doc.get("nullRate")
            if nr is not None:
                null_rates.append(float(nr))

        total = len(scans)
        return {
            "total_forms":          total,
            "avg_processing_time":  round(float(np.mean(durations)), 2)  if durations    else 0.0,
            "avg_confidence":       round(float(np.mean(confidences)), 4) if confidences  else 0.0,
            "avg_null_rate":        round(float(np.mean(null_rates)), 4)  if null_rates   else 0.0,
            "throughput_fpm":       round(60.0 / float(np.mean(durations)), 2) if durations else 0.0,
            "status_distribution":  status_counts,
            "failure_rate":         round(status_counts["failed"] / total, 4) if total > 0 else 0.0,
            "conflict_rate":        round(status_counts["conflict"] / total, 4) if total > 0 else 0.0,
        }