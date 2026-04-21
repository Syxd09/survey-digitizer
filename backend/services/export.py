import pandas as pd
import os
from typing import List, Dict, Any
from .storage import StorageService

class ExcelExportService:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def generate_excel(self, dataset_id: str) -> str:
        """
        Fetch completed scans for a dataset and generate a multi-sheet Excel file.
        """
        # 1. Fetch data from Firestore
        scans_ref = self.storage.db.collection('datasets').document(dataset_id).collection('scans')
        # ENFORCED EXPORT GATE: Only export 'good' or 'partial' validated scans
        query = scans_ref.where('status', 'in', ['good', 'partial']).stream()
        
        q2_data = []
        q3_data = []
        
        for doc in query:
            scan = doc.to_dict()
            extracted = scan.get("extractedData", {})
            rows = extracted.get("questions", [])
            q_type = extracted.get("diagnostics", {}).get("mode", "UNKNOWN") 
            # In a real impl, we'd use the detected questionnaireType (e.g. SSIAR Q2)
            actual_type = scan.get("questionnaireType", "Q2") # Fallback
            
            entry = {
                "ScanID": scan.get("scanId"),
                "Timestamp": scan.get("createdAt"),
                "Confidence": scan.get("confidence"),
                "Status": scan.get("status")
            }
            
            # Flatten questions into columns
            for i, q in enumerate(rows):
                entry[f"Q{i+1}_{q.get('question')[:20]}"] = q.get("selected")
            
            if "Q3" in actual_type:
                q3_data.append(entry)
            else:
                q2_data.append(entry)

        # 2. Create DataFrames and Export
        temp_dir = "temp_exports"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        file_path = os.path.join(temp_dir, f"{dataset_id}_export.xlsx")
        
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            if q2_data:
                pd.DataFrame(q2_data).to_sheet(writer, sheet_name="Questionnaire_Q2", index=False)
            if q3_data:
                pd.DataFrame(q3_data).to_sheet(writer, sheet_name="Questionnaire_Q3", index=False)
            
            if not q2_data and not q3_data:
                # Create empty sheet if no data
                pd.DataFrame([{"Message": "No data found"}]).to_sheet(writer, sheet_name="Empty", index=False)

        return file_path

# Monkey patch for pandas ExcelWriter version compatibility if needed
def to_sheet(df, writer, sheet_name, index=False):
    df.to_excel(writer, sheet_name=sheet_name, index=index)
pd.DataFrame.to_sheet = to_sheet
