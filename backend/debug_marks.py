"""Debug mark detection on a single image."""
import cv2
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from services.survey_extractor import SurveyExtractor

img_path = os.path.join(os.path.dirname(__file__), "test-images", "1.jpeg")
img = cv2.imread(img_path)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

ext = SurveyExtractor()

# Run grid detection
h_lines, v_lines = ext._detect_grid_lines(gray)
print(f"H-lines ({len(h_lines)}): {h_lines}")
print(f"V-lines ({len(v_lines)}): {v_lines}")
print(f"Image: {img.shape}")

# Build cell grid
h, w = gray.shape
cells, n_rows, n_cols = ext._build_cell_grid(h_lines, v_lines, w, h)
print(f"\nGrid: {n_rows} rows x {n_cols} cols")

# Show cell dimensions
print("\nCell layout:")
for r in range(n_rows):
    row_info = []
    for c in range(n_cols):
        cell = cells.get((r, c))
        if cell:
            row_info.append(f"[{cell.width:3d}x{cell.height:3d}]")
        else:
            row_info.append("[  ---  ]")
    print(f"  Row {r}: {' '.join(row_info)}")

# OCR each header cell
print("\nHeaders (Row 0):")
for c in range(n_cols):
    cell = cells.get((0, c))
    if cell:
        crop = img[cell.y1:cell.y2, cell.x1:cell.x2]
        text = ext._ocr_cell(crop)
        print(f"  Col {c} ({cell.width}x{cell.height}): '{text.strip()}'")

# OCR Row 1 to see if it's a second header row
if n_rows > 1:
    print("\nRow 1:")
    for c in range(n_cols):
        cell = cells.get((1, c))
        if cell:
            crop = img[cell.y1:cell.y2, cell.x1:cell.x2]
            text = ext._ocr_cell(crop)
            print(f"  Col {c} ({cell.width}x{cell.height}): '{text.strip()}'")

# Now debug mark detection on a data row
print("\n\nMark detection scores per cell:")
for r in range(min(n_rows, 6)):
    scores = []
    for c in range(n_cols):
        cell = cells.get((r, c))
        if cell:
            cell_crop = gray[cell.y1:cell.y2, cell.x1:cell.x2]
            score = ext._detect_mark(cell_crop, "checkmark")
            scores.append(f"C{c}={score:.3f}")
            if r == 2:
                cv2.imwrite(f"debug_r{r}_c{c}.png", cell_crop)
        else:
            scores.append(f"C{c}=-.---")
    print(f"  Row {r}: {' | '.join(scores)}")

