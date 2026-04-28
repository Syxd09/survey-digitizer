"""
ExcelExportService
==================
Exports validated scan results to a multi-sheet Excel workbook.
"""

import logging
import os
from typing import Any, Dict, List

import pandas as pd
import openpyxl
import openpyxl.styles

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
        Fetch validated/approved scans and write a multi-sheet .xlsx file.
        Returns the local file path.
        """
        # Phase 15: Include 'approved' and 'conflict' (if user wants to see low-conf items)
        target_statuses = ["good", "partial", "approved", "conflict", "corrected"]
        scans = self.storage.get_scans_by_status(dataset_id, target_statuses)
        
        # Wide Format List (one row per scan)
        wide_data: List[Dict[str, Any]] = []
        # Long Format List (one row per question)
        long_data: List[Dict[str, Any]] = []

        for scan in scans:
            extracted = scan.get("extractedData", {})
            questions = extracted.get("questions", [])
            scan_id   = scan.get("scanId", "unknown")
            ts        = scan.get("createdAt", "")

            # 1. Prepare Wide Entry
            wide_entry: Dict[str, Any] = {
                "id":         scan_id,
                "user_id":    scan.get("userId", "anon"),
                "survey_id":  scan.get("datasetId", "default"),
                "timestamp":  ts,
                "confidence": f"{scan.get('confidence', 0) * 100:.1f}%",
                "status":     scan.get("status", "").upper(),
            }

            def get_answer_label(val: Any) -> str:
                v = str(val).strip()
                mapping = {
                    "1": "Not True",
                    "2": "Somewhat True",
                    "3": "Certainly True"
                }
                return mapping.get(v, "Unknown")

            for i, q in enumerate(questions, start=1):
                val = q.get("selected")
                label = get_answer_label(val)
                q_text = q.get("question") or ""
                
                # 1. Prepare Wide Entry
                # Use "q{i}: {text}" as header to make it obvious
                header_key = f"q{i}: {q_text[:30]}..." if q_text else f"q{i}"
                wide_entry[header_key] = val

                # 2. Prepare Long Entry
                long_data.append({
                    "id":         scan_id,
                    "user_id":    scan.get("userId", "anon"),
                    "survey_id":  scan.get("datasetId", "default"),
                    "timestamp":  ts,
                    "question_#": i,
                    "question_text": q_text or f"Question {i}",
                    "value":      val,
                    "answer_label": label,
                    "confidence": f"{q.get('confidence', 0) * 100:.1f}%",
                    "status":     q.get("status", "OK")
                })

            wide_data.append(wide_entry)

        os.makedirs(EXPORT_DIR, exist_ok=True)
        file_path = os.path.join(EXPORT_DIR, f"{dataset_id}_export.xlsx")

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            # Write Wide Sheet
            df_wide = pd.DataFrame(wide_data) if wide_data else pd.DataFrame([{"Message": "No data found"}])
            df_wide.to_excel(writer, sheet_name="Data_Wide", index=False)
            
            # Write Long Sheet
            df_long = pd.DataFrame(long_data) if long_data else pd.DataFrame([{"Message": "No data found"}])
            df_long.to_excel(writer, sheet_name="Data_Long", index=False)

            # Apply Styling
            workbook = writer.book
            header_font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            header_fill = openpyxl.styles.PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
            
            for sheet_name in ["Data_Wide", "Data_Long"]:
                if sheet_name not in workbook.sheetnames: continue
                sheet = workbook[sheet_name]
                
                # Style Header
                for cell in sheet[1]:
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = openpyxl.styles.Alignment(horizontal="center")

                # Auto-adjust column widths
                for col in sheet.columns:
                    max_length = 0
                    column = col[0].column_letter
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    sheet.column_dimensions[column].width = min(adjusted_width, 50)

        logger.info(f"[EXPORT] Created dual-format workbook → {file_path}")
        return file_path