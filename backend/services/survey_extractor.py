"""
Hydra v12.5 — Survey Form Extractor
=====================================
Form-agnostic survey digitization engine.

Architecture:
1. OpenCV grid detection → find table cells
2. Dynamic column header identification via OCR
3. Per-cell mark detection (checkmarks ✓ or circled numbers)
4. Question text extraction per row
5. Structured JSON output

Supports any survey layout — not hardcoded to specific forms.
"""

import cv2
import numpy as np
import logging
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, asdict

from services.llm_semantic_refiner import get_semantic_refiner

logger = logging.getLogger(__name__)
# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Cell:
    """A single table cell."""
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self): return self.x2 - self.x1
    @property
    def height(self): return self.y2 - self.y1
    @property
    def area(self): return self.width * self.height
    @property
    def cx(self): return (self.x1 + self.x2) // 2
    @property
    def cy(self): return (self.y1 + self.y2) // 2


@dataclass
class SurveyQuestion:
    """A single extracted question with its selected answer."""
    number: int
    text: str
    selected_column: Optional[str] = None
    selected_index: Optional[int] = None
    confidence: float = 0.0
    mark_type: str = ""  # "checkmark", "circle", "none"


@dataclass
class SurveyResult:
    """Complete survey extraction result."""
    form_metadata: Dict = field(default_factory=dict)
    columns: List[str] = field(default_factory=list)
    questions: List[SurveyQuestion] = field(default_factory=list)
    form_type: str = "unknown"  # "checkmark", "likert", "unknown"
    header_text: str = ""
    instructions: str = ""

    def to_dict(self):
        return {
            "form_metadata": self.form_metadata,
            "columns": self.columns,
            "questions": [asdict(q) for q in self.questions],
            "form_type": self.form_type,
            "header_text": self.header_text,
            "instructions": self.instructions,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Survey Extractor
# ═══════════════════════════════════════════════════════════════════════════

class SurveyExtractor:
    """
    Form-agnostic survey extraction engine.
    Dynamically detects table structure, column headers, and response marks.
    """

    def __init__(self, ocr_engines: Dict = None):
        """
        Args:
            ocr_engines: dict with 'easyocr' and/or 'tesseract' reader instances
        """
        self.ocr_engines = ocr_engines or {}
        self._easyocr_reader = None
        self._tesseract_available = False
        self._init_ocr()

    def _init_ocr(self):
        """Initialize OCR engines for text extraction."""
        # EasyOCR
        if "easyocr" in self.ocr_engines:
            self._easyocr_reader = self.ocr_engines["easyocr"]
        else:
            try:
                import easyocr
                self._easyocr_reader = easyocr.Reader(["en"], gpu=True)
            except Exception as e:
                logger.warning(f"[SURVEY] EasyOCR init failed: {e}")

        # Tesseract
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
        except Exception:
            self._tesseract_available = False

    # ─── Main Entry Point ─────────────────────────────────────────────────

    def extract(self, image: np.ndarray) -> SurveyResult:
        """
        Extract survey data from an image.

        Args:
            image: BGR OpenCV image

        Returns:
            SurveyResult with structured question/answer data
        """
        logger.info("[SURVEY] Starting form-agnostic extraction...")
        result = SurveyResult()

        # 1. Preprocess
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]

        # 2. Detect table grid
        h_lines, v_lines = self._detect_grid_lines(gray)
        logger.info(f"[SURVEY] Detected {len(h_lines)} horizontal, {len(v_lines)} vertical lines")

        if len(h_lines) < 3 or len(v_lines) < 2:
            logger.warning("[SURVEY] Insufficient grid lines — falling back to text-only")
            return self._fallback_text_extraction(image, result)

        # 3. Build cell grid from line intersections
        cells, n_rows, n_cols = self._build_cell_grid(h_lines, v_lines, w, h)
        logger.info(f"[SURVEY] Grid: {n_rows} rows × {n_cols} cols = {len(cells)} cells")

        if n_rows < 2 or n_cols < 2:
            return self._fallback_text_extraction(image, result)

        # 4. Identify column headers (first data row)
        col_headers = self._extract_column_headers(image, cells, n_cols)
        result.columns = col_headers
        logger.info(f"[SURVEY] Detected columns: {col_headers}")

        # 5. Determine form type
        result.form_type = self._classify_form_type(col_headers)
        logger.info(f"[SURVEY] Form type: {result.form_type}")

        # 6. Determine which columns are "question" vs "response"
        question_cols, response_cols = self._identify_column_roles(
            cells, n_rows, n_cols, col_headers, image
        )
        logger.info(f"[SURVEY] Question cols: {question_cols}, Response cols: {response_cols}")

        # 7. Extract header/metadata from above the table
        result.form_metadata = self._extract_metadata(image, cells)
        result.header_text = result.form_metadata.get("title", "")

        # 8. Extract questions and detect marks
        for row_idx in range(1, n_rows):  # Skip header row
            q = self._extract_question_row(
                image, gray, cells, row_idx, n_cols,
                question_cols, response_cols, col_headers, result.form_type
            )
            if q and q.text.strip():
                result.questions.append(q)

        # 9. Apply LLM Semantic Refinement for ultimate accuracy
        if result.questions:
            try:
                refiner = get_semantic_refiner()
                raw_texts = [q.text for q in result.questions]
                refined_texts = refiner.refine_questions(
                    raw_header=result.header_text,
                    form_type=result.form_type,
                    questions=raw_texts
                )
                
                # Update question objects with refined text
                for idx, new_text in enumerate(refined_texts):
                    if idx < len(result.questions):
                        result.questions[idx].text = new_text
            except Exception as e:
                logger.warning(f"[SURVEY] LLM Refinement skipped due to error: {e}")

        logger.info(f"[SURVEY] Extracted {len(result.questions)} questions")
        return result

    # ─── Grid Detection ───────────────────────────────────────────────────

    def _detect_grid_lines(self, gray: np.ndarray) -> Tuple[List[int], List[int]]:
        """
        Robust multi-strategy grid detection for real-world survey photos.
        Tries multiple binarization methods and kernel sizes,
        picks the combination that yields the best grid.
        """
        h, w = gray.shape

        # Build multiple binary images to try
        binaries = []

        # Strategy 1: OTSU
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binaries.append(("otsu", otsu))

        # Strategy 2: Adaptive threshold (best for faint printed lines)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 10
        )
        binaries.append(("adaptive", adaptive))

        # Strategy 3: Sharpened + OTSU (enhances faint lines)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        sharpened = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
        _, sharp_bin = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binaries.append(("sharpened", sharp_bin))

        # Try each strategy with multiple kernel sizes
        best_h_lines = []
        best_v_lines = []
        best_score = 0

        h_divs = [12, 16, 20, 25, 30]  # Kernel width = w // div
        v_divs = [12, 16, 20, 25]       # Kernel height = h // div
        h_thresh_ratios = [0.08, 0.10, 0.12]  # Min line span %
        v_thresh_ratios = [0.03, 0.05, 0.08]

        for name, binary in binaries:
            for h_div in h_divs:
                for h_thr in h_thresh_ratios:
                    kw = max(w // h_div, 15)
                    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
                    h_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
                    h_lines = self._extract_line_positions(h_mask, "horizontal", h_thr)
                    h_lines = self._deduplicate_lines(h_lines, min_gap=max(12, h // 80))

                    if len(h_lines) < 3:
                        continue

                    for v_div in v_divs:
                        for v_thr in v_thresh_ratios:
                            kh = max(h // v_div, 15)
                            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
                            v_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
                            v_lines = self._extract_line_positions(v_mask, "vertical", v_thr)
                            v_lines = self._deduplicate_lines(v_lines, min_gap=max(12, w // 40))

                            if len(v_lines) < 2:
                                continue

                            # Score: prefer more lines but penalize excessive counts (noise)
                            n_h = len(h_lines)
                            n_v = len(v_lines)
                            # Sweet spot: 5-20 h_lines, 3-8 v_lines for survey forms
                            h_score = n_h if n_h <= 25 else max(0, 50 - n_h)
                            v_score = n_v if n_v <= 10 else max(0, 20 - n_v)
                            score = h_score * 2 + v_score * 3  # V-lines more valuable

                            if score > best_score:
                                best_score = score
                                best_h_lines = h_lines
                                best_v_lines = v_lines

        logger.info(
            f"[SURVEY-GRID] Best: {len(best_h_lines)}H × {len(best_v_lines)}V "
            f"(score={best_score})"
        )
        return best_h_lines, best_v_lines

    def _extract_line_positions(
        self, mask: np.ndarray, axis: str, thresh_ratio: float = 0.10
    ) -> List[int]:
        """Extract line positions from a binary mask via projection profiling."""
        positions = []

        if axis == "horizontal":
            projection = np.sum(mask, axis=1)
            threshold = mask.shape[1] * thresh_ratio * 255
        else:
            projection = np.sum(mask, axis=0)
            threshold = mask.shape[0] * thresh_ratio * 255

        in_peak = False
        peak_start = 0

        for i, val in enumerate(projection):
            if val > threshold:
                if not in_peak:
                    peak_start = i
                    in_peak = True
            else:
                if in_peak:
                    positions.append((peak_start + i) // 2)
                    in_peak = False

        if in_peak:
            positions.append((peak_start + len(projection)) // 2)

        return sorted(positions)

    def _deduplicate_lines(self, lines: List[int], min_gap: int = 15) -> List[int]:
        """Merge lines that are too close together."""
        if not lines:
            return []
        deduped = [lines[0]]
        for line in lines[1:]:
            if line - deduped[-1] >= min_gap:
                deduped.append(line)
            else:
                deduped[-1] = (deduped[-1] + line) // 2
        return deduped

    # ─── Cell Grid Construction ───────────────────────────────────────────

    def _build_cell_grid(
        self, h_lines: List[int], v_lines: List[int], img_w: int, img_h: int
    ) -> Tuple[Dict[Tuple[int, int], Cell], int, int]:
        """Build a grid of cells from horizontal and vertical lines."""
        cells = {}
        n_rows = len(h_lines) - 1
        n_cols = len(v_lines) - 1

        for r in range(n_rows):
            for c in range(n_cols):
                cell = Cell(
                    row=r, col=c,
                    x1=v_lines[c], y1=h_lines[r],
                    x2=v_lines[c + 1], y2=h_lines[r + 1],
                )
                # Only keep cells with reasonable dimensions
                if cell.width > 10 and cell.height > 10:
                    cells[(r, c)] = cell

        return cells, n_rows, n_cols

    # ─── Column Header Detection ──────────────────────────────────────────

    def _extract_column_headers(
        self, image: np.ndarray, cells: Dict, n_cols: int
    ) -> List[str]:
        """Extract text from the first row to identify column headers."""
        headers = []

        # Try first two rows (headers can span 2 rows)
        for c in range(n_cols):
            cell = cells.get((0, c))
            if not cell:
                headers.append("")
                continue

            # Also check second row if it exists for multi-line headers
            cell2 = cells.get((1, c))

            crop = image[cell.y1:cell.y2, cell.x1:cell.x2]
            text = self._ocr_cell(crop)

            if cell2 and not text.strip():
                crop2 = image[cell2.y1:cell2.y2, cell2.x1:cell2.x2]
                text = self._ocr_cell(crop2)

            headers.append(text.strip())

        return headers

    def _classify_form_type(self, headers: List[str]) -> str:
        """Determine if this is a checkmark form, Likert scale, or unknown."""
        header_text = " ".join(headers).lower()

        # Checkmark indicators
        checkmark_signals = ["not true", "somewhat true", "certainly true",
                            "true", "false", "yes", "no", "never", "always",
                            "sometimes", "often", "rarely"]
        checkmark_score = sum(1 for s in checkmark_signals if s in header_text)

        # Likert indicators
        likert_signals = ["strongly agree", "agree", "disagree", "strongly disagree",
                         "neutral"]
        likert_score = sum(1 for s in likert_signals if s in header_text)

        # Numeric scale detection (1, 2, 3, 4, 5, 6 as headers)
        numeric_headers = [h for h in headers if re.match(r"^\d+$", h.strip())]
        if len(numeric_headers) >= 3:
            likert_score += 3

        if checkmark_score > likert_score:
            return "checkmark"
        elif likert_score > 0:
            return "likert"
        else:
            return "checkmark"  # default

    def _identify_column_roles(
        self, cells: Dict, n_rows: int, n_cols: int,
        headers: List[str], image: np.ndarray
    ) -> Tuple[List[int], List[int]]:
        """
        Determine which columns contain questions and which contain responses.
        Strategy: question columns have wide cells with lots of text;
                  response columns have narrow cells with marks.
        """
        col_widths = []
        for c in range(n_cols):
            widths = [cells[(r, c)].width for r in range(n_rows) if (r, c) in cells]
            col_widths.append(np.mean(widths) if widths else 0)

        # Typically: first 1-2 columns are S.No + Question, rest are responses
        # Heuristic: columns wider than 40% of avg are question columns
        if not col_widths:
            return [0], list(range(1, n_cols))

        avg_width = np.mean(col_widths)
        question_cols = []
        response_cols = []

        for c in range(n_cols):
            header = headers[c].lower() if c < len(headers) else ""

            # Explicit header-based detection
            is_sno = any(k in header for k in ["s.no", "sno", "s no", "sl", "sr", "#"])
            is_question = any(k in header for k in ["question", "item", "statement"])

            if is_sno or is_question:
                question_cols.append(c)
            elif col_widths[c] > avg_width * 1.5:
                question_cols.append(c)
            else:
                response_cols.append(c)

        # Fallback: if no question cols detected, assume first wide column(s)
        if not question_cols:
            # Sort by width, take the widest column(s) as question
            sorted_cols = sorted(range(n_cols), key=lambda c: col_widths[c], reverse=True)
            question_cols = [sorted_cols[0]]
            if len(sorted_cols) > 1 and col_widths[sorted_cols[1]] > avg_width:
                question_cols.append(sorted_cols[1])
            question_cols.sort()
            response_cols = [c for c in range(n_cols) if c not in question_cols]

        return question_cols, response_cols

    # ─── Per-Row Extraction ───────────────────────────────────────────────

    def _extract_question_row(
        self, image: np.ndarray, gray: np.ndarray,
        cells: Dict, row_idx: int, n_cols: int,
        question_cols: List[int], response_cols: List[int],
        col_headers: List[str], form_type: str
    ) -> Optional[SurveyQuestion]:
        """Extract question text and detect which response column is marked."""

        # Extract question text
        question_text = ""
        question_number = 0

        for c in question_cols:
            cell = cells.get((row_idx, c))
            if not cell:
                continue
            crop = image[cell.y1:cell.y2, cell.x1:cell.x2]
            text = self._ocr_cell(crop)

            # Try to extract question number
            num_match = re.match(r"^(\d+)\s*[.\)]\s*(.*)", text.strip())
            if num_match:
                question_number = int(num_match.group(1))
                text = num_match.group(2)
            elif re.match(r"^\d+$", text.strip()):
                question_number = int(text.strip())
                continue  # This is just the S.No column

            question_text += " " + text

        question_text = re.sub(r"\s+", " ", question_text).strip()

        if not question_text:
            return None

        # Collect raw mark scores for ALL response columns in this row
        raw_scores = {}
        for c in response_cols:
            cell = cells.get((row_idx, c))
            if not cell:
                raw_scores[c] = 0.0
                continue
            cell_crop = gray[cell.y1:cell.y2, cell.x1:cell.x2]
            raw_scores[c] = self._detect_mark(cell_crop, form_type)

        # Use RELATIVE scoring: find the cell that stands out from its peers
        selected_idx = None
        selected_col = None
        confidence = 0.0
        mark_type = "none"

        if raw_scores:
            scores_list = list(raw_scores.values())
            cols_list = list(raw_scores.keys())

            if len(scores_list) >= 2:
                max_score = max(scores_list)
                max_idx = scores_list.index(max_score)

                # Calculate stats without the max to find baseline
                others = [s for i, s in enumerate(scores_list) if i != max_idx]
                mean_others = np.mean(others) if others else 0.0
                std_others = np.std(others) if len(others) > 1 else 0.0

                # The marked cell must be significantly above the baseline
                gap = max_score - mean_others
                relative_ratio = max_score / (mean_others + 1e-6)

                # Decision: marked if gap is significant AND the score stands out
                if gap > 0.05 and relative_ratio > 1.5:
                    selected_idx = max_idx
                    actual_col_idx = cols_list[max_idx]
                    selected_col = (
                        col_headers[actual_col_idx]
                        if actual_col_idx < len(col_headers)
                        else f"Column {actual_col_idx + 1}"
                    )
                    # Confidence based on how clearly this cell stands out
                    if std_others > 0:
                        z_score = (max_score - mean_others) / (std_others + 1e-6)
                        confidence = min(1.0, 0.5 + z_score * 0.15)
                    else:
                        confidence = min(1.0, 0.6 + gap * 2)
                    mark_type = form_type if form_type != "unknown" else "checkmark"

            elif len(scores_list) == 1:
                # Only one response column
                if scores_list[0] > 0.15:
                    selected_idx = 0
                    actual_col_idx = cols_list[0]
                    selected_col = (
                        col_headers[actual_col_idx]
                        if actual_col_idx < len(col_headers)
                        else f"Column {actual_col_idx + 1}"
                    )
                    confidence = min(1.0, scores_list[0])
                    mark_type = form_type if form_type != "unknown" else "checkmark"

        return SurveyQuestion(
            number=question_number if question_number else row_idx,
            text=question_text,
            selected_column=selected_col,
            selected_index=selected_idx,
            confidence=round(confidence, 3),
            mark_type=mark_type,
        )

    # ─── Mark Detection ───────────────────────────────────────────────────

    def _detect_mark(self, cell_gray: np.ndarray, form_type: str) -> float:
        """
        Detect if a cell contains a handwritten mark (checkmark or circle).
        Returns a raw score — NOT normalized to 0-1 yet.

        Key insight: response cells with only printed text (like column numbers
        "1", "2", "3") have UNIFORM ink across the cell. Handwritten marks
        (✓ or circles) create CONCENTRATED ink in the cell center.

        Signals:
        1. Center-weighted ink density (marks are centered in cells)
        2. Edge density difference (marks have sharper edges than faint print)
        3. Contour compactness (marks form distinct blobs)
        """
        if cell_gray.size == 0:
            return 0.0

        h, w = cell_gray.shape

        if h < 10 or w < 10:
            return 0.0

        # Crop generously inward to avoid table borders
        mx = max(4, w // 6)
        my = max(4, h // 6)
        inner = cell_gray[my:h - my, mx:w - mx]

        if inner.size == 0:
            return 0.0

        ih, iw = inner.shape

        # If the cell is uniform (blank), return 0
        std_dev = np.std(inner)
        if std_dev < 5.0:
            return 0.0

        # Binarize using a threshold darker than the mean background
        mean_val = np.mean(inner)
        thresh_val = mean_val - max(15.0, std_dev * 0.8)
        _, binary = cv2.threshold(inner, thresh_val, 255, cv2.THRESH_BINARY_INV)
        
        total_ink = np.sum(binary > 0) / binary.size

        # If cell is almost empty, quick reject
        if total_ink < 0.01:
            return 0.0

        # 1. CENTER vs PERIPHERY ink density
        # Handwritten marks concentrate in center; printed text spans edges
        center_h = max(1, ih // 3)
        center_w = max(1, iw // 3)
        cy1, cy2 = ih // 2 - center_h // 2, ih // 2 + center_h // 2
        cx1, cx2 = iw // 2 - center_w // 2, iw // 2 + center_w // 2

        center_region = binary[cy1:cy2, cx1:cx2]
        center_ink = np.sum(center_region > 0) / (center_region.size + 1e-6)

        # Center concentration ratio
        center_ratio = center_ink / (total_ink + 1e-6)

        # 2. Edge density for strong strokes
        edges = cv2.Canny(inner, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # 3. Contour analysis — handwritten marks form 1-3 significant contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        significant = [c for c in contours if cv2.contourArea(c) > max(30, binary.size * 0.005)]

        contour_score = 0.0
        if significant:
            largest = max(significant, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            perimeter = cv2.arcLength(largest, True)
            area_ratio = area / (binary.size + 1e-6)

            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)

                # Handwritten checkmarks: 1-3 contours, moderate area, low circularity
                # Handwritten circles: 1 contour, moderate area, high circularity
                # Printed small text: many small contours, low area each

                if form_type == "likert":
                    # Boost for circular marks (circled numbers)
                    contour_score = circularity * 0.6 + (0.3 if 0.03 < area_ratio < 0.5 else 0)
                else:
                    # Boost for checkmark-like strokes
                    contour_score = 0.4 if 0.02 < area_ratio < 0.5 else 0.1
                    if len(significant) <= 3:
                        contour_score += 0.2

        # Combine signals with emphasis on CENTER concentration
        # This is the key differentiator: handwritten marks are CENTERED
        score = (
            total_ink * 2.0 +
            center_ratio * 1.5 +
            edge_density * 1.0 +
            contour_score
        )

        return score

    # ─── OCR Utilities ────────────────────────────────────────────────────

    def _ocr_cell(self, cell_image: np.ndarray) -> str:
        """OCR a single cell crop. Uses EasyOCR first, Tesseract as fallback."""
        if cell_image.size == 0:
            return ""

        h, w = cell_image.shape[:2]
        if h < 8 or w < 8:
            return ""

        # Upscale small crops for better OCR
        if h < 40 or w < 80:
            scale = max(2, 60 // h)
            cell_image = cv2.resize(cell_image, None, fx=scale, fy=scale,
                                    interpolation=cv2.INTER_CUBIC)

        # Try EasyOCR
        if self._easyocr_reader:
            try:
                results = self._easyocr_reader.readtext(cell_image, detail=1)
                texts = [r[1] for r in results if r[2] > 0.3]
                if texts:
                    return " ".join(texts)
            except Exception:
                pass

        # Fallback: Tesseract
        if self._tesseract_available:
            try:
                import pytesseract
                text = pytesseract.image_to_string(
                    cell_image, config="--psm 6 --oem 3"
                ).strip()
                return text
            except Exception:
                pass

        return ""

    # ─── Metadata Extraction ──────────────────────────────────────────────

    def _extract_metadata(self, image: np.ndarray, cells: Dict) -> Dict:
        """Extract form metadata from the area above the table."""
        if not cells:
            return {}

        # Find table top boundary
        min_y = min(c.y1 for c in cells.values())

        if min_y < 30:
            return {}

        # Crop the header area
        header_crop = image[0:min_y, :]
        header_text = self._ocr_cell(header_crop)

        metadata = {"raw_header": header_text}

        # Extract study code
        code_match = re.search(r"(?:Study\s*Code|Code)[:\s]*([A-Z0-9\-]+)", header_text, re.I)
        if code_match:
            metadata["study_code"] = code_match.group(1)

        # Extract questionnaire title
        q_match = re.search(r"(Questionnaire\s*\d+)", header_text, re.I)
        if q_match:
            metadata["title"] = q_match.group(1)

        # Extract form number
        form_match = re.search(r"Form\s*(?:No|Number)[.:\s]*(\w*)", header_text, re.I)
        if form_match:
            metadata["form_number"] = form_match.group(1)

        return metadata

    # ─── Fallback ─────────────────────────────────────────────────────────

    def _fallback_text_extraction(self, image: np.ndarray, result: SurveyResult) -> SurveyResult:
        """If grid detection fails, extract text in reading order."""
        logger.warning("[SURVEY] Using fallback text-only extraction")
        text = self._ocr_cell(image)
        result.header_text = text[:200] if text else ""
        result.form_type = "unknown"
        return result
