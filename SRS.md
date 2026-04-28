# OCR Form Processing Pipeline — Complete Design Specification (Improved)

> Version 2.0 | All 15 Phases + Cross-Cutting Concerns
> Incorporates architectural improvements, gap resolutions, and production-hardening decisions.

---

## Table of Contents

1. Phase 1 — Image Quality & Preprocessing
2. Phase 2 — OCR + Structured Output
3. Phase 3 — Line Reconstruction
4. Phase 4 — Extraction Engine (Hybrid)
5. Phase 4.5 — Checkbox & Radio Button Detection
6. Phase 5 — Cleaning & Normalization
7. Phase 6 — Validation Layer
8. Phase 7 — Confidence Engine
9. Phase 8 — Decision Engine
10. Phase 9 — Storage & Data Model
11. Phase 10 — API Layer
12. Phase 11 — Review System
13. Phase 12 — Observability, Logging & Debugging
14. Phase 13 — Configuration & Extensibility
15. Phase 14 — Performance, Scaling & Future Readiness
16. Phase 15 — Security, Reliability & Production Readiness
17. Cross-Cutting Concerns

---

---

# PHASE 1 — Image Quality & Preprocessing (Design Specification)

## 1. Objective

Transform any incoming image into a standardized, OCR-ready asset with:

- Correct orientation
- Consistent resolution
- Acceptable visual quality
- Explicit handling of rotation range and page orientation

This layer does not extract data. It prepares data so extraction becomes reliable.

---

## 2. Scope

**Included**
- Image quality validation
- Rotation correction (deskew) within defined range
- Portrait vs landscape orientation normalization
- Size normalization
- Basic enhancement (conditional)
- Output standardization
- Logging + trace

**Excluded**
- OCR
- Field extraction
- Template logic
- Perspective correction (advanced; later phase)

---

## 3. Position in System Architecture

```
Input Source (upload / scanner)
 → Phase 1: Preprocessing
 → Phase 2: OCR
 → Phase 3: Extraction
 → ...
```

This phase is a gatekeeper. It can:
- Allow processing
- Reject input early

---

## 4. Functional Responsibilities

### 4.1 Quality Assessment

Evaluate whether the image is suitable for OCR.

**Checks**
- Blur level (Laplacian variance)
- Brightness / exposure
- Basic readability indicators

**Outcome**
- Accept → continue pipeline
- Reject → return structured reason

**Design Note**
Rejection is critical. Processing low-quality images leads to:
- Incorrect extraction
- Wasted compute
- Poor user trust

---

### 4.2 Orientation Correction (Deskew)

**Problem**
Real-world inputs are often slightly rotated or scanned in the wrong orientation entirely.

**Two-Stage Correction (NEW)**

**Stage 1 — Coarse Orientation (Portrait vs Landscape)**
- Detect if image is landscape (width > height by a factor of ≥ 1.3)
- If landscape → rotate 90° clockwise to normalize to portrait
- Store this as a pre-rotation operation, separate from deskew
- Log: `"orientation_correction": "landscape_to_portrait"`

**Stage 2 — Fine Deskew (Skew Angle Correction)**
- Detect skew angle using Hough Line Transform or projection-profile method
- Apply correction only within the acceptable range (see config)
- Log detected angle and whether correction was applied

**Acceptable Rotation Range (Configurable)**
```json
{
  "deskew": {
    "min_angle_deg": -15,
    "max_angle_deg": 15,
    "reject_if_outside_range": true
  }
}
```

**Rule**
- Skew within range → correct and continue
- Skew outside range → reject with reason `"rotation_out_of_range"`
- Do NOT attempt to fix severely rotated images (>15°); they indicate a scanning error and are better rejected

**Output**
- Corrected image
- Detected rotation angle (stored in metadata)
- Orientation correction applied (boolean)

---

### 4.3 Size Normalization

**Problem**
Images come in arbitrary resolutions.

**Responsibility**
- Standardize width to fixed reference (configurable, e.g., 1200px)
- Maintain aspect ratio (height scales proportionally)
- Store the scale factor applied (used by extraction engine for coordinate mapping)

**Scale Factor Storage (CRITICAL)**
```json
{
  "scale_factor": 0.83,
  "original_width": 1440,
  "original_height": 1980,
  "normalized_width": 1200,
  "normalized_height": 1650
}
```

This scale factor must be passed to downstream phases so that any coordinates defined in templates remain accurate.

**Why this matters**
- Template coordinates depend on consistent scaling
- OCR behaves more predictably at standard resolutions

---

### 4.4 Optional Enhancement (Controlled)

**Purpose**
Improve OCR readability when needed.

**Allowed operations**
- Contrast adjustment (CLAHE)
- Adaptive thresholding (when brightness is poor)

**Constraint**
- Must be conditional, not always applied
- Only apply when quality metrics fall below defined thresholds
- Over-processing can degrade OCR — preserve the original information

**Decision Logic**
```
if blur_score < threshold_blur:
    apply adaptive thresholding
elif brightness < threshold_brightness_low OR brightness > threshold_brightness_high:
    apply contrast normalization
else:
    skip enhancement
```

---

### 4.5 Output Standardization

All processed images must follow a uniform contract:
- Same width baseline (normalized)
- Clean orientation (portrait, deskewed)
- Stored in system with original preserved

This ensures every downstream module works with predictable input.

---

## 5. Output Contract (Strict)

```json
{
  "status": "ok",
  "image_path": "string",
  "original_image_path": "string",
  "width": 1200,
  "height": 1650,
  "scale_factor": 0.83,
  "rotation_angle": 2.4,
  "orientation_corrected": true,
  "enhancement_applied": false,
  "quality_metrics": {
    "blur_score": 142.6,
    "brightness": 178.3
  },
  "processed_at": "timestamp"
}
```

If rejected:
```json
{
  "status": "rejected",
  "reason": "rotation_out_of_range | low_quality_image | unsupported_format | corrupted_file",
  "detail": "Detected rotation angle 42° exceeds maximum allowed 15°"
}
```

---

## 6. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | < 500 ms per image |
| Consistency | Same input → same output (deterministic) |
| Stability | Must not crash on malformed images |
| Observability | Every step must be logged |

---

## 7. Logging & Traceability (Mandatory)

For each image, store:
- Original image path
- Processed image path
- Orientation correction applied (boolean + direction)
- Rotation angle detected
- Scale factor applied
- Quality metrics (blur, brightness)
- Enhancement applied (boolean + type)
- Processing timestamp
- Rejection reason (if applicable)

---

## 8. Design Decisions

**Decision 1 — Reject vs Fix**
- Do NOT attempt to fix severely bad images
- Reject early instead
- Define "severe" explicitly in config (rotation > 15°, blur < 50, etc.)

**Decision 2 — Two-Stage Orientation Correction**
- Stage 1: Portrait vs landscape (coarse, discrete)
- Stage 2: Fine deskew (continuous, within range)
- These are separate operations with separate logging

**Decision 3 — Fixed Width Normalization**
- Chosen over dynamic scaling
- Ensures template compatibility
- Scale factor stored for coordinate mapping

**Decision 4 — Minimal Enhancement**
- Avoid aggressive preprocessing
- Preserve original information
- Apply only when metrics fall below thresholds

**Decision 5 — Store Scale Factor**
- Every downstream phase must receive the scale factor
- This prevents template coordinate misalignment after resize

---

## 9. Must / Should / Good-to-Have

**Must Have (MVP Critical)**
- Quality check (blur + brightness)
- Portrait vs landscape detection
- Deskew within configurable range
- Rejection for out-of-range rotation
- Resize normalization with scale factor storage
- Standard output contract
- Logging

**Should Have**
- Configurable thresholds (not hardcoded)
- Store quality metrics
- Graceful rejection with detailed reason
- Enhancement decision logged

**Good to Have (Later)**
- Perspective correction (4-point transform)
- Shadow removal
- Auto-cropping document boundaries

---

## 10. Risks & Limitations

| Issue | Impact | Mitigation |
|---|---|---|
| Rotation > 15° | Incorrect deskew | Reject with reason |
| Landscape scan | Broken line reconstruction | Stage 1 correction |
| Poor lighting | OCR degradation | Conditional enhancement |
| Shadows / folds | Extraction errors | Known MVP limitation |
| Perspective distortion | Misaligned layout | Future phase |

---

## 11. Integration Constraints

- Output (image + metadata) must be compatible with OCR module
- Image path must be accessible to OCR service
- Scale factor must be passed through pipeline metadata
- Dimensions must be consistent across all images

---

## 12. Acceptance Criteria

This phase is considered complete only if:
1. Images are correctly aligned (visually horizontal, portrait)
2. Output size is consistent across inputs
3. Rotation out of acceptable range is rejected reliably
4. Landscape images are normalized to portrait before deskew
5. Poor-quality images are rejected with clear reason
6. OCR results (manual check) improve after preprocessing
7. Scale factor is stored and accessible to downstream phases
8. Logs are available for every processed image

---

## 13. Common Failure Patterns (Prevent These)

- Skipping quality checks → noisy OCR
- Not separating portrait/landscape from deskew → wrong correction applied
- Over-enhancing images → loss of detail
- Using inconsistent resizing → template mismatch
- Not storing scale factor → extraction coordinates wrong
- Ignoring logging → impossible debugging

---

## 14. Execution Boundary

Do NOT extend this phase into:
- OCR
- Extraction
- ML improvements

Keep it a pure preprocessing layer.

---

---

# PHASE 2 — OCR + Structured Output (Design Specification)

## 1. Objective

Convert a preprocessed image into structured textual data with:
- Word-level text
- Bounding boxes
- Confidence scores

This phase produces the raw intelligence layer that all extraction logic depends on.

---

## 2. Scope

**Included**
- OCR execution using Google Cloud Vision API
- Extraction of hierarchical OCR data
- Conversion to standardized internal format
- Basic text normalization (minimal)
- Raw OCR storage
- Retry with exponential backoff

**Excluded**
- Field extraction
- Template mapping
- Validation
- Decision logic

---

## 3. Position in System Flow

```
Preprocessed Image
 → OCR Engine
 → Structured OCR Output (words + bbox + confidence)
 → Next: Line Reconstruction
```

---

## 4. Functional Responsibilities

### 4.1 OCR Execution

**Engine Choice**

Primary:
- Google Cloud Vision API (`document_text_detection`)

Fallback (future, not now):
- Tesseract

**Reason**
- Better layout understanding
- Word-level confidence
- Bounding box support

**Cost Awareness (IMPORTANT)**
Google Cloud Vision API is priced per 1,000 pages. At scale this becomes a significant cost driver.

Document the following before going to production:
```
Cost model:
- Unit: per 1,000 pages
- Review current GCP pricing at deployment time
- Implement idempotency (Phase 9) to prevent duplicate API calls on re-uploads
- Store raw OCR response to avoid re-calling API on reprocessing
```

This is not optional. Ignoring cost at design time leads to budget surprises at scale.

---

### 4.2 Retry Strategy (Improved)

Apply exponential backoff with a cap:

```
Attempt 1: immediate
Attempt 2: wait 1 second
Attempt 3: wait 3 seconds
Max attempts: 3
If all fail → return structured error
```

Do NOT use a flat "retry once" rule. Transient API failures are common and exponential backoff handles them far better.

```python
retry_config = {
    "max_attempts": 3,
    "backoff_factor": 2,
    "initial_wait_sec": 1,
    "max_wait_sec": 10
}
```

---

### 4.3 OCR Output Parsing

The OCR engine returns hierarchical data:
```
Page → Block → Paragraph → Word → Symbol
```

Your system must:
- Traverse hierarchy
- Extract word-level units
- Ignore symbol-level granularity

---

### 4.4 Word-Level Standardization (Critical)

Convert raw OCR output into a flat list of words.

Each word must contain:
- `text`
- `bounding_box` (4 points)
- `confidence`

---

### 4.5 Bounding Box Format

Standardize to:
```json
[
  [x1, y1],
  [x2, y2],
  [x3, y3],
  [x4, y4]
]
```

**Rules**
- Coordinates must match preprocessed image scale (not original)
- Order must be consistent (clockwise from top-left)
- If OCR returns polygon vertices in different order, normalize on parse

---

### 4.6 Minimal Text Normalization

Apply only safe operations:
- Trim whitespace
- Remove non-printable characters

