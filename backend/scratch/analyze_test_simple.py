import sys, os, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.ocr_engine import OCREngine

img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-images", "test_form.png")
img = cv2.imread(img_path)
if img is None:
    print("Image not found")
    sys.exit()

h, w = img.shape[:2]
ocr = OCREngine(api_key="invalid")
with open(img_path, "rb") as f:
    words = ocr.execute_ocr(f.read())

print(f"Image w: {w}, h: {h}")
for i, w_obj in enumerate(words):
    if i > 20: break
    print(w_obj["text"], w_obj["bbox"])

