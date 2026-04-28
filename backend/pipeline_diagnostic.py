"""
Pipeline Diagnostic — Real Execution Trace
===========================================
Runs the ACTUAL pipeline code step-by-step with full instrumentation.
No mocking. No assumptions. Real values only.
"""

import sys
import os
import json
import cv2
import numpy as np
from PIL import Image as PILImage

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config import settings
from services.document_processor import get_document_processor
from services.template_service import get_template_service
from services.mark_detector import get_mark_detector

# ── Load test image ──────────────────────────────────────────────────────────

TEST_IMAGE = os.path.join(os.path.dirname(__file__), "test-images", "1.jpeg")

if not os.path.exists(TEST_IMAGE):
    print(f"ERROR: Test image not found: {TEST_IMAGE}")
    sys.exit(1)

img_bgr_original = cv2.imread(TEST_IMAGE)
h_orig, w_orig = img_bgr_original.shape[:2]

print("=" * 80)
print("PIPELINE DIAGNOSTIC — REAL EXECUTION TRACE")
print("=" * 80)
print(f"\nTest Image: {TEST_IMAGE}")
print(f"Original Dimensions: {w_orig} x {h_orig}")

# ── PHASE 1: Preprocessing ──────────────────────────────────────────────────

print("\n" + "─" * 80)
print("PHASE 1: PREPROCESSING")
print("─" * 80)

doc_processor = get_document_processor()
processed_img, p1_diag = doc_processor.process_document(img_bgr_original)

h_proc, w_proc = processed_img.shape[:2]

print(f"  Original:     {w_orig} x {h_orig}")
print(f"  Processed:    {w_proc} x {h_proc}")
print(f"  Scale Factor: {p1_diag['normalization']['scale_factor']}")
print(f"  Rotated:      {p1_diag['orientation'].get('coarse_rotated', False)}")
print(f"  Deskew:       {p1_diag['orientation'].get('fine_deskew_applied', False)} (angle: {p1_diag['orientation'].get('skew_angle', 0)}°)")
print(f"  Quality:      {p1_diag['quality']['status']}")
print(f"    Blur:       {p1_diag['quality']['blur_value']} (threshold: {settings.BLUR_THRESHOLD})")
print(f"    Brightness: {p1_diag['quality']['brightness_value']}")
print(f"  Enhancement:  CLAHE={p1_diag.get('enhancement', {}).get('clahe_applied')}, Sauvola={p1_diag.get('enhancement', {}).get('sauvola_applied')}")

# ── PHASE 4: TEMPLATE ANALYSIS ──────────────────────────────────────────────

print("\n" + "─" * 80)
print("PHASE 4: TEMPLATE ANALYSIS")
print("─" * 80)

template_service = get_template_service()
template = template_service.get_template()

print(f"  Template ID:  {template['id']}")
print(f"  Template Name: {template['name']}")
print(f"  Total Fields: {len(template['fields'])}")

# Count strategies
strategies = {}
for f in template['fields']:
    s = f.get('strategy', 'unknown')
    strategies[s] = strategies.get(s, 0) + 1
print(f"  Strategies:   {strategies}")

# Show first 3 fields
print(f"\n  Sample Fields:")
for f in template['fields'][:3]:
    print(f"    {f['id']}: strategy={f['strategy']}, type={f.get('type')}")
    if f.get('options'):
        for opt in f['options']:
            print(f"      option: value={opt['value']}, bbox_ratio={opt['bbox_ratio']}")

# ── PHASE 4.5: BOUNDING BOX VALIDATION ──────────────────────────────────────

print("\n" + "─" * 80)
print("PHASE 4.5: BOUNDING BOX VALIDATION (CRITICAL)")
print("─" * 80)
print(f"  Processed image size: {w_proc} x {h_proc}")
print(f"  All bbox ratios are scaled against this size.\n")

mark_detector = get_mark_detector()

# Run detection for ALL 25 questions
all_results = []