Do NOT:
- Auto-correct text
- Apply heuristics
- Modify semantics

That comes in Phase 5.

---

## 5. Output Contract (Strict)

```json
[
  {
    "text": "Shivam",
    "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
    "confidence": 0.97
  }
]
```

---

## 6. Raw OCR Storage (Mandatory)

Store complete OCR response separately:

```json
{
  "form_id": "uuid",
  "raw_ocr": "...full API response as JSON...",
  "processed_words": [...],
  "word_count": 142,
  "average_confidence": 0.91,
  "ocr_requested_at": "timestamp",
  "ocr_completed_at": "timestamp",
  "api_attempts": 1
}
```

**Why**
- Debugging
- Reprocessing without API call (cost saving)
- Future improvements without re-OCR

---

## 7. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | OCR latency ~1–2 sec (external); must handle timeout gracefully |
| Reliability | Handle partial OCR failures; never crash on empty results |
| Consistency | Same image → same parsed output |
| Cost Control | Idempotency prevents duplicate API calls |

---

## 8. Error Handling

**Case 1: No text detected**
```json
{
  "status": "failed",
  "reason": "no_text_detected"
}
```

**Case 2: API failure after all retries**
```json
{
  "status": "failed",
  "reason": "ocr_api_failure",
  "attempts": 3
}
```

**Case 3: Partial OCR**
- Accept
- Continue pipeline
- Log word count and average confidence

**Case 4: Timeout**
- Fail gracefully
- Return structured error
- Do NOT leave pipeline in an unknown state

---

## 9. Logging (Mandatory)

Store per OCR call:
- OCR request timestamp
- OCR response timestamp
- Number of API attempts
- Number of words detected
- Average confidence
- Failure reason (if any)

---

## 10. Design Decisions

**Decision 1 — Word-Level Granularity**
Chosen over line-level or paragraph-level for maximum flexibility in later processing.

**Decision 2 — Flat Structure**
Flatten hierarchy early to simplify extraction and reduce complexity.

**Decision 3 — No Early Intelligence**
Do NOT group lines, detect fields, or interpret content here. Keep this phase pure OCR output.

**Decision 4 — Exponential Backoff**
Flat "retry once" is insufficient. Exponential backoff with a cap handles transient failures properly.

**Decision 5 — Cost as a First-Class Concern**
Raw OCR storage is not just for debugging. It is the primary mechanism for cost control via reprocessing without re-calling the API.

---

## 11. Must / Should / Good-to-Have

**Must Have**
- OCR integration
- Word-level extraction
- Bounding boxes
- Confidence scores
- Standard output format
- Raw OCR storage
- Exponential backoff retry

**Should Have**
- Cost tracking (pages processed counter)
- Basic normalization
- Logging metrics

**Good to Have (Later)**
- Multi-language support
- OCR engine fallback (Tesseract)
- Confidence-based filtering

---

## 12. Risks & Limitations

| Issue | Impact |
|---|---|
| Handwriting | Low accuracy |
| Noisy images | Incorrect text |
| Overlapping text | Incorrect grouping |
| Special characters | Misread |
| API pricing increase | Budget impact |

---

## 13. Integration Constraints

- Input must come from preprocessing layer
- Scale factor from Phase 1 must be confirmed — bounding box coordinates must match preprocessed (normalized) image scale
- Output must feed into line reconstruction phase

---

## 14. Acceptance Criteria

This phase is complete only if:
1. OCR returns word-level structured output
2. Bounding boxes align visually with words on the normalized image
3. Confidence scores are available per word
4. Raw OCR is stored and retrievable
5. Works on at least 3 different sample images
6. API failures are handled without pipeline crash
7. Retry mechanism is verified with simulated failures

---

## 15. Common Failure Patterns

- Using plain text instead of structured OCR
- Ignoring bounding boxes
- Modifying text too early
- Not storing raw OCR (forces expensive re-calls)
- Flat retry strategy (not exponential)
- No timeout handling

---

---

# PHASE 3 — Line Reconstruction (Design Specification)

## 1. Objective

Convert OCR word-level output into structured, human-readable lines to enable:
- Reliable anchor detection
- Contextual understanding
- Robust extraction

This phase transforms: **unordered words → ordered lines**

---

## 2. Scope

**Included**
- Grouping words into lines
- Sorting words within lines
- Generating line-level text
- Preserving spatial relationships
- Ordering lines top → bottom

**Excluded**
- Field extraction
- Template matching
- Validation
- Multi-column layout detection (known constraint)

---

## 3. Position in System Flow

```
OCR Output (words)
 → Line Reconstruction
 → Structured Lines
 → Next: Extraction Engine (anchor + bbox)
```

---

## 4. Core Problem

OCR gives:
```
["Name", ":", "Shivam", "Kumar"]
```
as separate words with coordinates.

But forms are interpreted as:
```
"Name: Shivam Kumar"
```

Without this phase:
- Anchor detection becomes unreliable
- Extraction becomes fragmented

---

## 5. Functional Responsibilities

### 5.1 Word Grouping into Lines

**Principle**
Words that lie on the same horizontal band belong to the same line.

**Logic**
- Compare Y-coordinates (centroid of bounding box) of words
- Group words whose vertical positions fall within the Y-proximity threshold

**Key Concept: Y-Proximity Threshold**
- Define as relative percentage of image height (preferred) OR fixed pixels
- Words within this threshold are considered the same line
- Configurable via system config (not hardcoded)

```json
{
  "line_reconstruction": {
    "y_threshold_px": 12,
    "y_threshold_relative": 0.012
  }
}
```

Use relative threshold when images vary in resolution. Use fixed pixels when input is always normalized (preferred after Phase 1 normalization).

---

### 5.2 Sorting Words within Each Line

Once grouped:
- Sort words left → right using the X-coordinate of the left edge of their bounding box

This ensures correct reading order.

---

### 5.3 Line Ordering

After all lines are formed:
- Sort lines top → bottom using the Y-coordinate of the top edge of the line bounding box

This produces a human-readable, natural document order.

---

### 5.4 Line Formation

Each line must produce:
- Combined text (words joined with single space)
- Ordered word list with individual bboxes preserved
- Bounding box for the entire line

**Line Bounding Box Computation**
```
x1 = min(x_left of all words)
y1 = min(y_top of all words)
x2 = max(x_right of all words)
y2 = max(y_bottom of all words)
```

This creates a tight container box for the full line.

---

## 6. Output Contract (Strict)

```json
[
  {
    "line_index": 0,
    "text": "Name: Shivam Kumar",
    "words": [
      {"text": "Name", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "confidence": 0.98},
      {"text": ":", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "confidence": 0.95},
      {"text": "Shivam", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "confidence": 0.97},
      {"text": "Kumar", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "confidence": 0.96}
    ],
    "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
    "word_count": 4
  }
]
```

---

## 7. Multi-Column Layout — Known Architectural Constraint (IMPORTANT)

**This is not just a limitation. It is an explicit architectural boundary.**

The Y-proximity threshold approach correctly handles single-column forms. For multi-column layouts (e.g., a form where the left half has Name/DOB fields and the right half has separate fields), threshold-based grouping will produce incorrect mixed lines.

**Explicit Decision**
Multi-column support is OUT OF SCOPE for this phase and the current pipeline version.

**Implications**
- Forms with multi-column layouts must be documented as unsupported
- Template design should avoid multi-column where possible
- If multi-column forms must be supported in future, this phase requires redesign using column-detection logic before line grouping

**Safeguard**
Add a flag in the template config:
```json
{
  "form_type": "form_v1",
  "layout": "single_column"
}
```
If `layout` is not `"single_column"`, the pipeline should warn (not reject at MVP) and log accordingly.

---

## 8. Handling Multi-Line Fields

Some fields (e.g., address) span multiple lines.

**Rule**
- Do NOT merge lines automatically here
- Keep them as separate line objects
- Merging happens during extraction (Phase 4) where field context is known

---

## 9. Handling Noise Words

Ignore:
- Words with bounding boxes below a minimum area threshold (configurable)
- Words with confidence below a minimum threshold (configurable, e.g., < 0.3)

But do NOT aggressively remove content. Preserve borderline cases and let later phases handle them.

---

## 10. Design Decisions

**Decision 1 — Line as Primary Unit**
System shifts from word-based → line-based understanding. This is essential for anchor detection and contextual parsing.

**Decision 2 — Threshold-Based Grouping**
Chosen over ML clustering or complex layout analysis because:
- Fast
- Deterministic
- Sufficient for single-column structured forms

**Decision 3 — Preserve Word-Level Data**
Even after forming lines, keep original word data (text + bbox + confidence) intact within each line object.

**Decision 4 — Multi-Column is an Explicit Boundary**
Not a silent failure mode. Document it, log it, and handle it explicitly in template config.

**Decision 5 — Relative Y-Threshold After Normalization**
Since Phase 1 normalizes image width, using a fixed-pixel Y-threshold is more predictable than relative percentage.

---

## 11. Must / Should / Good-to-Have

**Must Have**
- Word grouping into lines (Y-threshold)
- Left-to-right word sorting
- Top-to-bottom line ordering
- Line text generation
- Line bounding boxes
- Word-level data preserved

**Should Have**
- Configurable Y-threshold
- Basic noise filtering (min confidence, min bbox area)
- Layout type flag in template
- Consistent line indexing

**Good to Have (Later)**
- Adaptive threshold (based on detected font size)
- Column detection
- Merging broken lines (e.g., hyphenated words)

---

## 12. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | < 100 ms per image |
| Determinism | Same OCR input → same line output |
| Stability | Must handle irregular spacing and sparse words |

---

## 13. Risks & Limitations

| Issue | Impact |
|---|---|
| Uneven line spacing | Incorrect grouping |
| Overlapping text | Mixed lines |
| Skewed images (not fixed earlier) | Broken lines |
| Multi-column layouts | Mis-grouping (explicit constraint) |

---

## 14. Logging (Mandatory)

Store per image:
- Number of lines created
- Average words per line
- Y-threshold value used
- Number of noise words filtered
- Layout warning flag (if multi-column suspected)

---

## 15. Integration Constraints

- Input must be word-level OCR output from Phase 2
- Output feeds into extraction engine (Phase 4)
- Coordinates must remain unchanged from OCR output (no re-scaling at this phase)

---

## 16. Acceptance Criteria

This phase is complete only if:
1. Words are correctly grouped into lines
2. Lines read naturally (human-readable)
3. Order is correct (top → bottom, left → right)
4. Works across multiple sample images
5. Bounding boxes correctly enclose all words in a line
6. Word-level data is preserved inside line objects
7. Multi-column forms produce a logged warning

---

## 17. Common Failure Patterns

- Grouping based on X instead of Y
- Incorrect threshold causing merged lines across rows
- Losing word-level data after forming lines
- Not sorting lines top → bottom
- Treating multi-column as a silent bug rather than an explicit constraint

---

---

# PHASE 4 — Extraction Engine (Hybrid: Anchor + BBox + Line-Based)

## 1. Objective

Convert structured OCR (lines + words) into field-level data using a multi-strategy extraction system that is robust to layout variations.

This phase produces:
- Field values (raw, uncleaned)
- Extraction method used
- Extraction confidence (raw, from OCR only)

---

## 2. Scope

**Included**
- Anchor-based extraction (primary)
- BBox/Zone-based extraction (fallback)
- Line-based extraction (backup)
- Strategy selection and fallback logic
- Basic field-level confidence (from OCR only)
- Placeholder status for checkbox/radio fields (handled in Phase 4.5)

**Excluded**
- Text cleaning/normalization (Phase 5)
- Validation and correction (Phase 6)
- Decision engine
- Checkbox/radio detection (Phase 4.5)

---

## 3. Position in System Flow

```
Lines (from Phase 3)
 + Words (from Phase 2)
 + Template (form_v1)
 + Scale Factor (from Phase 1)
 → Extraction Engine
 → Field Values (raw)
 → Phase 4.5: Checkbox Detection
 → Next: Cleaning Layer (Phase 5)
```

---

## 4. Core Design — Multi-Strategy Priority

```
1. Anchor-based (primary)
2. Zone/BBox-based (fallback)
3. Line-based (backup)
```

The engine must attempt in order and stop on first acceptable result.

---

## 5. Template Requirements (Extended)

