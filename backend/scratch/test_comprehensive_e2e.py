"""
Comprehensive End-to-End Pipeline Test
=======================================
Tests every phase of the pipeline individually AND as a whole,
then validates the CORRECTNESS of the output — not just "did it not crash".

Validates:
  1. Image decoding & preprocessing (Phase 1)
  2. OCR word extraction (Phase 2)
  3. Line reconstruction (Phase 3)
  4. Grid detection (Phase 4.3)
  5. Field extraction (Phase 4)
  6. Validation & cleaning (Phase 5/6)
  7. Confidence scoring (Phase 7)
  8. Decision routing (Phase 8)
  9. Database persistence (Phase 9)
  10. Debug overlay generation (Phase 12)
  11. Full pipeline integration
"""

import os, sys, json, time, hashlib, base64, traceback
import cv2
import numpy as np

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

# ── Test Result Tracker ──────────────────────────────────────────────────────
PASS = 0
FAIL = 0
RESULTS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    status = "✅ PASS" if condition else "❌ FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  {status} | {name}"
    if detail and not condition:
        msg += f"  →  {detail}"
    print(msg)
    RESULTS.append({"name": name, "passed": condition, "detail": detail})

def section(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")

# ── Load a real test image ───────────────────────────────────────────────────
IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-images")
IMG_PATH = os.path.join(IMG_DIR, "1.jpeg")

if not os.path.exists(IMG_PATH):
    print(f"❌ FATAL: Test image not found at {IMG_PATH}")
    sys.exit(1)

img_bgr = cv2.imread(IMG_PATH)
assert img_bgr is not None, "Failed to load test image"
h_orig, w_orig = img_bgr.shape[:2]

with open(IMG_PATH, "rb") as f:
    img_bytes_raw = f.read()
img_b64 = base64.b64encode(img_bytes_raw).decode("utf-8")

print(f"\n🔬 Test image: {IMG_PATH}")
print(f"   Dimensions: {w_orig}×{h_orig}, Size: {len(img_bytes_raw)//1024}KB")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: Document Preprocessing
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 1: Document Preprocessing")

from services.document_processor import get_document_processor
doc_proc = get_document_processor()
processed_img, p1_diag = doc_proc.process_document(img_bgr)

check("Returns processed image", processed_img is not None and processed_img.size > 0)
check("Returns diagnostics dict", isinstance(p1_diag, dict))
check("Quality assessment present", "quality" in p1_diag)
check("Quality has status", p1_diag.get("quality", {}).get("status") in ["PASS", "FAIL", "REJECT"],
      f"Got: {p1_diag.get('quality', {}).get('status')}")
check("Blur value is numeric", isinstance(p1_diag.get("quality", {}).get("blur_value"), (int, float)))
check("Brightness value is numeric", isinstance(p1_diag.get("quality", {}).get("brightness_value"), (int, float)))
check("Orientation info present", "orientation" in p1_diag)
check("Normalization applied", "normalization" in p1_diag)
check("Scale factor recorded", isinstance(p1_diag.get("normalization", {}).get("scale_factor"), (int, float)))
check("Image is resized to target width", processed_img.shape[1] == settings.TARGET_WIDTH,
      f"Got width={processed_img.shape[1]}, expected={settings.TARGET_WIDTH}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: OCR Engine
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 2: OCR Engine")

from services.ocr_engine import get_ocr_engine
ocr_engine = get_ocr_engine()

# Encode processed image for OCR
_, enc = cv2.imencode(".jpg", processed_img)
proc_bytes = enc.tobytes()

try:
    words = ocr_engine.execute_ocr(proc_bytes)
    ocr_ok = True
except Exception as e:
    words = []
    ocr_ok = False
    print(f"  ⚠️  OCR failed (expected if no API key): {e}")

check("OCR engine initialised", ocr_engine is not None)
check("OCR returns list", isinstance(words, list))

if words:
    check("Words have text field", all("text" in w for w in words))
    check("Words have confidence", all("confidence" in w for w in words))
    check("Words have bbox (polygon)", all("bbox" in w and len(w["bbox"]) == 4 for w in words))
    check("Confidence values in [0,1]", all(0 <= w["confidence"] <= 1 for w in words))
    check("Extracted meaningful word count (>5)", len(words) > 5,
          f"Only got {len(words)} words")

    # Verify bbox structure: each bbox should be [[x,y],[x,y],[x,y],[x,y]]
    sample = words[0]["bbox"]
    check("BBox is polygon format", len(sample) == 4 and len(sample[0]) == 2,
          f"Got: {sample}")
    print(f"  ℹ️  Total words extracted: {len(words)}")
    print(f"  ℹ️  Sample: '{words[0]['text']}' (conf={words[0]['confidence']:.3f})")
else:
    print("  ⚠️  Skipping word-level checks (no OCR results)")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Line Reconstruction
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 3: Line Reconstruction")

from services.line_reconstructor import get_line_reconstructor
line_recon = get_line_reconstructor()

if words:
    lines = line_recon.reconstruct_lines(words)
    check("Returns list of lines", isinstance(lines, list))
    check("Lines have text", all("text" in l for l in lines))
    check("Lines have bbox (rect)", all("bbox" in l and len(l["bbox"]) == 4 for l in lines),
          f"Sample bbox: {lines[0]['bbox'] if lines else 'N/A'}")
    check("Lines have confidence", all("confidence" in l for l in lines))
    check("Lines sorted top-to-bottom", 
          all(lines[i]["bbox"][1] <= lines[i+1]["bbox"][1] for i in range(len(lines)-1)) if len(lines) > 1 else True)
    check("Word count preserved", sum(len(l.get("words", [])) for l in lines) == len(words),
          f"Lines contain {sum(len(l.get('words', [])) for l in lines)} words vs {len(words)} input")
    print(f"  ℹ️  Reconstructed {len(lines)} lines from {len(words)} words")
    if lines:
        print(f"  ℹ️  First line: '{lines[0]['text'][:60]}...'")
else:
    lines = []
    print("  ⚠️  Skipping (no OCR words)")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4.3: Grid Detection
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 4.3: Grid Detection")

from services.grid_detector import get_grid_detector
grid_det = get_grid_detector()
grid_result = grid_det.detect_grid(processed_img)

check("Grid returns success flag", "success" in grid_result)
check("Grid returns diagnostics", "diagnostics" in grid_result)

if grid_result["success"]:
    check("Grid has rows", len(grid_result.get("rows", [])) > 0,
          f"Got {len(grid_result.get('rows', []))} rows")
    check("Grid has option_columns", len(grid_result.get("option_columns", [])) > 0,
          f"Got {len(grid_result.get('option_columns', []))} option cols")
    check("Grid has cells", len(grid_result.get("cells", [])) > 0)
    check("Grid has table_bbox", grid_result.get("table_bbox") is not None)
    
    # Validate cell structure
    if grid_result.get("cells"):
        cell = grid_result["cells"][0]
        check("Cell has row_index", "row_index" in cell)
        check("Cell has col_index", "col_index" in cell)
        check("Cell has bbox [x1,y1,x2,y2]", "bbox" in cell and len(cell["bbox"]) == 4)
        check("Cell bbox values are positive", all(v >= 0 for v in cell["bbox"]))
    
    rows = grid_result["rows"]
    cols = grid_result["option_columns"]
    expected_cells = len(rows) * len(cols)
    check("Cell count = rows × cols", len(grid_result["cells"]) == expected_cells,
          f"Got {len(grid_result['cells'])}, expected {expected_cells}")
    
    print(f"  ℹ️  Grid: {len(rows)} data rows × {len(cols)} option columns")
    print(f"  ℹ️  Table bbox: {grid_result['table_bbox']}")
    print(f"  ℹ️  Header rows skipped: {len(grid_result.get('header_rows', []))}")
else:
    print(f"  ⚠️  Grid detection failed — template fallback will be used")
    print(f"  ℹ️  Diagnostics: {json.dumps(grid_result.get('diagnostics', {}), indent=2)}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Extraction Engine
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 4: Field Extraction")

from services.extraction_engine import get_extraction_engine
from services.template_service import get_template_service
ext_engine = get_extraction_engine()
tmpl_svc = get_template_service()
template = tmpl_svc.get_template()

if grid_result["success"]:
    extracted = ext_engine.extract_fields_dynamic(
        img_bgr=processed_img, grid_result=grid_result,
        template=template, lines=lines, all_words=words
    )
    extraction_method = "dynamic_grid"
else:
    extracted = ext_engine.extract_fields(lines, template, processed_img, all_words=words)
    extraction_method = "template_fallback"

check("Extraction returns list", isinstance(extracted, list))
check("Fields extracted (>0)", len(extracted) > 0, f"Got {len(extracted)}")

if extracted:
    f = extracted[0]
    check("Field has 'id'", "id" in f, f"Keys: {list(f.keys())}")
    check("Field has 'raw_value'", "raw_value" in f)
    check("Field has 'confidence'", "confidence" in f)
    check("Field has 'status'", "status" in f)
    check("Field has 'strategy'", "strategy" in f)
    check("Field status is valid enum", 
          f["status"] in ["OK", "NOT_FOUND", "AMBIGUOUS", "NEEDS_REVIEW", "REJECT"],
          f"Got: {f['status']}")
    
    # Check extraction method is set correctly
    if extraction_method == "dynamic_grid":
        check("Dynamic fields have strategy='dynamic_grid'", f["strategy"] == "dynamic_grid",
              f"Got: {f['strategy']}")
    
    # Value distribution analysis
    ok_count = sum(1 for f in extracted if f["status"] == "OK")
    not_found = sum(1 for f in extracted if f["status"] == "NOT_FOUND")
    ambiguous = sum(1 for f in extracted if f["status"] == "AMBIGUOUS")
    print(f"  ℹ️  Method: {extraction_method}")
    print(f"  ℹ️  Fields: {len(extracted)} total, {ok_count} OK, {not_found} NOT_FOUND, {ambiguous} AMBIGUOUS")
    
    # Show first 3 field values
    for i, fld in enumerate(extracted[:3]):
        print(f"  ℹ️  [{fld['id']}] raw='{fld['raw_value']}' status={fld['status']} conf={fld['confidence']}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4.5: Mark Detector
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 4.5: Mark Detector (Unit)")

from services.mark_detector import get_mark_detector
md = get_mark_detector()

# Create a synthetic test: black square on white background
test_marked = np.ones((50, 50, 3), dtype=np.uint8) * 255
cv2.rectangle(test_marked, (10, 10), (40, 40), (0, 0, 0), -1)  # Fill with black
res_marked = md.is_marked(test_marked, [5, 5, 45, 45])
check("Detects filled region as marked", res_marked["is_marked"],
      f"density={res_marked['density']}")

test_empty = np.ones((50, 50, 3), dtype=np.uint8) * 255
res_empty = md.is_marked(test_empty, [5, 5, 45, 45])
check("Detects empty region as unmarked", not res_empty["is_marked"],
      f"density={res_empty['density']}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5/6: Validator
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 5/6: Validation & Cleaning")

from services.validator import get_validator
validator = get_validator()

# Test cleaning
check("Numeric cleaning: 'O1S' → '015'", validator.clean_value("O1S", "numeric") == "015")
check("Date cleaning: '12-05-2025' → '12/05/2025'", validator.clean_value("12-05-2025", "date") == "12/05/2025")
check("Whitespace normalization", validator.clean_value("  hello   world  ") == "hello world")

# Test validation
v1 = validator.validate_field("test", "hello", {"type": "text"})
check("Valid text passes", v1["status"] == "OK")

v2 = validator.validate_field("test", "", {"type": "text", "required": True})
check("Empty required field → REJECT", v2["status"] == "REJECT")

v3 = validator.validate_field("test", "12.34.56", {"type": "numeric"})
check("Multi-decimal non-numeric → warning", v3["status"] == "NEEDS_REVIEW")

v4 = validator.validate_field("test", "5", {"type": "numeric", "min": 1, "max": 3})
check("Out-of-range numeric → warning", v4["status"] == "NEEDS_REVIEW")

# Fuzzy enum matching
v5 = validator.validate_field("test", "Somwhat True", 
    {"type": "text", "allowed_values": ["Not True", "Somewhat True", "Certainly True"]})
check("Fuzzy enum matches 'Somwhat True' → 'Somewhat True'", 
      v5["cleaned"] == "Somewhat True", f"Got: '{v5['cleaned']}'")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7: Confidence Engine
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 7: Confidence Engine")

from services.confidence_engine import get_confidence_engine
conf_engine = get_confidence_engine()

# Test: high quality, good validation
r1 = conf_engine.compute_field_confidence(0.95, "PASS", "OK", "anchor", True)
check("High quality → high score", r1["score"] > 0.7, f"Got: {r1['score']}")

# Test: poor quality penalty
r2 = conf_engine.compute_field_confidence(0.95, "FAIL", "OK", "anchor", True)
check("Quality FAIL → penalized", r2["score"] < r1["score"],
      f"PASS={r1['score']}, FAIL={r2['score']}")

# Test: dynamic_grid method offset
r3 = conf_engine.compute_field_confidence(0.9, "PASS", "OK", "dynamic_grid", True, visual_diff=0.5)
check("dynamic_grid method is recognized", r3["signals"]["method_offset"] == 0.15,
      f"Got: {r3['signals']['method_offset']}")
check("Visual signal included", r3["signals"]["visual_diff"] is not None)

# Test: rejected validation → low score
r4 = conf_engine.compute_field_confidence(0.5, "PASS", "REJECT", "anchor", False)
check("REJECT validation → low score", r4["score"] < 0.5, f"Got: {r4['score']}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8: Decision Engine
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 8: Decision Engine")

from services.decision_engine import get_decision_engine
dec_engine = get_decision_engine()

# Test: all good
d1 = dec_engine.decide([
    {"id": "q1", "confidence": 0.95, "status": "OK", "priority": "critical"},
    {"id": "q2", "confidence": 0.90, "status": "OK", "priority": "critical"},
])
check("All-good fields → AUTO_ACCEPT", d1["status"] == "AUTO_ACCEPT")
check("Overall confidence computed", d1["overall_confidence"] > 0.8)

# Test: low confidence
d2 = dec_engine.decide([
    {"id": "q1", "confidence": 0.95, "status": "OK", "priority": "critical"},
    {"id": "q2", "confidence": 0.30, "status": "OK", "priority": "critical"},
])
check("Low confidence field → NEEDS_REVIEW", d2["status"] == "NEEDS_REVIEW")

# Test: critical rejection
d3 = dec_engine.decide([
    {"id": "q1", "confidence": 0.95, "status": "REJECT", "priority": "critical"},
])
check("Critical REJECT → REJECT", d3["status"] == "REJECT")

# Test: empty fields
d4 = dec_engine.decide([])
check("No fields → ERROR", d4["status"] == "ERROR")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9: Database Persistence
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 9: Database Persistence")

# Use a temporary SQLite DB for testing
TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_e2e_comprehensive.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from services.database import DatabaseService
db = DatabaseService(f"sqlite:///{TEST_DB}")
db.create_tables()

test_req_id = "test-req-001"
test_hash = hashlib.md5(b"test_image").hexdigest()

# Save request
db.save_request(test_req_id, {
    "status": "AUTO_ACCEPT",
    "decision": {"status": "AUTO_ACCEPT", "overall_confidence": 0.92},
    "fields": [
        {"id": "q1", "raw_value": "1", "cleaned_value": "Not True", "confidence": 0.95, "status": "OK"},
        {"id": "q2", "raw_value": "2", "cleaned_value": "Somewhat True", "confidence": 0.88, "status": "OK"},
    ],
    "trace": {"file_path": IMG_PATH}
}, image_hash=test_hash)

# Retrieve
retrieved = db.get_request(test_req_id)
check("Request persisted and retrievable", retrieved is not None)
check("Request ID matches", retrieved["request_id"] == test_req_id)
check("Fields persisted", len(retrieved["fields"]) == 2)
check("Field raw_text stored", retrieved["fields"][0]["raw_text"] == "1")
check("Field cleaned_text stored", retrieved["fields"][0]["cleaned_text"] == "Not True")

# Idempotency
idem_id = db.check_idempotency(test_hash)
check("Idempotency detects duplicate hash", idem_id == test_req_id)
check("Idempotency returns None for new hash", db.check_idempotency("nonexistent") is None)

# Stage traces
db.save_stage_trace(test_req_id, "preprocessing", "SUCCESS", 150)
db.save_stage_trace(test_req_id, "ocr", "SUCCESS", 800)
traces = db.get_stage_traces(test_req_id)
check("Stage traces persisted", len(traces) == 2)
check("Stage trace has duration", traces[0]["duration_ms"] == 150)

# Field correction (Phase 11)
db.update_field(test_req_id, "q1", "Certainly True", corrected_by="test_user")
updated = db.get_request(test_req_id)
q1 = next(f for f in updated["fields"] if f["id"] == "q1")
check("Correction updates cleaned_text", q1["cleaned_text"] == "Certainly True")
check("Previous value preserved", q1["previous_value"] == "Not True")
check("Corrected_by recorded", q1["corrected_by"] == "test_user")
check("Corrected_at timestamp set", q1["corrected_at"] is not None)

# Pagination
db.save_request("test-req-002", {"status": "NEEDS_REVIEW"}, image_hash="hash2")
db.save_request("test-req-003", {"status": "REJECT"}, image_hash="hash3")
all_reqs = db.list_requests(limit=10)
check("List requests returns results", len(all_reqs) >= 3)
filtered = db.list_requests(status="REJECT")
check("Status filter works", all(r["status"] == "REJECT" for r in filtered))

# Cleanup
os.remove(TEST_DB)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 12: Observability
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 12: Observability")

from services.observability import get_observability_service
obs = get_observability_service()

# Test debug overlay generation
test_diag = {
    "fields": [
        {"id": "q1", "bbox": [100, 200, 300, 250], "status": "OK", "cleaned_value": "test"},
        {"id": "q2", "bbox": [100, 260, 300, 310], "status": "NEEDS_REVIEW", "cleaned_value": "review"},
    ]
}
overlay = obs.generate_debug_overlay(processed_img, test_diag)
check("Debug overlay generated", overlay is not None and overlay.shape == processed_img.shape)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 13: Template Service
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 13: Template Service")

check("Default template loads", template is not None)
check("Template has fields", len(template.get("fields", [])) > 0)
check("SDQ template has 25 questions", len(template.get("fields", [])) == 25,
      f"Got {len(template.get('fields', []))}")

# Verify field structure
if template.get("fields"):
    tf = template["fields"][0]
    check("Template field has id", "id" in tf)
    check("Template field has strategy", "strategy" in tf)
    check("Template field has priority", "priority" in tf)

# Fallback
fallback = tmpl_svc.get_template("nonexistent_template")
check("Unknown template → falls back to sdq_v1", fallback["id"] == "sdq_v1")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 14: Cache Service
# ══════════════════════════════════════════════════════════════════════════════
section("Phase 14: Cache Service")

from services.cache_service import get_cache_service
cache = get_cache_service()
check("Cache service initialised", cache is not None)
check("is_connected property works", isinstance(cache.is_connected, bool))
# Cache may or may not be connected depending on env — that's OK
print(f"  ℹ️  Redis connected: {cache.is_connected}")

# ══════════════════════════════════════════════════════════════════════════════
# CROSS-CUTTING: Integration Checks
# ══════════════════════════════════════════════════════════════════════════════
section("Cross-Cutting: Integration Checks")

# Verify config weights sum to 1.0
w = settings.CONFIDENCE_WEIGHTS
check("Confidence weights sum to 1.0", abs(sum(w.values()) - 1.0) < 0.01,
      f"Sum: {sum(w.values())}")

# Verify thresholds are sensible
check("PIXEL_DENSITY_THRESHOLD in (0,1)", 0 < settings.PIXEL_DENSITY_THRESHOLD < 1)
check("AUTO_ACCEPT_THRESHOLD in (0,1)", 0 < settings.AUTO_ACCEPT_THRESHOLD < 1)
check("MIN_FILL_THRESHOLD < PIXEL_DENSITY_THRESHOLD",
      settings.MIN_FILL_THRESHOLD < settings.PIXEL_DENSITY_THRESHOLD)

# Verify grid detector config
check("GRID_LINE_SCALE_HORIZONTAL > 0", settings.GRID_LINE_SCALE_HORIZONTAL > 0)
check("GRID_MIN_ROW_HEIGHT > 0", settings.GRID_MIN_ROW_HEIGHT > 0)

# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'━'*60}")
print(f"  FINAL RESULTS")
print(f"{'━'*60}")
print(f"  ✅ Passed: {PASS}")
print(f"  ❌ Failed: {FAIL}")
print(f"  📊 Total:  {PASS + FAIL}")
print(f"  🎯 Rate:   {PASS/(PASS+FAIL)*100:.1f}%")
print(f"{'━'*60}")

# Save results to file
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_results.json")
with open(output_path, "w") as f:
    json.dump({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "passed": PASS, "failed": FAIL,
        "rate": f"{PASS/(PASS+FAIL)*100:.1f}%",
        "results": RESULTS
    }, f, indent=2)
print(f"\n  Results saved to: {output_path}")

if FAIL > 0:
    print("\n  ❌ FAILURES:")
    for r in RESULTS:
        if not r["passed"]:
            print(f"     • {r['name']}: {r['detail']}")

sys.exit(0 if FAIL == 0 else 1)