for field in template['fields']:
    if field.get('strategy') != 'radio_group':
        continue
    
    q_id = field['id']
    options = field.get('options', [])
    densities = []
    
    for opt in options:
        bbox_ratio = opt['bbox_ratio']
        real_bbox = [
            int(bbox_ratio[0] * w_proc),
            int(bbox_ratio[1] * h_proc),
            int(bbox_ratio[2] * w_proc),
            int(bbox_ratio[3] * h_proc)
        ]
        
        # Run actual mark detection
        result = mark_detector.is_marked(processed_img, real_bbox)
        
        # Compute crop dimensions for sanity check
        crop_w = real_bbox[2] - real_bbox[0]
        crop_h = real_bbox[3] - real_bbox[1]
        
        densities.append({
            "value": opt['value'],
            "bbox_ratio": bbox_ratio,
            "real_bbox": real_bbox,
            "crop_size": f"{crop_w}x{crop_h}",
            "density": result['density'],
            "is_marked": result['is_marked'],
            "status": result['status']
        })
    
    # Winner-takes-all logic (same as extraction_engine.py)
    densities_sorted = sorted(densities, key=lambda x: x['density'], reverse=True)
    winner = densities_sorted[0]
    runner_up = densities_sorted[1] if len(densities_sorted) > 1 else {"density": 0.0}
    diff = winner['density'] - runner_up['density']
    
    if winner['density'] < settings.MIN_FILL_THRESHOLD:
        final_value = "UNANSWERED"
        final_status = "NOT_FOUND"
        confidence = 0.0
    elif diff < settings.VISUAL_CONFIDENCE_THRESHOLD:
        final_value = winner['value']
        final_status = "AMBIGUOUS"
        confidence = 0.3
    else:
        final_value = winner['value']
        final_status = "OK"
        confidence = 1.0
    
    row_result = {
        "row_id": q_id.upper(),
        "question_label": field.get('name', '')[:60],
        "option_boxes": [],
        "winner_index": None,
        "runner_up_index": None,
        "confidence_gap": round(diff, 4),
        "final_value": final_value,
        "final_status": final_status,
        "confidence": confidence
    }
    
    for i, d in enumerate(densities):
        row_result["option_boxes"].append({
            "index": i + 1,
            "label": d['value'],
            "bbox": d['real_bbox'],
            "crop_size": d['crop_size'],
            "fill_ratio": d['density']
        })
        if d['value'] == winner['value']:
            row_result["winner_index"] = i + 1
    
    # Find runner_up index
    for i, d in enumerate(densities):
        if d['value'] == densities_sorted[1]['value'] if len(densities_sorted) > 1 else None:
            row_result["runner_up_index"] = i + 1
    
    all_results.append(row_result)

# ── PRINT DETAILED PER-ROW OUTPUT ────────────────────────────────────────────

print("  PER-ROW MARK DETECTION RESULTS")
print("  " + "=" * 76)

# Status counters
status_counts = {"OK": 0, "AMBIGUOUS": 0, "NOT_FOUND": 0}
value_counts = {"Not True": 0, "Somewhat True": 0, "Certainly True": 0, "UNANSWERED": 0}

for r in all_results:
    status_counts[r["final_status"]] = status_counts.get(r["final_status"], 0) + 1
    value_counts[r["final_value"]] = value_counts.get(r["final_value"], 0) + 1
    
    print(f"\n  {r['row_id']}: {r['question_label']}...")
    for ob in r['option_boxes']:
        marker = " ◀ WINNER" if ob['index'] == r['winner_index'] else ""
        print(f"    [{ob['index']}] {ob['label']:18s} bbox={ob['bbox']}  crop={ob['crop_size']:8s}  fill={ob['fill_ratio']:.4f}{marker}")
    print(f"    → RESULT: {r['final_value']}  status={r['final_status']}  gap={r['confidence_gap']:.4f}  conf={r['confidence']}")

# ── AGGREGATE ANALYSIS ───────────────────────────────────────────────────────

print("\n" + "─" * 80)
print("AGGREGATE ANALYSIS")
print("─" * 80)

print(f"\n  Status Distribution:")
for k, v in status_counts.items():
    print(f"    {k}: {v}/{len(all_results)} ({v/len(all_results)*100:.0f}%)")