Each field must define how it can be extracted. Template coordinates must be expressed as **ratios relative to normalized image width and height** (not absolute pixels), because Phase 1 normalizes the image size.

```json
{
  "name": "full_name",
  "type": "text",
  "priority": "critical",
  "required": true,
  "strategies": {
    "anchor": {
      "labels": ["Name", "Full Name"],
      "direction": "right",
      "max_distance_ratio": 0.21
    },
    "zone": {
      "bbox_ratio": [0.1, 0.2, 0.4, 0.05],
      "expand_ratio": 0.15
    },
    "line": {
      "contains": ["Name"]
    }
  },
  "validation": {
    "required": true
  }
}
```

**CRITICAL: Relative Coordinates**

All distances and bounding boxes in templates must use **ratios** (0.0 to 1.0), not pixels:

- `max_distance_ratio` = max distance as a ratio of normalized image width
- `bbox_ratio` = [x_ratio, y_ratio, width_ratio, height_ratio]

This ensures template definitions remain valid regardless of input image size, as long as Phase 1 normalization is applied consistently.

At runtime, convert to absolute pixels using the normalized image dimensions before applying.

---

## 6. Strategy 1 — Anchor-Based Extraction (Primary)

**Concept**
Mimics human reading: Find label → move in direction → read value

**Responsibilities**
1. Locate anchor word(s) in reconstructed lines
2. Identify anchor bounding box position
3. Extract words in the defined direction up to max distance

**Direction Options**
- `right` → same line, increasing X
- `below` → lines below the anchor line, within vertical distance

**Distance Constraint**
- Prevents over-capturing unrelated text
- Defined per field as `max_distance_ratio` (converted to pixels at runtime)
- Hard cutoff — no words beyond this distance are included

**Multiple Anchor Labels**
- Try each label in order
- Stop on first match
- Allows for OCR variation (e.g., "Name" vs "Full Name")

**Output**
```json
{
  "field": "full_name",
  "value": "Shivam Kumar",
  "method": "anchor",
  "anchor_found": "Name",
  "words_used": [...],
  "confidence": 0.97,
  "status": "extracted"
}
```

**Failure Conditions**
- No anchor label found in any line
- Anchor found but no text in specified direction within distance
- Direction is `below` but no lines exist below anchor

---

## 7. Strategy 2 — Zone / BBox-Based Extraction (Fallback)

**Concept**
Extract all text within a defined region of the image.

**Responsibilities**
1. Convert relative bbox ratios to absolute pixel coordinates using normalized image size
2. Expand bbox using expand_ratio to handle slight misalignments
3. Select words whose bounding box centroid falls inside the expanded region

**Expansion**
```
expanded_x1 = x1 - (width * expand_ratio)
expanded_y1 = y1 - (height * expand_ratio)
expanded_x2 = x2 + (width * expand_ratio)
expanded_y2 = y2 + (height * expand_ratio)
```

**Advantages**
- Works for fixed layouts
- Fast and deterministic

**Limitations**
- Sensitive to misalignment
- Depends on preprocessing quality
- Breaks if form layout shifts

---

## 8. Strategy 3 — Line-Based Extraction (Backup)

**Concept**
Use entire line when structure is predictable.

**Logic**
- Find line containing keyword (e.g., "Phone")
- Extract text after keyword on the same line

**Example**
Input line: `"Phone: 9876543210"`
Output: `"9876543210"`

**Use Case**
- When anchor detection partially fails
- When bbox is unreliable
- Simple colon-separated fields

---

## 9. Strategy Selection Logic

```
for each field in template:
    try anchor strategy
    if success → accept, stop
    else:
        try zone strategy
        if success → accept, stop
        else:
            try line strategy
            if success → accept, stop
            else:
                mark field as "failed"
                log all strategy attempts
```

**Success Criteria (per strategy)**
- Non-empty value after whitespace trim
- Value length within reasonable bounds (not just a single stray character)
- Average word confidence above minimum threshold

---

## 10. Field Output Contract

```json
{
  "field": "full_name",
  "value": "Shivam Kumar",
  "method": "anchor",
  "confidence": 0.97,
  "words_used": [
    {"text": "Shivam", "bbox": [...], "confidence": 0.98},
    {"text": "Kumar", "bbox": [...], "confidence": 0.96}
  ],
  "strategies_attempted": ["anchor"],
  "status": "extracted"
}
```

If failed:
```json
{
  "field": "full_name",
  "value": null,
  "method": null,
  "confidence": 0.0,
  "strategies_attempted": ["anchor", "zone", "line"],
  "status": "failed"
}
```

---

## 11. Confidence (Initial)

At this phase:
```
confidence = average OCR confidence of words used for extraction
```

No validation applied yet. True confidence score is computed in Phase 7.

---

## 12. Handling Checkbox / Radio Fields

**Rule: Do NOT attempt detection here.**

For checkbox/radio fields, the extraction engine marks them as pending:

```json
{
  "field": "gender",
  "status": "pending_detection",
  "method": null,
  "zone_bbox": [0.3, 0.45, 0.2, 0.04]
}
```

Phase 4.5 handles all checkbox and radio button detection. The zone bbox is passed forward for Phase 4.5 to use.

---

## 13. Handling Multi-Line Field Values

For `textarea` type fields (e.g., address) where value spans multiple lines:
- Collect all lines within the defined zone or below anchor (up to max distance)
- Join with space (configurable to newline)
- Preserve order top → bottom

---

## 14. Logging (Mandatory)

Store per field:
- Strategy attempted (in order)
- Strategy selected (or "failed")
- Anchor found (label matched, or null)
- Words extracted
- Distance from anchor to last word
- Confidence score
- Status

---

## 15. Design Decisions

**Decision 1 — Hybrid Strategy**
Single-method extraction is unreliable in real-world forms. Multiple strategies provide resilience.

**Decision 2 — Anchor First**
Most robust against minor layout variation because it uses semantic labels rather than positional assumptions.

**Decision 3 — Relative Coordinates (CRITICAL)**
All template coordinates must be ratios, not pixels, to survive Phase 1 normalization.

**Decision 4 — Early Exit**
Stop after first valid extraction to reduce noise and compute.

**Decision 5 — Checkbox Deferred to Phase 4.5**
Checkbox detection requires different techniques (pixel analysis / region classification). Mixing it here would break the clean extraction logic.

---

## 16. Must / Should / Good-to-Have

**Must Have**
- Anchor-based extraction
- Zone-based fallback
- Line-based backup
- Strategy selection logic
- Relative coordinate handling
- Checkbox placeholder output
- Field-level output format

**Should Have**
- Multiple anchor labels per field
- Configurable distance thresholds
- Expandable bbox
- Strategies-attempted log

**Good to Have (Later)**
- Fuzzy matching for anchor labels
- Semantic similarity matching
- Multi-anchor support (field with two possible label locations)

---

## 17. Risks & Limitations

| Issue | Impact |
|---|---|
| Missing anchor label | Fallback required |
| OCR misread label | Anchor fails |
| Overlapping text | Wrong extraction |
| Dense forms | Over-capture |
| Template uses absolute pixels | Breaks after normalization |

---

## 18. Acceptance Criteria

This phase is complete only if:
1. At least 3 fields extracted correctly per sample form
2. Anchor works reliably on sample forms
3. Fallback methods trigger when anchor fails
4. Output includes method + strategies attempted + confidence
5. No crashes on missing anchors
6. Relative coordinates verified correct after normalization
7. Checkbox/radio fields produce pending_detection status

---

---

# PHASE 4.5 — Checkbox & Radio Button Detection (Design Specification)

## 1. Objective

Detect the selected state of checkbox and radio button fields using image analysis within defined zones.

This phase bridges the gap between text extraction (Phase 4) and field-level data (Phase 5) for non-text fields.

---

## 2. Scope

**Included**
- Checkbox state detection (checked / unchecked)
- Radio button group detection (which option is selected)
- Zone-based image analysis
- Confidence scoring for detection

**Excluded**
- Text field extraction
- Validation
- UI rendering

---

## 3. Position in System Flow

```
Phase 4 Output (pending_detection fields)
 + Preprocessed Image
 + Template (zone definitions for checkboxes)
 → Phase 4.5: Checkbox/Radio Detection
 → Field Values (checked/unchecked, selected_option)
 → Phase 5: Cleaning
```

---

## 4. Detection Approach

### 4.1 Checkbox Detection (Binary)

**Method: Pixel Fill Density Analysis**

For each checkbox region:
1. Crop the image to the checkbox zone (using zone bbox from template)
2. Convert to grayscale
3. Apply binary threshold
4. Calculate the ratio of dark pixels to total pixels in the zone

```
fill_ratio = dark_pixel_count / total_pixel_count

if fill_ratio >= threshold_checked:
    state = "checked"
else:
    state = "unchecked"
```

Default threshold (configurable): `0.15` (15% fill = checked)

**Why fill density?**
Checkboxes when checked contain a visible mark (X, tick, filled box) which increases dark pixel density. Empty checkboxes are largely white.

---

### 4.2 Radio Button Detection (Group)

**Method: Comparative Fill Density**

For a group of radio buttons:
1. Crop each option's zone
2. Compute fill density for each
3. Select the option with the highest fill density (if above minimum threshold)

```
for each option in group:
    compute fill_density(option_zone)

selected = option with max fill_density if max > threshold_min
if no option exceeds threshold_min:
    selected = None (no selection detected)
```

---

### 4.3 Template Definition for Checkboxes

```json
{
  "name": "gender",
  "type": "radio",
  "priority": "important",
  "options": ["Male", "Female", "Other"],
  "zones": [
    {"label": "Male", "bbox_ratio": [0.1, 0.45, 0.03, 0.025]},
    {"label": "Female", "bbox_ratio": [0.2, 0.45, 0.03, 0.025]},
    {"label": "Other", "bbox_ratio": [0.32, 0.45, 0.03, 0.025]}
  ],
  "detection": {
    "min_fill_ratio": 0.12,
    "checked_fill_ratio": 0.15
  }
}
```

---

## 5. Output Contract

**Checkbox (binary):**
```json
{
  "field": "terms_accepted",
  "type": "checkbox",
  "value": "checked",
  "fill_ratio": 0.22,
  "confidence": 0.85,
  "method": "pixel_density",
  "status": "extracted"
}
```

**Radio group:**
```json
{
  "field": "gender",
  "type": "radio",
  "value": "Male",
  "fill_ratios": {
    "Male": 0.31,
    "Female": 0.04,
    "Other": 0.03
  },
  "confidence": 0.88,
  "method": "comparative_density",
  "status": "extracted"
}
```

If no selection detected:
```json
{
  "field": "gender",
  "value": null,
  "status": "no_selection_detected"
}
```

---

## 6. Confidence Scoring

```
confidence = 1.0 - (second_highest_fill / highest_fill)
```

If the top option has 0.31 fill and second has 0.04:
- Confidence = 1.0 - (0.04 / 0.31) = 0.87 (high separation = high confidence)

If top is 0.18 and second is 0.16:
- Confidence = 1.0 - (0.16 / 0.18) = 0.11 (low separation = low confidence → needs review)

---

## 7. Must / Should / Good-to-Have

**Must Have**
- Checkbox binary detection
- Radio group comparative detection
- Zone-based cropping
- Confidence score
- Output consistent with Phase 4 field format

**Should Have**
- Configurable thresholds per field
- Handling of "no selection" state
- Logging of fill ratios

**Good to Have (Later)**
- ML-based checkbox classifier
- Pre-printed checkbox detection (distinguish box border from fill)
- Handwritten tick vs printed mark differentiation

---

## 8. Acceptance Criteria

1. Checked checkboxes correctly identified
2. Unchecked checkboxes correctly identified
3. Radio button selection correctly identified from group
4. "No selection" handled without crash
5. Confidence reflects detection certainty

---

---

# PHASE 5 — Cleaning & Normalization (Design Specification)

## 1. Objective

Refine raw extracted field values into clean, standardized, and usable data by:
- Correcting common OCR errors
- Normalizing formats
- Removing noise
- Preparing data for validation

This phase improves accuracy without human intervention.

---

## 2. Scope

**Included**
- Text cleaning (generic + field-specific)
- OCR error correction (heuristic-based, context-aware)
- Formatting normalization
- Whitespace and symbol handling

