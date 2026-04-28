"""
Grid Detection Diagnostic — Tests all 5 images
================================================
Runs the new dynamic grid detector against every test image and
compares results with what's visually on the forms.
"""

import sys, os, json, cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
load_dotenv()

from config import settings
from services.document_processor import get_document_processor
from services.grid_detector import get_grid_detector
from services.mark_detector import get_mark_detector

doc_processor = get_document_processor()
grid_detector = get_grid_detector()
mark_detector = get_mark_detector()

TEST_DIR = os.path.join(os.path.dirname(__file__), "test-images")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

EXPECTED = {
    "1.jpeg": {"rows_min": 5, "cols_expected": 3, "note": "SDQ page 1, 7 rows, checkmarks"},
    "2.jpeg": {"rows_min": 2, "cols_expected": 6, "note": "6-col Likert, 3 rows, circled"},
    "3.jpeg": {"rows_min": 4, "cols_expected": 3, "note": "SDQ continuation Q20-25, 6 rows"},
    "4.jpeg": {"rows_min": 8, "cols_expected": 3, "note": "SDQ page 2 Q8-19, 12 rows"},
    "5.jpeg": {"rows_min": 3, "cols_expected": 6, "note": "6-col Likert page 2, 5 rows"},
}

all_reports = {}

for fname, expected in EXPECTED.items():
    img_path = os.path.join(TEST_DIR, fname)
    if not os.path.exists(img_path):
        print(f"SKIP: {fname} not found")
        continue

    print("=" * 80)
    print(f"IMAGE: {fname}")
    print(f"  Expected: {expected['note']}")
    print("=" * 80)

    # Load and preprocess
    img_bgr = cv2.imread(img_path)
    h_orig, w_orig = img_bgr.shape[:2]
    processed, p1_diag = doc_processor.process_document(img_bgr)
    h_proc, w_proc = processed.shape[:2]
    print(f"  Original: {w_orig}x{h_orig} -> Processed: {w_proc}x{h_proc}")

    # Run grid detection
    grid = grid_detector.detect_grid(processed)

    report = {
        "image": fname,
        "expected": expected,
        "original_size": f"{w_orig}x{h_orig}",
        "processed_size": f"{w_proc}x{h_proc}",
        "grid_success": grid["success"],
        "table_bbox": grid.get("table_bbox"),
        "diagnostics": grid.get("diagnostics", {}),
    }

    if not grid["success"]:
        print(f"  GRID DETECTION: FAILED")
        print(f"    Diagnostics: {grid.get('diagnostics', {})}")
        all_reports[fname] = report
        continue

    data_rows = grid["rows"]
    option_cols = grid["option_columns"]
    header_rows = grid.get("header_rows", [])

    print(f"  GRID DETECTION: SUCCESS")
    print(f"    Table bbox: {grid['table_bbox']}")
    print(f"    Header rows: {len(header_rows)}")
    print(f"    Data rows: {len(data_rows)} (expected >= {expected['rows_min']})")
    print(f"    Option columns: {len(option_cols)} (expected: {expected['cols_expected']})")
    
    # Validate row count
    row_ok = len(data_rows) >= expected['rows_min']
    col_ok = len(option_cols) == expected['cols_expected']
    print(f"    Row count: {'PASS' if row_ok else 'FAIL'}")
    print(f"    Col count: {'PASS' if col_ok else 'FAIL'}")

    # Show column ranges
    print(f"\n    Column ranges (option cols):")
    for i, (cx1, cx2) in enumerate(option_cols):
        print(f"      Col {i+1}: x={cx1}-{cx2} (width={cx2-cx1}px)")

    # Run mark detection on each cell
    print(f"\n    PER-ROW MARK DETECTION:")
    print(f"    {'Row':<5} ", end="")
    for i in range(len(option_cols)):
        print(f"{'Col'+str(i+1):<10} ", end="")
    print(f"{'Winner':<10} {'Status':<12} {'Gap':<8}")
    print(f"    {'-'*5} ", end="")
    for i in range(len(option_cols)):
        print(f"{'-'*10} ", end="")
    print(f"{'-'*10} {'-'*12} {'-'*8}")

    row_results = []
    for row_idx, (ry1, ry2) in enumerate(data_rows):
        row_cells = [c for c in grid["cells"] if c["row_index"] == row_idx]
        row_cells.sort(key=lambda c: c["col_index"])

        densities = []
        for cell in row_cells:
            bbox = cell["bbox"]
            res = mark_detector.is_marked(processed, bbox)
            densities.append({
                "col": cell["col_index"],
                "density": res["density"],
                "marked": res["is_marked"],
                "bbox": bbox
            })

        # Winner takes all
        densities.sort(key=lambda x: x["density"], reverse=True)
        winner = densities[0]
        runner_up = densities[1] if len(densities) > 1 else {"density": 0.0}
        diff = winner["density"] - runner_up["density"]

        if winner["density"] < settings.MIN_FILL_THRESHOLD:
            status = "UNANSWERED"
            selected = "-"
        elif diff < settings.VISUAL_CONFIDENCE_THRESHOLD:
            status = "AMBIGUOUS"
            selected = f"Col{winner['col']+1}"
        else:
            status = "OK"
            selected = f"Col{winner['col']+1}"

        # Print row
        print(f"    Q{row_idx+1:<4} ", end="")
        # Re-sort by col for display
        densities_display = sorted(densities, key=lambda x: x["col"])
        for d in densities_display:
            marker = "*" if d["col"] == winner["col"] and status != "UNANSWERED" else " "
            print(f"{d['density']:.4f}{marker}    ", end="")
        print(f"{selected:<10} {status:<12} {diff:.4f}")

        row_results.append({
            "row": row_idx + 1,
            "densities": [{
                "col": d["col"] + 1,
                "density": round(d["density"], 4),
                "bbox": d["bbox"]
            } for d in sorted(densities, key=lambda x: x["col"])],
            "winner_col": winner["col"] + 1 if status != "UNANSWERED" else None,
            "status": status,
            "gap": round(diff, 4)
        })

    report["data_rows"] = len(data_rows)
    report["option_columns"] = len(option_cols)
    report["row_count_pass"] = row_ok
    report["col_count_pass"] = col_ok
    report["row_results"] = row_results

    # Count results
    ok_count = sum(1 for r in row_results if r["status"] == "OK")
    amb_count = sum(1 for r in row_results if r["status"] == "AMBIGUOUS")
    una_count = sum(1 for r in row_results if r["status"] == "UNANSWERED")
    print(f"\n    Summary: {ok_count} OK / {amb_count} AMBIGUOUS / {una_count} UNANSWERED")

    report["summary"] = {"ok": ok_count, "ambiguous": amb_count, "unanswered": una_count}

    # Save debug overlay
    overlay = grid_detector.generate_debug_overlay(processed, grid)
    overlay_path = os.path.join(OUTPUT_DIR, f"grid_overlay_{fname}")
    cv2.imwrite(overlay_path, overlay)
    print(f"    Overlay saved: {overlay_path}")

    all_reports[fname] = report
    print()

# Save full report
report_path = os.path.join(OUTPUT_DIR, "grid_diagnostic_report.json")
with open(report_path, "w") as f:
    json.dump(all_reports, f, indent=2, default=str)
print(f"\nFull report: {report_path}")

# Final summary
print("\n" + "=" * 80)
print("OVERALL SUMMARY")
print("=" * 80)
for fname, r in all_reports.items():
    success = r.get("grid_success", False)
    if success:
        s = r.get("summary", {})
        rows = r.get("data_rows", 0)
        cols = r.get("option_columns", 0)
        row_pass = "PASS" if r.get("row_count_pass") else "FAIL"
        col_pass = "PASS" if r.get("col_count_pass") else "FAIL"
        print(f"  {fname}: GRID={rows}x{cols} rows={row_pass} cols={col_pass} | {s.get('ok',0)} OK / {s.get('ambiguous',0)} AMB / {s.get('unanswered',0)} UNA")
    else:
        print(f"  {fname}: GRID DETECTION FAILED")
