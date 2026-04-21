import sys
import cv2
import numpy as np
from PIL import Image as PILImage
import easyocr
import logging
logging.basicConfig(level=logging.DEBUG)

# Load image
pil_img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
open_cv_image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
print(f"Original shape: {open_cv_image.shape}")

# Enhance
lab = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
cl = clahe.apply(l)
limg = cv2.merge((cl, a, b))
enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
sharpened = cv2.filter2D(enhanced, -1, kernel)
print(f"Enhanced shape: {sharpened.shape}")

# Deskew (skip - may mess up)

# Test OCR on enhanced
reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(sharpened, paragraph=False)
print(f"Results count: {len(results)}")
for (bbox, text, prob) in results[:5]:
    print(f"  {text[:30]} conf={prob:.2f}")