print(f"\n  Value Distribution:")
for k, v in value_counts.items():
    print(f"    {k}: {v}")

# Compute density statistics
all_densities_flat = []
for r in all_results:
    for ob in r['option_boxes']:
        all_densities_flat.append(ob['fill_ratio'])

print(f"\n  Density Statistics (all {len(all_densities_flat)} option boxes):")
print(f"    Min:    {min(all_densities_flat):.4f}")
print(f"    Max:    {max(all_densities_flat):.4f}")
print(f"    Mean:   {np.mean(all_densities_flat):.4f}")
print(f"    Median: {np.median(all_densities_flat):.4f}")
print(f"    StdDev: {np.std(all_densities_flat):.4f}")

# Check if densities are suspiciously uniform (suggests wrong regions)
max_d = max(all_densities_flat)
min_d = min(all_densities_flat)
spread = max_d - min_d

print(f"\n  ⚠ DIAGNOSTIC FLAGS:")
if spread < 0.05:
    print(f"    🔴 CRITICAL: All densities within {spread:.4f} range — suggests bboxes are hitting BLANK PAPER or all hitting the SAME region type")
elif max_d < settings.MIN_FILL_THRESHOLD:
    print(f"    🔴 CRITICAL: Max density ({max_d:.4f}) is below MIN_FILL_THRESHOLD ({settings.MIN_FILL_THRESHOLD}) — NO marks detected at all")
elif status_counts.get("UNANSWERED", 0) > 20:
    print(f"    🔴 CRITICAL: {status_counts['UNANSWERED']}/25 rows UNANSWERED — bboxes likely misaligned")
elif status_counts.get("AMBIGUOUS", 0) > 15:
    print(f"    🟡 WARNING: {status_counts['AMBIGUOUS']}/25 rows AMBIGUOUS — threshold may need tuning")
else:
    print(f"    🟢 Detection appears functional. {status_counts.get('OK', 0)}/25 clear winners.")

# ── BBOX ALIGNMENT SANITY CHECK ──────────────────────────────────────────────

print("\n" + "─" * 80)
print("BBOX ALIGNMENT SANITY CHECK")
print("─" * 80)

# Check if bboxes are within image bounds
oob_count = 0
for r in all_results:
    for ob in r['option_boxes']:
        bbox = ob['bbox']
        if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > w_proc or bbox[3] > h_proc:
            oob_count += 1
            print(f"  🔴 OUT OF BOUNDS: {r['row_id']} option {ob['index']}: {bbox} (image: {w_proc}x{h_proc})")

if oob_count == 0:
    print(f"  ✅ All {len(all_results) * 3} option boxes are within image bounds.")

# Check crop sizes (should be reasonable - e.g., 50-200px each dimension)
tiny_crops = 0
huge_crops = 0
for r in all_results:
    for ob in r['option_boxes']:
        bbox = ob['bbox']
        cw = bbox[2] - bbox[0]
        ch = bbox[3] - bbox[1]
        if cw < 10 or ch < 10:
            tiny_crops += 1
        if cw > 300 or ch > 300:
            huge_crops += 1

print(f"  Tiny crops (<10px): {tiny_crops}")
print(f"  Huge crops (>300px): {huge_crops}")

# Show bbox coverage as % of image
first_q = all_results[0]['option_boxes']
last_q = all_results[-1]['option_boxes']
y_start_px = first_q[0]['bbox'][1]
y_end_px = last_q[-1]['bbox'][3]
x_start_px = first_q[0]['bbox'][0]
x_end_px = first_q[-1]['bbox'][2]

print(f"\n  Grid Coverage on Processed Image ({w_proc}x{h_proc}):")
print(f"    X range: {x_start_px}px — {x_end_px}px  ({x_start_px/w_proc*100:.1f}% — {x_end_px/w_proc*100:.1f}%)")
print(f"    Y range: {y_start_px}px — {y_end_px}px  ({y_start_px/h_proc*100:.1f}% — {y_end_px/h_proc*100:.1f}%)")
print(f"    Total grid area: {(x_end_px-x_start_px)*(y_end_px-y_start_px)} px²  ({(x_end_px-x_start_px)*(y_end_px-y_start_px)/(w_proc*h_proc)*100:.1f}% of image)")

