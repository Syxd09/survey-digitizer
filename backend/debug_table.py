import sys
import cv2
import numpy as np
from PIL import Image as PILImage

# Load image
img = cv2.imread('E:/webProgramming/survey-digitizer/test-file.png')
pil_img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
open_cv_image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

# Test table detection
gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

print(f"Image shape: {open_cv_image.shape}")
print(f"Total contours: {len(contours)}")

cells = []
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if 20 < w < open_cv_image.shape[1] * 0.9 and 15 < h < open_cv_image.shape[0] * 0.9 and w > 20 and h > 10:
        cells.append({'x': x, 'y': y, 'w': w, 'h': h})

print(f"Filtered cells: {len(cells)}")
for c in cells[:10]:
    print(f"  x={c['x']} y={c['y']} w={c['w']} h={c['h']}")
