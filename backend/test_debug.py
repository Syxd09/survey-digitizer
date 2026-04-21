import cv2
from PIL import Image as PILImage
import numpy as np
from services.processor import SurveyProcessor
import json

proc = SurveyProcessor()
pil_img = PILImage.open("test-file.png").convert("RGB")
img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

img_restored, diag = proc.restorer.process(img_bgr)
cv2.imwrite("test-restored.png", img_restored)

p_res = proc._run_paddle_ocr(img_restored)
e_res = proc._run_easy_ocr(img_restored)
t_res = proc._run_tesseract_ocr(img_restored)

with open("debug_ocr.json", "w") as f:
    json.dump({
        "paddle": p_res,
        "easy": e_res,
        "tesseract": t_res
    }, f, indent=2)

print(f"Paddle returned {len(p_res)} regions")
print(f"EasyOCR returned {len(e_res)} regions")
print(f"Tesseract returned {len(t_res)} regions")