**Excluded**
- Validation (Phase 6)
- Confidence score update (Phase 7)
- Decision logic

---

## 3. Position in System Flow

```
Extracted Fields (raw, from Phase 4 and 4.5)
 → Cleaning & Normalization
 → Cleaned Fields
 → Next: Validation Layer (Phase 6)
```

---

## 4. Core Principle

**Do not guess meaning. Only correct high-confidence, predictable OCR errors.**

And critically: **apply corrections only when field type is confirmed**. Never apply numeric corrections to text/name fields, even if those fields contain unexpected numeric-looking characters.

---

## 5. Functional Responsibilities

### 5.1 Generic Cleaning (All Fields)

Apply to every field regardless of type:
- Trim leading/trailing whitespace
- Collapse multiple spaces → single space
- Remove non-printable characters (control characters, null bytes)
- Normalize common punctuation (curly quotes → straight)

---

### 5.2 OCR Error Correction (Heuristic, Context-Aware)

Correct predictable OCR mistakes **only when field type is confirmed numeric**.

| Error | Correction | Condition |
|---|---|---|
| `O` → `0` | Numeric fields only | Field type = number OR phone |
| `I` or `l` → `1` | Numeric fields only | Field type = number OR phone |
| `S` → `5` | Numeric fields only (cautious) | Optional, configurable |
| Extra spaces | Remove | All numeric fields |

**CRITICAL RULE**
These corrections MUST ONLY apply when:
1. The field's `type` in the template is `"number"`, `"phone"`, or other explicitly numeric type
2. AND the character appears in a numeric context

Never apply character substitutions globally across all fields. A name field with an `O` must NOT have it replaced with `0`.

**Implementation Guard**
```python
def apply_ocr_corrections(value, field_type, corrections_config):
    if field_type not in ["number", "phone", "age", "numeric"]:
        return value, []  # Do not touch non-numeric fields
    # Apply corrections...
```

---

### 5.3 Field-Type Specific Cleaning

**Numeric Fields (phone, age, count)**
- Remove spaces
- Remove non-digit characters (after OCR correction)
- Apply OCR corrections (O→0, I→1)
- Strip country codes if not expected

**Name Fields**
- Remove digits (they are OCR noise in name fields)
- Preserve spaces between words
- Optional: Title-case normalization (configurable)
- Do NOT apply numeric OCR corrections

**Textarea (address, description)**
- Preserve punctuation
- Allow multi-line merge with space separator (configurable)
- Normalize spacing

**Categorical Fields (radio/checkbox values)**
- Normalize case to lowercase
- Trim whitespace
- Match against allowed values list (soft match, strict match is Phase 6)

---

### 5.4 Length & Structure Normalization

