import cv2
import numpy as np
from PIL import Image as PILImage
import easyocr
import logging

logging.basicConfig(level=logging.DEBUG)

img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

# CLAHE
lab = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
cl = clahe.apply(l)
limg = cv2.merge((cl, a, b))
enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

# Process non tabular
reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(enhanced, paragraph=False)

print(f"Total OCR results: {len(results)}")

data = []
for (bbox, text, prob) in results:
    center_y = (bbox[0][1] + bbox[2][1]) / 2
    center_x = (bbox[0][0] + bbox[2][0]) / 2
    # Filter
    if prob > 0.3 and len(text.strip()) > 1:
        data.append({
            "text": text.strip(), 
            "y": center_y, 
            "x": center_x,
            "conf": prob
        })

print(f"Filtered data: {len(data)}")
for d in data:
    print(f"  y={d['y']:.0f} x={d['x']:.0f} c={d['conf']:.2f} {d['text']}")

# Sort
data.sort(key=lambda d: (d["y"], d["x"]))
print("\nAfter sort:")
for d in data[:5]:
    print(f"  y={d['y']:.0f} x={d['x']:.0f} {d['text'][:30]}")

# Group lines
threshold = 20
lines = []
current_line = [data[0]]

for item in data[1:]:
    if abs(item["y"] - current_line[-1]["y"]) < threshold:
        current_line.append(item)
    else:
        current_line.sort(key=lambda d: d["x"])
        lines.append(current_line)
        current_line = [item]

if current_line:
    current_line.sort(key=lambda d: d["x"])
    lines.append(current_line)

print(f"\nTotal lines: {len(lines)}")
for i, line in enumerate(lines):
    line_text = " ".join([d["text"] for d in line])
    print(f"  Line {i}: {line_text[:50]}")