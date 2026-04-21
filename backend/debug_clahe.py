import cv2
import numpy as np
from PIL import Image as PILImage
import easyocr

img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

print("Original image ready")

# Apply CLAHE (same as _enhance_image)
lab = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
cl = clahe.apply(l)
limg = cv2.merge((cl, a, b))
enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

print("After CLAHE")

# Try OCR
reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(enhanced, paragraph=False)
print(f"Results: {len(results)}")
for r in results[:10]:
    print(f"  {r[1]} (conf={r[2]:.2f})")