- Remove obvious noise: single stray characters that are clearly artifacts (e.g., a lone `:` or `.`)
- Enforce soft length bounds (log warnings, do not reject here — rejection is Phase 6's job)

---

### 5.5 Multi-Line Handling (textarea)

If value spans multiple lines:
- Join using space (default) or newline (configurable per field)
- Preserve readability

```json
{
  "name": "address",
  "type": "textarea",
  "multiline_join": "newline"
}
```

---

## 6. Output Contract

```json
{
  "field": "phone",
  "original_value": "98O65I321O",
  "cleaned_value": "9806513210",
  "changes_applied": [
    "trim_whitespace",
    "ocr_correction_O_to_0",
    "ocr_correction_I_to_1"
  ],
  "field_type": "phone"
}
```

For a name field with the same input (no corrections applied):
```json
{
  "field": "full_name",
  "original_value": "  Shivam  Kumar  ",
  "cleaned_value": "Shivam Kumar",
  "changes_applied": ["trim_whitespace", "collapse_spaces"],
  "field_type": "text"
}
```

---

## 7. Change Tracking (Mandatory)

For every field:
- Store original value
- Store cleaned value
- Store list of all transformations applied
- Store field type used to determine cleaning rules

This supports debugging, auditing, and ML improvement later.

---

## 8. Design Decisions

**Decision 1 — Non-Destructive Cleaning**
Always preserve original value. Never overwrite.

**Decision 2 — Heuristic-Only**
No ML or semantic guessing at this stage.

**Decision 3 — Field-Type-Aware Cleaning (CRITICAL)**
Different rules per field type. OCR corrections are ONLY applied to confirmed numeric fields.

**Decision 4 — Configurable Rules**
All replacement rules come from config, not hardcoded.

```json
{
  "cleaning": {
    "numeric_corrections": {
      "O": "0",
      "I": "1",
      "l": "1"
    },
    "apply_s_to_5": false
  }
}
```

---

## 9. Must / Should / Good-to-Have

**Must Have**
- Generic cleaning (trim, collapse, non-printable removal)
- Numeric correction (O→0, I→1) ONLY for numeric field types
- Field-type specific rules
- Change tracking (original + cleaned + transformations)

**Should Have**
- Configurable cleaning rules
- Field-type guard (prevents wrong corrections)
- Multi-line join configuration

**Good to Have (Later)**
- Dictionary-based name corrections
- Language-aware normalization
- Spell-check integration (cautious)

---

## 10. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | < 50 ms per form |
| Determinism | Same input + same field type → same cleaned output |
| Safety | No modification of semantic meaning |

---

## 11. Risks & Limitations

| Issue | Impact | Safeguard |
|---|---|---|
| Over-correction | Wrong data | Apply corrections only to numeric types |
| Ambiguous characters | Wrong replacement | Make S→5 optional (disabled by default) |
| Field type mismatch in template | Wrong cleaning applied | Validate template field types at startup |

---

## 12. Logging (Mandatory)

Store per field:
- Original value
- Cleaned value
- Field type
- Transformations applied
- Whether any corrections were made

---

## 13. Integration Constraints

- Input from extraction phase (Phase 4 / 4.5)
- Output to validation layer (Phase 6)
- Must preserve field structure and metadata
- Must receive field type from template — this is not optional

---

## 14. Acceptance Criteria

This phase is complete only if:
1. Common OCR errors in numeric fields are corrected
2. Name fields are NOT modified by numeric corrections
3. Original values are preserved in all cases
4. Changes are traceable per field
5. No over-aggressive modifications
6. Field-type guard verified with test cases

---

## 15. Common Failure Patterns

- Blindly replacing O→0 in all fields regardless of type
- Modifying semantic meaning (e.g., removing valid symbols from addresses)
- Not tracking changes
- Hardcoding cleaning rules
- Missing the field-type guard

---

---

# PHASE 6 — Validation Layer (Design Specification)

## 1. Objective

Assess whether cleaned field values are correct, complete, and acceptable based on defined rules.

This phase does not modify data. It only:
- Verifies correctness
- Flags issues with severity level
- Produces validation signals for the confidence engine

---

## 2. Scope

**Included**
- Required field checks
- Format validation (regex, type)
- Range checks
- Length validation
- Categorical validation
- Soft vs hard error classification
- Validation result structuring

**Excluded**
- Data correction (already done in Phase 5)
- Confidence scoring (Phase 7)
- Decision logic (Phase 8)

---

## 3. Position in System Flow

```
Cleaned Fields (from Phase 5)
 → Validation Layer
 → Validation Results (with severity)
 → Next: Confidence Engine (Phase 7)
```

---

## 4. Core Principle

**Validation must be strict, deterministic, and explainable. Errors must carry severity so downstream phases can treat them proportionally.**

---

## 5. Functional Responsibilities

### 5.1 Required Field Validation

**Rule**
- If `required = true` AND value is null or empty → hard error (`missing_required`)
- Severity: `error` (hard)

---

### 5.2 Format Validation (Regex-Based)

Each field defines expected format in template config.

| Field | Rule | Severity |
|---|---|---|
| phone | 10-digit, starts with 6-9 | error |
| email (future) | standard email pattern | error |
| name | alphabetic + spaces | warning |
| age | 1-3 digit number | error |

**Output**
- `valid: true / false`
- `errors` array with error code + severity

---

### 5.3 Type Validation

| Type | Check | Severity |
|---|---|---|
| number | digits only after cleaning | error |
| text | non-empty string | warning |
| categorical | must match allowed options | error |

---

### 5.4 Length Validation

Defined per field in config.

| Field | Rule | Severity |
|---|---|---|
| phone | exactly 10 digits | error |
| name | ≥ 2 characters | warning |
| age | 1–3 digits | warning |

---

### 5.5 Range Validation

For numeric fields:

| Field | Range | Severity |
|---|---|---|
| age | 0–120 | error |
| any count | ≥ 0 | error |

---

### 5.6 Categorical Validation

For radio/checkbox fields:
- Value must be in allowed options list
- Case-insensitive comparison after normalization
- If not in list → `invalid_option` error (hard)

---

## 6. Soft vs Hard Validation (CRITICAL IMPROVEMENT)

This is the most important enhancement over a simple pass/fail model.

**Hard Errors (severity: "error")**
- The value is definitively wrong
- Confidence engine will assign validation_confidence = 0.0
- Decision engine will likely route to review

Examples: missing required field, phone with 7 digits, age = 200

**Soft Errors (severity: "warning")**
- The value is suspicious but possibly correct
- Confidence engine will assign validation_confidence = 0.5 (partial penalty)
- Decision engine considers it a review candidate but not a hard failure

Examples: name contains a digit (could be OCR noise), value is shorter than expected but not impossible

**This distinction prevents the confidence cliff** where a field with one minor anomaly collapses to zero validation confidence.

---

## 7. Output Contract

```json
{
  "field": "phone",
  "value": "9806513210",
  "valid": true,
  "errors": [],
  "warnings": []
}
```

With hard error:
```json
{
  "field": "phone",
  "value": "123",
  "valid": false,
  "errors": [
    {"code": "invalid_format", "severity": "error", "message": "Does not match ^[6-9]\\d{9}$"},
    {"code": "length_mismatch", "severity": "error", "message": "Expected 10 digits, got 3"}
  ],
  "warnings": []
}
```

With soft warning:
```json
{
  "field": "full_name",
  "value": "Shivam9Kumar",
  "valid": true,
  "errors": [],
  "warnings": [
    {"code": "contains_digit", "severity": "warning", "message": "Name field contains numeric character"}
  ]
}
```

---

## 8. Error Types (Standardized)

Hard errors (`severity: "error"`):
- `missing_required`
- `invalid_format`
- `invalid_type`
- `length_mismatch`
- `out_of_range`
- `invalid_option`

Soft warnings (`severity: "warning"`):
- `contains_digit` (in name fields)
- `shorter_than_expected`
- `unusual_character`
- `capitalization_anomaly`

---

## 9. Template Extension (Validation Rules)

```json
{
  "name": "phone",
  "type": "text",
  "required": true,
  "validation": {
    "regex": "^[6-9]\\d{9}$",
    "length": {"exact": 10},
    "severity_overrides": {
      "length_mismatch": "error",
      "invalid_format": "error"
    }
  }
}
```

---

## 10. Design Decisions

**Decision 1 — Non-Mutating Layer**
Validation does not change data under any circumstance.

**Decision 2 — Rule-Based Only**
No ML or heuristics.

**Decision 3 — Severity-Based Errors (CRITICAL)**
Hard errors vs warnings allows the confidence engine to respond proportionally. Without this, any validation issue collapses confidence to zero.

**Decision 4 — Field-Driven Rules from Template**
All validation rules come from template/config. No hardcoded rules.

---

## 11. Must / Should / Good-to-Have

**Must Have**
- Required field check
- Regex validation
- Type validation
- Length validation
- Severity classification (error vs warning)
- Standardized error output

**Should Have**
- Configurable rules per field
- Multiple error reporting per field
- Categorical validation

**Good to Have (Later)**
- Cross-field validation (e.g., consistency between two related fields)
- Dynamic rule updates
- External validation APIs

---

## 12. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | < 20 ms per form |
| Determinism | Same input → same result |

---

## 13. Risks & Limitations

| Issue | Impact | Safeguard |
|---|---|---|
| Overly strict rules | False negatives | Use warnings for borderline cases |
| Weak rules | False positives | Review rules with real sample data |
| OCR noise | Validation failures | Phase 5 cleaning reduces this |

---

## 14. Logging (Mandatory)

Store per field:
- Cleaned value
- Validation result (valid/invalid)
- Error codes with severity
- Warning codes

---

## 15. Acceptance Criteria

This phase is complete only if:
1. Required fields are correctly flagged with `missing_required`
2. Invalid formats are detected with correct severity
3. Valid data passes without errors
4. Soft warnings do not block a field from being "valid"
5. Hard errors correctly mark a field as invalid
6. Works across multiple test cases with both valid and invalid inputs

---

---

# PHASE 7 — Confidence Engine (Design Specification)

## 1. Objective

Quantify the reliability of each extracted field by combining multiple signals into a single confidence score that drives downstream decisions.

This phase answers: **"How trustworthy is this value?"**

---

## 2. Scope

**Included**
- Multi-factor confidence computation
- Per-field confidence breakdown
- Normalization of scores
- Confidence categorization
- Proportional handling of soft vs hard validation results

**Excluded**
- Decision (auto-save vs review)
- Data correction
- UI

---

## 3. Position in System Flow

```
Validated Fields (with severity)
 + OCR Signals (from Phase 2)
 + Extraction Metadata (from Phase 4)
 → Confidence Engine
 → Field Confidence Scores
 → Next: Decision Engine (Phase 8)
```

---

## 4. Inputs

For each field:
- OCR word confidences (from Phase 2)
- Extraction method used (from Phase 4)
- Cleaned value (from Phase 5)
- Validation result with severity (from Phase 6)
- Field metadata (type, required, priority)

---

## 5. Confidence Components

### 5.1 OCR Confidence
Average confidence of words used for extraction.
- Reflects text recognition quality
- Range: 0.0–1.0

### 5.2 Validation Confidence (Improved — Non-Binary)

Derived from validation result using severity:

| Condition | Validation Confidence |
|---|---|
| No errors, no warnings | 1.0 |
| Warnings only (soft) | 0.5 |
| Hard error | 0.0 |
| Multiple hard errors | 0.0 |

**This replaces the previous binary (1.0 or 0.0) approach**, which caused a cliff effect where a field with one minor warning collapsed to zero validation confidence, unfairly tanking the final score.

### 5.3 Pattern / Structure Confidence

Measures how well value fits expected structure beyond regex:
- Correct length (exact match scores higher)
- Expected character distribution
- Known patterns (e.g., phone starts with 9 is more common than 6)

Range: 0.0–1.0

### 5.4 Extraction Method Weight (Additive, Not Multiplicative)

Different strategies have different base reliability. This is included as a **weighted additive factor**, not a multiplier applied to the final score.

| Method | Weight Contribution |
|---|---|
| anchor | 1.0 |
| zone/bbox | 0.85 |
| line-based | 0.75 |
| fallback/none | 0.5 |

**Why additive, not multiplicative?**
A multiplier approach penalizes good extractions from less reliable methods disproportionately. For example, a line-based extraction of a perfect phone number (all other scores = 1.0) with a 0.75 multiplier gives 0.75 — but the value may be completely correct. As a weighted additive factor, the method contributes proportionally alongside other components.

---

## 6. Final Confidence Formula

```
raw_confidence = (w_ocr × ocr_conf) + (w_val × val_conf) + (w_pat × pat_conf) + (w_method × method_weight)

Weights must sum to 1.0:
w_ocr + w_val + w_pat + w_method = 1.0
```

**Default weights (configurable):**
```json
{
  "weights": {
    "ocr": 0.40,
    "validation": 0.30,
    "pattern": 0.20,
    "method": 0.10
  }
}
```

**Example:**
- OCR confidence: 0.91 × 0.40 = 0.364
- Validation confidence: 1.0 × 0.30 = 0.300
- Pattern confidence: 0.95 × 0.20 = 0.190
- Method weight (anchor=1.0) × 0.10 = 0.100
- Final: 0.954

---

## 7. Output Contract

```json
{
  "field": "phone",
  "value": "9806513210",
  "confidence": {
    "ocr": 0.91,
    "validation": 1.0,
    "pattern": 0.95,
    "method": 1.0,
    "method_name": "anchor",
    "final": 0.954
  },
  "status": "high_confidence"
}
```

With soft warning:
```json
{
  "field": "full_name",
  "confidence": {
    "ocr": 0.87,
    "validation": 0.5,
    "pattern": 0.80,
    "method": 0.85,
    "method_name": "zone",
    "final": 0.744
  },
  "status": "medium_confidence"
}
```

---

## 8. Confidence Categories

| Range | Category | Status |
|---|---|---|
| ≥ 0.85 | high | accepted |
| 0.60–0.85 | medium | review_candidate |
| < 0.60 | low | needs_review |

Thresholds are configurable:
```json
{
  "thresholds": {
    "high": 0.85,
    "medium": 0.60
  }
}
```

---

## 9. Design Decisions

**Decision 1 — Multi-Factor Scoring**
Avoid reliance on OCR alone. OCR confidence alone doesn't account for extraction quality or validation failures.

**Decision 2 — Decomposed Output**
Store all components, not just final score. Required for debugging and future ML improvement.

**Decision 3 — Non-Binary Validation Contribution**
Soft warnings contribute 0.5 (partial confidence reduction) rather than 0.0. This prevents the confidence cliff.

**Decision 4 — Method as Additive Factor (Not Multiplier)**
Extraction method contributes proportionally alongside other factors rather than scaling the final score. This prevents over-penalizing correct extractions from less reliable methods.

**Decision 5 — Configurable Weights**
Allow tuning without code changes. Different form types may need different weight distributions.

---

## 10. Must / Should / Good-to-Have

**Must Have**
- OCR-based confidence
- Non-binary validation contribution (error vs warning)
- Pattern confidence
- Method as weighted additive factor
- Final confidence calculation
- Category assignment
- Structured output with all components

**Should Have**
- Configurable weights per form type
- Configurable thresholds
- Field priority modifier (critical fields get stricter categories)

**Good to Have (Later)**
- Historical correction-based confidence adjustment
- ML-based scoring
- Adaptive thresholds per form type

---

## 11. Non-Functional Requirements

| Property | Requirement |
|---|---|
| Performance | < 10 ms per form |
| Determinism | Same input → same score |

---

## 12. Acceptance Criteria

1. Confidence computed for all fields
2. All components visible in output
3. Soft warning produces 0.5 validation confidence (not 0.0)
4. Method factor is additive, not multiplicative
5. High-confidence fields are consistently reliable in testing
6. Low-confidence fields are correctly flagged

---

---

# PHASE 8 — Decision Engine (Design Specification)

## 1. Objective

Determine the final processing outcome of each form and its fields by deciding:
- What can be auto-accepted and saved
- What must be sent for human review

This phase converts confidence signals into actionable system decisions and defines what happens after corrections are submitted.

---

## 2. Scope

**Included**
- Decision rules based on confidence
- Field-level and form-level decisions
- Routing to "processed" vs "needs_review"
- Prioritization using field importance
- Re-evaluation path after human correction

**Excluded**
- UI for review
- Data correction
- Analytics

---

## 3. Position in System Flow

```
Field Confidence Scores (from Phase 7)
 → Decision Engine
 → Final Status (processed / needs_review)
 → Storage / Review Queue

(Post-correction path)
Human Correction (from Phase 11)
 → Re-evaluation Trigger
 → Confidence Recompute (Phase 7)
 → Decision Engine (re-run)
 → Updated Form Status
```

---

## 4. Core Principle

Decisions must be rule-based, transparent, and conservative for critical data. Re-evaluation after correction is a first-class concern.

---

## 5. Inputs

For each field:
- Final confidence score (from Phase 7)
- Confidence category (high / medium / low)
- Validation result and severity
- Field priority (critical / important / optional)
- `is_corrected` flag (has a human corrected this field?)

---

## 6. Field Priority Definition

```json
{
  "name": "phone",
  "priority": "critical"
}
```

| Level | Meaning |
|---|---|
| critical | Must be correct; failure blocks auto-processing |
| important | Should be correct; failure is a review candidate |
| optional | Nice to have; failure does not block processing |

---

## 7. Field-Level Decision Rules

| Confidence Category | Priority | Field Status |
|---|---|---|
| high (≥ 0.85) | any | accepted |
| medium (0.60–0.85) | critical | needs_review |
| medium (0.60–0.85) | important | review_candidate |
| medium (0.60–0.85) | optional | accepted |
| low (< 0.60) | critical | needs_review |
| low (< 0.60) | important | needs_review |
| low (< 0.60) | optional | review_candidate |
| is_corrected = true | any | accepted (override) |

---

## 8. Form-Level Decision Logic

**Rule 1 — Critical Field Failure**
```
if any critical field has status = needs_review
 → form_status = needs_review
```

**Rule 2 — Multiple Medium Fields**
```
if count(review_candidate fields) > max_review_fields (configurable)
 → form_status = needs_review
```

**Rule 3 — All Critical Fields Accepted**
```
if all critical fields have status = accepted
 AND count(needs_review fields) = 0
 → form_status = processed
```

**Rule 4 — Optional Field Tolerance**
```
Optional fields can fail without blocking processing.
```

**Rule 5 — Post-Correction Override**
```
if field.is_corrected = true
 → field_status = accepted (regardless of confidence)
After all corrections applied:
 re-evaluate form_status using rules 1–4
```

---

## 9. Re-Evaluation After Correction (CRITICAL — New)

This is a first-class concern, not an optional future feature.

**Trigger**
When a human submits corrections via Phase 11 and the API (`PUT /forms/{id}/correct`):
1. Mark corrected fields as `is_corrected = true`
2. Update `final_value` with corrected value
3. Recompute confidence for corrected fields:
   - OCR confidence: unchanged (reflects original OCR)
   - Validation confidence: re-run validation on corrected value
   - Pattern confidence: re-compute on corrected value
   - Method: unchanged
4. Re-run decision engine for the entire form
5. Update `form_status` based on new field statuses

**Why this matters**
Without re-evaluation, a form with 2 corrected fields might stay as `needs_review` even after all issues are resolved. The form status must reflect the current state, not the original state.

---

## 10. Decision Output Contract

```json
{
  "form_id": "uuid",
  "form_status": "processed",
  "thresholds_used": {
    "high": 0.85,
    "medium": 0.60,
    "max_review_fields": 2
  },
  "fields": [
    {
      "name": "phone",
      "status": "accepted",
      "confidence_final": 0.93,
      "priority": "critical",
      "is_corrected": false
    },
    {
      "name": "address",
      "status": "review_candidate",
      "confidence_final": 0.72,
      "priority": "optional",
      "is_corrected": false
    }
  ],
  "summary": {
    "total_fields": 5,
    "accepted": 4,
    "review_candidate": 1,
    "needs_review": 0,
    "corrected": 0
  },
  "decision_reason": "all_critical_fields_accepted"
}
```

---

## 11. Routing Logic

**Processed Forms**
- Saved directly to database as final
- Available via GET /forms/{id}

**Needs Review**
- Sent to exception queue (Phase 11)
- Flagged for manual correction
- Re-evaluated after correction

---

## 12. Design Decisions

**Decision 1 — Conservative for Critical Fields**
Even one critical field failure → review. No exceptions.

**Decision 2 — Re-Evaluation After Correction is Mandatory**
Form status must update after human correction. This must be implemented at MVP, not deferred.

**Decision 3 — is_corrected Override**
Once a human corrects a field, that field is accepted regardless of confidence score. Human judgment overrides machine confidence.

**Decision 4 — Configurable Thresholds**
All thresholds come from config. No hardcoded logic.

---

## 13. Must / Should / Good-to-Have

**Must Have**
- Field-level decision with priority awareness
- Form-level aggregation
- Re-evaluation path after correction
- `is_corrected` override
- Routing (processed vs review)
- Decision reason stored

**Should Have**
- Configurable thresholds
- Review count limits (`max_review_fields`)
- Summary metrics per form

**Good to Have (Later)**
- Dynamic thresholds based on historical correction rates
- Per-user tolerance levels
- Adaptive decision rules

---

## 14. Acceptance Criteria

1. Critical field failures trigger form review
2. High-confidence forms auto-process correctly
3. Medium/low fields are routed properly per priority
4. After correction, form status re-evaluates correctly
5. `is_corrected` fields are always accepted
6. Decisions are explainable (reason stored)
7. Configurable thresholds work without code changes

---

---

# PHASE 9 — Storage & Data Model (Design Specification)

## 1. Objective

Persist all outputs of the pipeline in a structured, traceable, and queryable format to support:
- Final data storage
- Review workflows
- Debugging and audits
- Future improvements

---

## 2. Scope

**Included**
- Database schema design
- Storage of forms, fields, OCR data, logs
- Idempotency strategy
- Versioning and traceability
- Index strategy

**Excluded**
- UI/dashboard
- Analytics computation
- External integrations

---

## 3. Core Principle

Store everything necessary to reconstruct, debug, and improve the system. Never store only final values.

---

## 4. Data Entities (Core Tables)

### 4.1 Forms Table

```json
{
  "id": "uuid",
  "file_hash": "sha256_string",
  "form_type": "form_v1",
  "template_version": 1,
  "image_path": "string",
  "processed_image_path": "string",
  "status": "processed | needs_review | rejected",
  "overall_confidence": 0.91,
  "decision_reason": "string",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### 4.2 Form Fields Table

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "field_name": "phone",
  "field_type": "text",
  "priority": "critical",
  "original_value": "98O65I321O",
  "cleaned_value": "9806513210",
  "final_value": "9806513210",
  "confidence_final": 0.93,
  "status": "accepted | review_candidate | needs_review",
  "extraction_method": "anchor",
  "strategies_attempted": ["anchor"],
  "is_corrected": false,
  "corrected_value": null,
  "corrected_by": null,
  "corrected_at": null,
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### 4.3 OCR Data Table

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "raw_ocr": "json_blob",
  "processed_words": "json_blob",
  "word_count": 142,
  "average_confidence": 0.91,
  "api_attempts": 1,
  "created_at": "timestamp"
}
```

### 4.4 Processing Trace Table

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "stage": "ocr | preprocess | extraction | ...",
  "status": "success | failed | skipped",
  "duration_ms": 1200,
  "metadata": "json_blob",
  "created_at": "timestamp"
}
```

**IMPORTANT — Relational Trace Records**
Each pipeline stage gets its own row in this table (not a JSON array in one row). This enables efficient queries like:
```sql
SELECT AVG(duration_ms) FROM processing_trace WHERE stage = 'ocr';
SELECT COUNT(*) FROM processing_trace WHERE stage = 'validation' AND status = 'failed';
```

### 4.5 Validation Logs Table

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "field_name": "phone",
  "valid": true,
  "errors": "json_array",
  "warnings": "json_array",
  "created_at": "timestamp"
}
```