# ── VISUAL DEBUG: Save annotated image ────────────────────────────────────────

print("\n" + "─" * 80)
print("SAVING DEBUG OVERLAY IMAGE")
print("─" * 80)

debug_img = processed_img.copy()

colors = [(0, 0, 255), (0, 165, 255), (0, 255, 0)]  # Red, Orange, Green for 3 options
color_labels = ["Not True", "Somewhat True", "Certainly True"]

for r in all_results:
    for ob in r['option_boxes']:
        bbox = ob['bbox']
        color_idx = ob['index'] - 1
        color = colors[color_idx] if color_idx < len(colors) else (255, 255, 255)
        
        # Draw the bbox rectangle
        thickness = 2 if ob['index'] == r['winner_index'] else 1
        cv2.rectangle(debug_img, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, thickness)
        
        # Put fill ratio text
        label = f"{ob['fill_ratio']:.2f}"
        cv2.putText(debug_img, label, (bbox[0], bbox[1] - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

debug_path = os.path.join(os.path.dirname(__file__), "data", "pipeline_diagnostic_overlay.jpg")
cv2.imwrite(debug_path, debug_img)
print(f"  Saved: {debug_path}")

# ── SAVE FULL JSON REPORT ─────────────────────────────────────────────────────

report = {
    "test_image": TEST_IMAGE,
    "original_dims": {"w": w_orig, "h": h_orig},
    "processed_dims": {"w": w_proc, "h": h_proc},
    "preprocessing": {
        "scale_factor": p1_diag['normalization']['scale_factor'],
        "rotated": p1_diag['orientation'].get('coarse_rotated', False),
        "deskew_applied": p1_diag['orientation'].get('fine_deskew_applied', False),
        "deskew_angle": p1_diag['orientation'].get('skew_angle', 0),
        "quality_status": p1_diag['quality']['status'],
        "enhancement": p1_diag.get('enhancement', {})
    },
    "template": {
        "id": template['id'],
        "name": template['name'],
        "total_fields": len(template['fields']),
        "strategies": strategies
    },
    "thresholds": {
        "PIXEL_DENSITY_THRESHOLD": settings.PIXEL_DENSITY_THRESHOLD,
        "MIN_FILL_THRESHOLD": settings.MIN_FILL_THRESHOLD,
        "VISUAL_CONFIDENCE_THRESHOLD": settings.VISUAL_CONFIDENCE_THRESHOLD,
        "MARGIN_EXCLUSION_RATIO": settings.MARGIN_EXCLUSION_RATIO
    },
    "detection_results": all_results,
    "aggregate": {
        "status_distribution": status_counts,
        "value_distribution": value_counts,
        "density_stats": {
            "min": round(min(all_densities_flat), 4),
            "max": round(max(all_densities_flat), 4),
            "mean": round(float(np.mean(all_densities_flat)), 4),
            "median": round(float(np.median(all_densities_flat)), 4),
            "std": round(float(np.std(all_densities_flat)), 4)
        }
    }
}

report_path = os.path.join(os.path.dirname(__file__), "data", "pipeline_diagnostic_report.json")
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2, default=str)
print(f"  Report: {report_path}")

# ── FINAL VERDICT ─────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("FINAL EXECUTION SUMMARY")
print("=" * 80)
print(f"  Pipeline Execution: COMPLETE")
print(f"  Phase 1 (Preprocess): {p1_diag['quality']['status']}")
print(f"  Phase 4 (Template):   {template['id']} ({len(template['fields'])} fields)")
print(f"  Phase 4.5 (Detection): {status_counts.get('OK',0)} OK / {status_counts.get('AMBIGUOUS',0)} AMBIGUOUS / {status_counts.get('NOT_FOUND',0)} UNANSWERED")
print(f"  Detection Method: PIXEL DENSITY (Otsu threshold)")
print(f"  OCR Used for Selections: NO (radio_group strategy bypasses OCR)")
print("=" * 80)
