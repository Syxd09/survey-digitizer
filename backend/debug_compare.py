import sys
sys.path.insert(0, 'E:/webProgramming/survey-digitizer/backend')

from services.processor import SurveyProcessor
from PIL import Image as PILImage
import logging
logging.basicConfig(level=logging.DEBUG, format='%(message)s')

# Load image exactly the same way as the test script
img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')

# Check what happens in process
import cv2
import numpy as np
open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
print("Input shape:", open_cv_image.shape, "dtype:", open_cv_image.dtype)

# Enhancement
lab = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
cl = clahe.apply(l)
limg = cv2.merge((cl, a, b))
enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

print("Enhanced shape:", enhanced.shape, "dtype:", enhanced.dtype)
print("Enhanced min/max:", enhanced.min(), enhanced.max())

# Try OCR on ENHANCED
import easyocr
temp_reader = easyocr.Reader(['en'], gpu=False)
results = temp_reader.readtext(enhanced, paragraph=False)
print(f"Results on enhanced: {len(results)}")
for r in results[:10]:
    print(f"  {r[1]} (conf={r[2]:.2f})")