### 4.6 Confidence Logs Table

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "field_name": "phone",
  "ocr_conf": 0.91,
  "validation_conf": 1.0,
  "pattern_conf": 0.95,
  "method_conf": 1.0,
  "method_name": "anchor",
  "final_conf": 0.954,
  "status": "high_confidence",
  "created_at": "timestamp"
}
```

### 4.7 Audit Log Table (Corrections)

```json
{
  "id": "uuid",
  "form_id": "uuid",
  "field_name": "phone",
  "before_value": "123",
  "after_value": "9876543210",
  "corrected_by": "reviewer_user_id",
  "corrected_at": "timestamp",
  "reason": "string (optional)"
}
```

---

## 5. Relationships

```
Forms (1)
 → Form Fields (many)
 → OCR Data (1)
 → Processing Trace (many — one row per stage)
 → Validation Logs (many — one per field)
 → Confidence Logs (many — one per field)
 → Audit Logs (many — one per correction event)
```

---

## 6. Index Strategy (CRITICAL)

Without indexes, queries degrade severely at scale. Define indexes from the start:

| Table | Index Columns | Purpose |
|---|---|---|
| forms | `status` | Fetch all needs_review forms |
| forms | `file_hash` | Idempotency check |
| forms | `form_type, template_version` | Filter by form type |
| form_fields | `form_id` | Fetch all fields for a form |
| form_fields | `field_name, status` | Filter by field across forms |
| processing_trace | `form_id` | Trace per form |
| processing_trace | `stage, status` | Analytics per stage |
| validation_logs | `form_id` | Validation results per form |
| confidence_logs | `form_id` | Confidence breakdown per form |
| audit_logs | `form_id` | Correction history per form |

---

## 7. Idempotency Strategy

**Problem**
Same image uploaded multiple times.

**Solution**
- Generate SHA-256 file hash at upload
- Store hash in Forms table
- Before processing, check if hash already exists

```
if hash exists in forms table:
 → return existing form_id and result (no reprocessing)
else:
 → process and store with hash
```

---

## 8. Versioning

Each form must store `form_type + template_version`.

**Template Immutability Rule**
Once a template version is published, it must never be modified. Changes to a form layout require creating a new template version. This ensures:
- Old forms remain queryable and reprocessable under their original template
- New forms use updated template
- No silent migration bugs

---

## 9. Must / Should / Good-to-Have

**Must Have**
- All 7 tables defined above
- File hash idempotency
- Relational trace (one row per stage, not JSON array)
- Index strategy implemented from day one
- Template version stored per form

**Should Have**
- `updated_at` on all mutable tables
- Soft deletes (`deleted_at`)
- JSON validation on blob fields

**Good to Have (Later)**
- Archival strategy for old forms
- Partitioning by `created_at` for large datasets
- Read replicas for analytics

---

## 10. Acceptance Criteria

1. All pipeline outputs are stored
2. Relationships correctly maintained with foreign keys
3. Any form can be fully reconstructed from DB
4. Raw OCR is retrievable without re-calling API
5. Processing trace can be queried per stage for analytics
6. Idempotency prevents duplicate records on re-upload
7. Indexes are present and queries are performant on test dataset

---

---

# PHASE 10 — API Layer (Design Specification)

## 1. Objective

Expose the backend pipeline through clear, stable, and minimal APIs that allow:
- Form submission
- Processing orchestration
- Result retrieval
- Review operations
- Post-correction re-evaluation trigger

---

## 2. Scope

**Included**
- REST API design (FastAPI)
- Request/response contracts
- Processing orchestration
- Error handling
- Idempotent request handling
- Pagination for list endpoints

**Excluded**
- UI/frontend
- Authentication (basic or added later)
- Rate limiting (later phase)

---

## 3. API Design Overview

### 3.1 POST /process-form

**Purpose:** Upload and process a form.

**Input**
- `file` (image, multipart)
- `form_type` (string, required)
- `user_id` (string, optional)

**Flow (internal)**
1. Validate file (type, size)
2. Generate SHA-256 hash (idempotency)
3. Check if already processed → return existing if found
4. Run full pipeline: preprocess → OCR → line reconstruction → extraction → checkbox detection → cleaning → validation → confidence → decision
5. Store all results
6. Return response

**Response (200)**
```json
{
  "form_id": "uuid",
  "status": "processed | needs_review | rejected",
  "fields": [...],
  "overall_confidence": 0.91,
  "processing_time_ms": 3200
}
```

**Response (409 — already processed)**
```json
{
  "form_id": "existing_uuid",
  "status": "already_processed",
  "message": "This image was previously uploaded. Returning existing result."
}
```

---

### 3.2 GET /forms/{id}

**Purpose:** Retrieve full processed form data.

**Response**
```json
{
  "form_id": "uuid",
  "status": "processed",
  "form_type": "form_v1",
  "template_version": 1,
  "fields": [...],
  "overall_confidence": 0.91,
  "logs": {
    "trace": [...],
    "validation": [...],
    "confidence": [...]
  },
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

---

### 3.3 GET /forms/review

**Purpose:** Fetch forms requiring manual review.

**Query Parameters**
- `status` (filter: needs_review | review_candidate)
- `priority` (filter: high | medium | low)
- `limit` (integer, default 20, max 100)
- `cursor` (string — cursor-based pagination token)

**Pagination**
This endpoint uses cursor-based pagination, not offset-based, because:
- Review queues can grow large
- Offset pagination degrades with large datasets
- Cursor ensures stable pagination even as new forms are added

**Response**
```json
{
  "forms": [
    {
      "form_id": "uuid",
      "status": "needs_review",
      "priority": "high",
      "created_at": "timestamp"
    }
  ],
  "next_cursor": "base64_cursor_string",
  "has_more": true
}
```

---

### 3.4 PATCH /forms/{id}/correct

**Purpose:** Submit corrected field values.

**Method:** `PATCH` (not PUT — this is a partial update)

**Input**
```json
{
  "fields": [
    {
      "name": "phone",
      "corrected_value": "9876543210"
    }
  ],
  "corrected_by": "reviewer_user_id"
}
```

**Flow**
1. Validate corrected values (basic format check)
2. Update `final_value` and set `is_corrected = true` for each corrected field
3. Write to audit log
4. Recompute confidence for corrected fields (Phases 6 + 7 re-run)
5. Re-run decision engine for form
6. Update form status

**Response**
```json
{
  "status": "updated",
  "form_id": "uuid",
  "form_status": "processed",
  "updated_fields": ["phone"],
  "re_evaluated": true
}
```

---

### 3.5 GET /health

**Purpose:** System health check.

**Response**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "timestamp"
}
```

---

## 4. Error Handling

**Standard Error Response**
```json
{
  "status": "error",
  "code": "invalid_input",
  "message": "Image not readable",
  "request_id": "uuid"
}
```

**Common Error Codes**
| Code | HTTP Status | Meaning |
|---|---|---|
| `invalid_input` | 400 | Bad file or missing param |
| `unsupported_format` | 400 | Not jpg/png |
| `file_too_large` | 413 | Exceeds size limit |
| `processing_failed` | 500 | Internal pipeline error |
| `no_text_detected` | 422 | OCR returned nothing |
| `low_quality_image` | 422 | Rejected by Phase 1 |
| `not_found` | 404 | Form ID does not exist |
| `already_processed` | 409 | Idempotency hit |

---

## 5. Response Consistency Rules

- Always include `status`
- Always include `form_id` where applicable
- Always include `request_id` for tracing
- Never return partial schema
- Never expose internal stack traces

---

## 6. Design Decisions

**Decision 1 — PATCH not PUT for corrections**
Corrections are partial updates. PATCH is semantically correct.

**Decision 2 — Cursor-Based Pagination**
Review queue can be large. Cursor pagination is stable and performant at scale.

**Decision 3 — Re-evaluation Triggered by PATCH**
Correction submission automatically triggers confidence recompute and decision re-run. This is mandatory, not optional.

**Decision 4 — Synchronous Flow (MVP)**
Avoid queue complexity initially. Acceptable for < 5 sec per form.

---

## 7. Acceptance Criteria

1. Form can be uploaded and processed via POST
2. Result retrievable via GET
3. Review queue paginated correctly
4. Corrections submitted via PATCH trigger re-evaluation
5. Errors handled cleanly with standard format
6. Duplicate uploads return 409 with existing form_id

---

---

# PHASE 11 — Review System (Exception Handling & Human Correction)

## 1. Objective

Provide a focused, efficient correction workflow for forms that cannot be confidently auto-processed, ensuring:
- Minimal human effort
- Fast resolution
- Full traceability

---

## 2. Core Principle

Humans should only see what the system is uncertain about, not the entire form.

---

## 3. Exception Queue

**Queue Criteria**
A form enters review if:
- Any critical field ≠ accepted
- Count of review_candidate fields > max_review_fields threshold
- Validation hard failures present

**Queue Data Structure**
```json
{
  "form_id": "uuid",
  "priority": "high | medium | low",
  "issues": [
    {
      "field": "phone",
      "reason": "invalid_format",
      "confidence": 0.42
    }
  ],
  "assigned_to": null,
  "created_at": "timestamp"
}
```

**Priority Rules**
| Priority | Condition |
|---|---|
| high | Critical field failure |
| medium | Multiple review_candidate fields |
| low | Optional field issues only |

---

## 4. Review Unit (Field-Level Focus)

**Principle:** Reviewer sees ONLY problematic fields, not the entire form.

**Data Provided per Flagged Field**
```json
{
  "field": "phone",
  "value": "123",
  "confidence": 0.42,
  "errors": [{"code": "invalid_format", "severity": "error"}],
  "image_snippet": {
    "path": "snippets/form_uuid_phone.jpg",
    "margin_applied_px": 30
  }
}
```

---

## 5. Image Snippet Strategy

**Purpose:** Help reviewer verify quickly without needing to scroll the full form.

**Crop Rules**
- Extend the field's bounding box by a fixed margin on all sides
- Margin: max(20% of field bbox dimension, 30px) on each side
- This ensures the reviewer sees enough context to understand the field's position on the form

**Example**
```
Field bbox: x=100, y=200, w=150, h=25
Margin: max(20% of 150=30, 30px) = 30px
Snippet crop: x=70, y=170, w=210, h=85
```

This margin definition is explicit and implementable. "Some context" is not.

---

## 6. Correction Workflow

**Steps**
1. Reviewer opens review queue (sorted by priority)
2. Sees only flagged fields for the assigned form
3. Views image snippet alongside extracted value and error
4. Edits incorrect values in input fields
5. Submits correction
6. System triggers re-evaluation (Phase 8) and updates form status

**Correction Rules (MVP)**
- Only flagged fields are editable
- All corrections are logged in audit table

---

## 7. Correction Data Model

```json
{
  "form_id": "uuid",
  "field": "phone",
  "original_value": "123",
  "corrected_value": "9876543210",
  "corrected_by": "reviewer_user_id",
  "corrected_at": "timestamp"
}
```

---

## 8. Post-Correction Behavior

```
Reviewer submits correction
 → Update field.final_value
 → Set field.is_corrected = true
 → Write audit log entry
 → Trigger confidence recompute (Phases 6 + 7)
 → Re-run decision engine (Phase 8)
 → Update form.status
 → Remove from review queue if form_status = processed
