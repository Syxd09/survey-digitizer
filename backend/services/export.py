"""
ExcelExportService
==================
Exports validated scan results to a multi-sheet Excel workbook.
"""

import logging
import os
from typing import Any, Dict, List

import pandas as pd

from .storage import StorageService

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "temp_exports",
)


class ExcelExportService:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def generate_excel(self, dataset_id: str) -> str:
        """
        Fetch validated scans and write a multi-sheet .xlsx file.
        Returns the local file path.
        """
        scans = self.storage.get_scans_by_status(dataset_id, ["good", "partial"])
        q2_data: List[Dict[str, Any]] = []
        q3_data: List[Dict[str, Any]] = []

        for scan in scans:
            extracted    = scan.get("extractedData", {})
            rows         = extracted.get("questions", [])
            scan_type    = scan.get("questionnaireType", "Q2")

            entry: Dict[str, Any] = {
                "ScanID":     scan.get("scanId"),
                "Timestamp":  scan.get("createdAt"),
                "Confidence": scan.get("confidence"),
                "NullRate":   scan.get("nullRate"),
                "Status":     scan.get("status"),
            }

            for i, q in enumerate(rows, start=1):
                col = f"Q{i}_{(q.get('question') or '')[:25]}"
                entry[col] = q.get("selected")

            if "Q3" in str(scan_type):
                q3_data.append(entry)
            else:
                q2_data.append(entry)

        os.makedirs(EXPORT_DIR, exist_ok=True)
        file_path = os.path.join(EXPORT_DIR, f"{dataset_id}_export.xlsx")

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            if q2_data:
                pd.DataFrame(q2_data).to_excel(
                    writer, sheet_name="Questionnaire_Q2", index=False
                )
            if q3_data:
                pd.DataFrame(q3_data).to_excel(
                    writer, sheet_name="Questionnaire_Q3", index=False
                )
            if not q2_data and not q3_data:
                pd.DataFrame([{"Message": "No validated data found for this dataset"}]).to_excel(
                    writer, sheet_name="Empty", index=False
                )

        logger.info(f"[EXPORT] Written {len(q2_data)+len(q3_data)} rows → {file_path}")
        return file_path