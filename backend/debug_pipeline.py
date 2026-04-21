import sys
sys.path.insert(0, 'E:/webProgramming/survey-digitizer/backend')

from PIL import Image as PILImage
import cv2
import numpy as np
import logging
import easyocr
logging.basicConfig(level=logging.INFO)

img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
print("=== Step 1: Load ===")
print("PIL size:", img.size)

# Step 1: Convert 
open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
print("=== Step 2: Converted to BGR ===")
print("Shape:", open_cv_image.shape)

# Step 3: Enhances
lab = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
cl = clahe.apply(l)
limg = cv2.merge((cl, a, b))
enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
print("=== Step 3: CLAHE ===")
print("Shape:", enhanced.shape)

# Step 4: Deskew
gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
gray = cv2.bitwise_not(gray)
thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
coords = np.column_stack(np.where(thresh > 0))
angle = cv2.minAreaRect(coords)[-1]
print(f"=== Step 4: Deskew - angle: {angle} ===")

(h, w) = enhanced.shape[:2]
center = (w // 2, h // 2)
M = cv2.getRotationMatrix2D(center, angle, 1.0)
rotated = cv2.warpAffine(enhanced, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
print("After deskew shape:", rotated.shape)

# Run OCR on deskewed
reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(rotated, paragraph=False)
print(f"=== Results after full pipeline: {len(results)} ===")
for r in results[:5]:
    print(f"  {r[1]}")