```

---

## 9. Audit Trail (Mandatory)

Every correction must be traceable:

```json
{
  "form_id": "uuid",
  "field": "phone",
  "before": "123",
  "after": "9876543210",
  "user": "reviewer_id",
  "timestamp": "...",
  "reason": "OCR misread 9 as 1 at position 0"
}
```

No silent overwrites. Every change creates an audit record.

---

## 10. Must / Should / Good-to-Have

**Must Have**
- Exception queue with priority
- Field-level review (not full form)
- Image snippets with defined margin
- Correction submission
- Audit logging
- Post-correction re-evaluation trigger

**Should Have**
- Priority-based queue ordering
- Error message shown alongside field
- Clear distinction of hard errors vs warnings

**Good to Have (Later)**
- Keyboard shortcuts for fast review
- Batch correction
- Reviewer performance tracking
- Assignment / locking (prevent two reviewers editing same form)

---

## 11. Acceptance Criteria

1. Review queue contains correct forms at right priority
2. Reviewer sees only flagged fields
3. Image snippets show field with adequate margin context
4. Corrections update data correctly
5. Audit logs are stored for every correction
6. Form status updates after correction via re-evaluation
7. Processed forms are removed from review queue

---

---

# PHASE 12 — Observability, Logging & Debugging Layer

## 1. Objective

Provide full visibility into the system's behavior so that every form can be:
- Traced end-to-end
- Debugged quickly
- Analyzed for failures
- Improved over time

---

## 2. Core Principle

If something fails, you must be able to answer why in under 60 seconds using only stored logs.

---

## 3. Logging Architecture

**Levels**

| Level | Purpose |
|---|---|
| request-level | Track entire API call |
| stage-level | Track each pipeline phase |
| field-level | Track per-field processing |

**Structured Logging Format (JSON only)**
All logs must be JSON. Never plain text.

```json
{
  "request_id": "uuid",
  "form_id": "uuid",
  "stage": "ocr",
  "status": "success",
  "duration_ms": 1200,
  "timestamp": "iso8601",
  "metadata": {}
}
```

---

## 4. Request-Level Logging

Track per API request:
- `request_id` (generated at entry point, propagated to all downstream stages)
- Timestamp
- Endpoint called
- Input metadata (file size, form_type)
- Total processing time
- Final status
- Form ID assigned

---

## 5. Stage-Level Logging

For each pipeline phase:

| Stage | Log Keys |
|---|---|
| preprocess | blur_score, brightness, rotation_angle, scale_factor, enhancement_applied |
| ocr | word_count, avg_confidence, api_attempts, duration_ms |
| line_reconstruction | line_count, avg_words_per_line, threshold_used |
| extraction | fields_extracted, fields_failed, methods_used |
| checkbox_detection | fields_detected, confidence_avg |
| cleaning | fields_modified, changes_count |
| validation | fields_valid, fields_invalid, error_codes |
| confidence | avg_confidence, high_count, medium_count, low_count |
| decision | form_status, decision_reason |
| storage | tables_written, duration_ms |

---

## 6. Field-Level Logging

For each field:
- Extraction method used
- Raw value
- Cleaned value
- Validation result + errors + warnings
- Confidence breakdown (all components)
- Final decision status

---

## 7. Correlation ID Propagation (CRITICAL)

The `request_id` must propagate across ALL processing stages including any future async boundaries.

**Current (synchronous):** Pass `request_id` as function parameter through entire pipeline call chain.

**Future (async/queue):** When queue-based processing is introduced, the `request_id` must be serialized into the job payload and deserialized by workers. It must survive the queue boundary.

Design for this now:
```json
{
  "job_id": "uuid",
  "request_id": "original_request_uuid",
  "form_id": "uuid",
  "created_at": "timestamp"
}
```

If `request_id` is not propagated through async boundaries, logs become untraceble.

---

## 8. End-to-End Trace Model

Each form must have a complete trace:

```json
{
  "form_id": "uuid",
  "request_id": "uuid",
  "trace": [
    {"stage": "preprocess", "status": "success", "duration_ms": 230},
    {"stage": "ocr", "status": "success", "duration_ms": 1400},
    {"stage": "line_reconstruction", "status": "success", "duration_ms": 45},
    {"stage": "extraction", "status": "success", "duration_ms": 180},
    {"stage": "checkbox_detection", "status": "success", "duration_ms": 60},
    {"stage": "cleaning", "status": "success", "duration_ms": 12},
    {"stage": "validation", "status": "partial_failure", "duration_ms": 8},
    {"stage": "confidence", "status": "success", "duration_ms": 5},
    {"stage": "decision", "status": "needs_review", "duration_ms": 2},
    {"stage": "storage", "status": "success", "duration_ms": 35}
  ]
}
```

---

## 9. Error Tracking

**Error Classification**
| Code | Meaning |
|---|---|
| `input_error` | Bad file, format issue |
| `processing_error` | Internal pipeline failure |
| `ocr_failure` | OCR API failure |
| `validation_failure` | Field validation failed |
| `system_error` | Unexpected exception |

**Error Log**
```json
{
  "request_id": "uuid",
  "form_id": "uuid",
  "stage": "ocr",
  "error_code": "ocr_failure",
  "message": "API returned empty response after 3 attempts",
  "timestamp": "iso8601"
}
```

---

## 10. Debugging Support

For any `form_id`, must be able to retrieve:
- Original image path
- Processed image path
- Raw OCR output
- All extracted field values + methods
- Validation logs per field
- Confidence breakdown per field
- Decision result and reason
- Correction history (if corrected)
- Complete pipeline trace with durations

This must be a single API call: `GET /forms/{id}` with `?include=full_debug`.

---

## 11. Must / Should / Good-to-Have

**Must Have**
- Structured JSON logging
- request_id propagation (correlation)
- Stage-level logs with duration
- Field-level logs
- Complete trace per form
- Error logging with classification

**Should Have**
- Performance metrics per stage
- Error rate tracking
- Query logs by form_id

**Good to Have (Later)**
- Centralized logging (ELK stack)
- Real-time dashboards
- Alerting on failure spikes
- Log archival policy

---

## 12. Acceptance Criteria

1. Every form has a complete trace
2. Errors logged with code + stage + message
3. Logs queryable by form_id
4. Stage durations available for all phases
5. Debugging a failed form requires no pipeline re-run
6. `request_id` present in all log entries for a given form

---

---

# PHASE 13 — Configuration & Extensibility (Design Specification)

## 1. Objective

Enable the system to be flexible, tunable, and extensible without code changes by externalizing:
- Templates
- Rules
- Thresholds
- Strategies

---

## 2. Core Principle

No critical logic should be hardcoded. Everything must be configurable. Configuration must be validated at startup — not discovered at runtime.

---

## 3. Configuration Categories

### 3.1 System Configuration
```json
{
  "preprocessing": {
    "blur_threshold": 100,
    "brightness_range": [50, 200],
    "resize_width": 1200,
    "deskew": {
      "min_angle_deg": -15,
      "max_angle_deg": 15,
      "reject_if_outside_range": true
    }
  },
  "ocr": {
    "retry": {
      "max_attempts": 3,
      "backoff_factor": 2,
      "initial_wait_sec": 1
    }
  },
  "line_reconstruction": {
    "y_threshold_px": 12
  },
  "confidence": {
    "weights": {
      "ocr": 0.40,
      "validation": 0.30,
      "pattern": 0.20,
      "method": 0.10
    },
    "thresholds": {
      "high": 0.85,
      "medium": 0.60
    }
  },
  "decision": {
    "max_review_fields": 2
  }
}
```

### 3.2 Template Configuration
```json
{
  "form_type": "form_v1",
  "version": 1,
  "layout": "single_column",
  "fields": [
    {
      "name": "full_name",
      "type": "text",
      "priority": "critical",
      "required": true,
      "strategies": {
        "anchor": {
          "labels": ["Name", "Full Name"],
          "direction": "right",
          "max_distance_ratio": 0.21
        },
        "zone": {
          "bbox_ratio": [0.1, 0.2, 0.4, 0.05],
          "expand_ratio": 0.15
        },
        "line": {
          "contains": ["Name"]
        }
      },
      "validation": {
        "required": true,
        "regex": "^[A-Za-z ]{2,}$"
      }
    },
    {
      "name": "gender",
      "type": "radio",
      "priority": "important",
      "options": ["Male", "Female", "Other"],
      "zones": [
        {"label": "Male", "bbox_ratio": [0.1, 0.45, 0.03, 0.025]},
        {"label": "Female", "bbox_ratio": [0.2, 0.45, 0.03, 0.025]}
      ],
      "detection": {
        "min_fill_ratio": 0.12,
        "checked_fill_ratio": 0.15
      }
    }
  ]
}
```

### 3.3 Validation Rules Configuration
```json
{
  "phone": {
    "regex": "^[6-9]\\d{9}$",
    "length": {"exact": 10},
    "severity_overrides": {
      "length_mismatch": "error",
      "invalid_format": "error"
    }
  }
}
```

### 3.4 Cleaning Rules Configuration
```json
{
  "cleaning": {
    "numeric_corrections": {
      "O": "0",
      "I": "1",
      "l": "1"
    },
    "apply_s_to_5": false
  }
}
```

---

## 4. Startup Configuration Validation (MANDATORY — Hard Requirement)

At application startup, before accepting any requests:
1. Load all config files
2. Validate schema (required fields, type correctness, value ranges)
3. Validate all template files
4. If any config is invalid → fail fast with clear error message

**This is a hard requirement, not a should-have.**

Silent config errors (e.g., a missing required field name, wrong regex syntax) are debugging nightmares in production. Catching them at startup prevents hours of unexplained failures.

```
App start
 → Load system config
 → Load all templates
 → Validate all schemas
 → If any errors → log + exit with non-zero code
 → Log active config summary
 → Accept requests
```

---

## 5. Template Versioning and Immutability

**Rule: Templates are immutable once published.**

When a form layout changes:
- Create a new template version (`form_v1` → version 2)
- Keep old version unchanged
- Old forms processed under version 1 remain reprocessable under version 1

This prevents breaking changes to historical data.

```
templates/
  form_v1/
    v1.json  (locked — do not edit)
    v2.json  (new version for updated layout)
```

---

## 6. Extensibility Points

**Adding New Fields**
- Update template (add field definition)
- No code change required
- Restart service to reload config

**Adding New Form Type**
- Create new template file
- Register in form_type registry
- No code change required

**Adjusting Thresholds**
- Modify system config
- Restart service (MVP)

**Adding New Extraction Strategy (Future)**
- Plug into extraction engine with strategy interface
- Enable via config flag

---

## 7. Must / Should / Good-to-Have

**Must Have**
- External config files (JSON)
- Template system with versioning
- Startup validation (hard requirement)
- Validation rules in config
- Confidence thresholds configurable
- Cleaning rules in config

**Should Have**
- Environment-based configs (dev / staging / prod)
- Centralized config loader module
- Active config logged at startup

**Good to Have (Later)**
- Admin UI for config management
- Hot reload without restart
- Config diff viewer (compare versions)

---

## 8. Acceptance Criteria

1. No critical logic is hardcoded
2. Templates can be updated independently of code
3. Thresholds changed via config with restart
4. Invalid config fails fast at startup with clear error
5. Old template versions remain accessible
6. System adapts to new form types without code change

---

---

# PHASE 14 — Performance, Scaling & Future Readiness

## 1. Objective

Ensure the system can handle increasing load, maintain responsiveness, and evolve without architectural rewrites.

---

## 2. Performance Targets (MVP Baseline)

| Metric | Target |
|---|---|
| Single form total | < 5 sec |
| Preprocessing (Phase 1) | < 500 ms |
| OCR (Phase 2) | ~1–2 sec (external API) |
| Extraction + Logic (Phases 3–8) | < 500 ms |
| Storage (Phase 9) | < 100 ms |
| API response total | < 6 sec |

---

## 3. Bottleneck Identification

**Primary (highest impact)**
- OCR API latency (~1–2 sec, external dependency)
- Image preprocessing (CPU-bound, OpenCV operations)
- Large file uploads (network bound)

**Secondary**
- Database writes (mitigated by index strategy)
- Logging overhead (mitigated by async logging)

---

## 4. Optimization Strategy

### 4.1 Image Optimization
- Enforce max file size at API layer (before pipeline starts)
- Resize early (Phase 1) to reduce memory usage for all downstream phases
- Avoid storing unprocessed large images in memory longer than necessary

### 4.2 OCR Optimization (Critical — Cost + Speed)
- Idempotency via file hash (Phase 9) prevents duplicate OCR calls
- Store raw OCR for reuse — if reprocessing is needed (e.g., template update), re-run extraction from stored OCR, not from API
- This is both a cost saving and a performance optimization

### 4.3 Parallel Execution within a Form

These operations are parallelizable within a single form (safe because they are independent):
- Field extraction (Phase 4) — each field is independent
- Validation (Phase 6) — each field is independent
- Confidence computation (Phase 7) — each field is independent
- Checkbox detection (Phase 4.5) — each field is independent

Implement using thread pool or async tasks per field batch.

### 4.4 Caching

| Cache Target | Key | Scope |
|---|---|---|
| OCR results | SHA-256 file hash | Permanent (stored in DB) |
| Processed images | SHA-256 file hash | Permanent (stored on disk) |
| Config/templates | In-memory at startup | Refreshed on restart |

**Important:** OCR and image caches are **exact-match only** (hash-based). A form uploaded with minor visual differences (different scan, adjusted brightness) will NOT hit the cache and will re-process. This is correct and expected behavior.

---

## 5. Concurrency Model

**MVP (Current)**
- Synchronous per-request processing
- One request → one pipeline execution
- Acceptable for low-to-medium volume

**Future (When Needed)**
```
API Layer
 → Job Queue (Redis / RabbitMQ)
 → Worker Pool
 → Process pipeline
 → Store result
 → Notify via webhook or polling
```

Design the API to be stateless now so this transition requires no API contract changes.

---

## 6. Horizontal Scaling Strategy

**Stateless API Design**
- No session state in API instances
- All state in shared database and storage
- Any instance can handle any request

**Scaling Path**
1. Start: single API instance
2. Scale: add API instances behind load balancer
3. Add: shared database (already designed as shared)
4. Add: shared file storage (S3 or equivalent)
5. Add: worker pool for async (when needed)

---

## 7. Batch Processing Design (Future)

**Use Case:** Bulk upload (multiple forms at once)

**Flow**
```
Upload batch (ZIP or multiple files)
 → Split into individual form jobs
 → Enqueue each job
 → Process asynchronously
 → Aggregate results
 → Return batch summary
```

Design for this flow now. Do not implement until needed.

---

## 8. Must / Should / Good-to-Have

**Must Have**
- Idempotency (no duplicate OCR calls)
- Efficient preprocessing (resize early)
- OCR result reuse from storage
- Stateless API design
- File size limit enforcement

**Should Have**
- Parallel field extraction/validation within a form
- Performance logging per stage
- In-memory config caching

**Good to Have (Later)**
- Async queue system
- Distributed worker pool
- Load balancing
- Auto-scaling policies

---

## 9. Acceptance Criteria

1. System handles multiple concurrent requests reliably
2. No duplicate OCR calls on re-upload (hash check works)
3. Performance meets defined targets on test dataset
4. API is stateless (verified by running multiple instances)
5. Bottlenecks documented with measured data

---

---

# PHASE 15 — Security, Reliability & Production Readiness

## 1. Objective

Harden the system for real-world usage by ensuring:
- Data security
- Controlled access
- Fault tolerance
- Safe failure handling
- Production-grade stability

---

## 2. Core Principle

Assume inputs are untrusted and failures are inevitable. Design defensively.

---

## 3. Input Security

### 3.1 File Validation
- Allow only image types: `jpg`, `jpeg`, `png`
- Restrict file size: ≤ 10 MB (configurable)
- Verify file signature (magic bytes), not just extension
  - JPEG: `FF D8 FF`
  - PNG: `89 50 4E 47`
- Reject files where extension and signature do not match

### 3.2 Content Sanitization
- Reject corrupted images (unreadable by image library)
- Prevent malformed JSON payloads (framework-level validation)

### 3.3 Request Validation
- Validate required parameters at entry point
- Reject incomplete requests immediately (before pipeline starts)
- Return clear 400 error with field-level validation failures

---

## 4. Access Control

### MVP (Minimum)
- API key authentication for all endpoints
- Key passed as header: `X-API-Key: {key}`
- Reject requests without valid key: 401

### Reviewer Access
- Reviewers can: read review queue, read flagged form fields, submit corrections
- Reviewers cannot: read non-assigned forms, modify non-flagged fields, access raw OCR data
- This must be enforced at the API layer even if role system is simple at MVP

### Future
- JWT-based authentication
- Role-based access control (admin / reviewer / reader)
- Per-role endpoint permissions

---

## 5. Data Protection

### In Transit
- Enforce HTTPS for all API calls
- No HTTP fallback

### At Rest
- Store images in restricted-access path (not publicly accessible)
- Processed images separate from uploads directory
- Database credentials in environment variables, never in config files

### Sensitive Data
- Do not log raw field values in plain text (log field names and status, not values)
- Exception: validation errors may include value for debugging (mark as sensitive in log schema)

---

## 6. Error Handling Strategy

**Rule: Never expose internal errors to clients.**

**Client Response (always)**
```json
{
  "status": "error",
  "code": "processing_failed",
  "message": "Unable to process form. Please try again.",
  "request_id": "uuid"
}
```

**Internal Log (full detail)**
```json
{
  "request_id": "uuid",
  "error": "ValueError: image array is None",
  "stack_trace": "...",
  "stage": "preprocess",
  "form_id": "uuid"
}
```

Stack traces go to internal logs only. Never in API responses.

---

## 7. Fault Tolerance

### 7.1 Retry Strategy
- OCR API: exponential backoff, max 3 attempts (defined in Phase 2)
- Database writes: retry once on transient failure
- Image processing: no retry (deterministic — if it fails twice it's the image)

### 7.2 Graceful Degradation
```
If OCR fails after all retries:
 → Return error status, do not crash
 → Log failure with form_id and reason

If one field extraction fails:
 → Mark field as failed, continue with other fields
 → Do not abort entire form processing

If storage fails:
 → Log critical error
 → Return processing result to caller anyway
 → Alert (future: dead letter queue for retry)
```

### 7.3 Timeout Handling
- Set maximum processing timeout per request (e.g., 15 sec)
- If exceeded: return 504 with `request_id`
- Never leave a request hanging indefinitely

---

## 8. Idempotency (Reliability)

- Hash-based deduplication (Phase 9)
- All PATCH requests are idempotent (applying same correction twice produces same result)
- All GET requests are inherently idempotent

---

## 9. Resource Protection

- Enforce file size limit at API layer (before reading file into memory)
- Set worker memory limits
- Limit concurrent processing (connection pool limits)

---

## 10. Logging Security

- Do not log API keys
- Do not log full file contents
- Do not log sensitive field values in default log level
- Restrict log file access to service user only

---

## 11. Must / Should / Good-to-Have

**Must Have**
- File validation (type, size, signature)
- HTTPS enforcement
- Safe error responses (no stack traces to client)
- Retry mechanism (Phase 2 OCR)
- Idempotency
- Basic API key authentication
- Reviewer access restrictions (read/correct only own assigned forms)

**Should Have**
- Request timeout enforcement
- Sensitive data masking in logs
- Secure image storage path
- Request validation at entry point

**Good to Have (Later)**
- Encryption at rest
- JWT + RBAC
- Audit access logs for data compliance
- Intrusion detection
- Vulnerability scanning in CI

---

## 12. Acceptance Criteria

1. Invalid file types rejected with 400 before pipeline starts
2. Files exceeding size limit rejected with 413
3. Magic byte validation catches misnamed files
4. System does not crash on malformed input
5. Stack traces never appear in API responses
6. Duplicate uploads return existing result, not reprocess
7. OCR failures handle gracefully with retry
8. All API calls require valid API key
9. Reviewer cannot access forms outside their scope

---

---

# CROSS-CUTTING CONCERNS

---

## CC-1: Form Type Detection

### Problem
The pipeline assumes `form_type` is passed explicitly by the caller. What if it is missing or incorrect?

### Decision
Form type must be a required parameter on `POST /process-form`.

**If missing:** Return 400 `missing_required_param`.

**If unknown:** Return 400 `unknown_form_type`.

**Future:** Auto-detection via template matching (compare OCR output against known anchor patterns) can be added as a Phase 4 fallback. This is out of scope for MVP but should be designed as an optional pre-extraction step.

---

## CC-2: Template Versioning & Migration Protocol

### Rules

1. **Templates are immutable once published.** Editing a published template is forbidden.
2. **New layout → new version.** Increment version number.
3. **Forms store their template version.** Reprocessing a form uses its original template version.
4. **Migration is explicit, not automatic.** If old forms must be reprocessed under a new template, this is a batch operation initiated deliberately, not triggered by a template update.

### Version Registry
```json
{
  "form_v1": {
    "latest": 2,
    "versions": [1, 2],
    "deprecated": []
  }
}
```

---

## CC-3: Golden Dataset & Testing Strategy

### What is a Golden Dataset?
A set of sample form images with known correct field values. Used to verify each phase produces expected output.

### Requirements
- Minimum: 10 sample forms per form type
- Covers: high quality, low quality, slight skew, landscape scan, missing fields, checkbox forms
- Each sample has a corresponding expected output JSON
- Stored in version control alongside templates

### Regression Testing
Each phase has acceptance criteria. These must be validated against the golden dataset:
- Phase 1: All samples preprocess without crash; poor quality ones rejected correctly
- Phase 2: OCR word count and confidence within expected range
- Phase 3: Lines match manually verified line groupings
- Phase 4: Field extraction matches expected values within tolerance
- Phase 5: Cleaned values match expected cleaned output
- Phase 6: Validation results match expected pass/fail
- Phase 7: Confidence scores within ±0.05 of expected
- Phase 8: Decision routing matches expected outcome

### Continuous Regression
After any code or config change, run the golden dataset through the pipeline and compare outputs. Any deviation is a regression.

---

## CC-4: System Flow Summary (All Phases)

```
Upload (API — Phase 10)
 ↓
File Validation + Idempotency Check (Phase 15 + 9)
 ↓
Preprocessing (Phase 1)
 ↓
OCR (Phase 2)
 ↓
Line Reconstruction (Phase 3)
 ↓
Extraction Engine (Phase 4)
 ↓
Checkbox Detection (Phase 4.5)
 ↓
Cleaning (Phase 5)
 ↓
Validation (Phase 6)
 ↓
Confidence Engine (Phase 7)
 ↓
Decision Engine (Phase 8)
 ↓
Storage (Phase 9)
 ↓
[if needs_review] → Review Queue (Phase 11)
       ↓
   Human Correction
       ↓
   Re-evaluation (Phase 6 → 7 → 8)
       ↓
   Storage Update (Phase 9)
 ↓
Response (Phase 10)

All Phases → Observability (Phase 12)
All Phases → Config Layer (Phase 13)
```

---

*End of OCR Form Processing Pipeline — Complete Design Specification v2.0*