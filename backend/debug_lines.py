import sys
import logging
logging.basicConfig(level=logging.DEBUG)

import easyocr
import cv2
import numpy as np

# Load image
img = cv2.imread('E:/webProgramming/survey-digitizer/test-file.png')
print(f"Image shape: {img.shape}")

# Run easyocr directly
reader = easyocr.Reader(['en'], gpu=False)
results = reader.readtext(img, paragraph=False)

data = []
for (bbox, text, prob) in results:
    center_y = (bbox[0][1] + bbox[2][1]) / 2
    center_x = (bbox[0][0] + bbox[2][0]) / 2
    if prob > 0.3 and len(text.strip()) > 1:
        data.append({
            "text": text.strip(), 
            "y": center_y, 
            "x": center_x,
            "conf": prob
        })

print(f"Filtered data count: {len(data)}")
for d in data:
    print(f"  y={d['y']:.0f} x={d['x']:.0f} conf={d['conf']:.2f} text={d['text']}")

# Sort
data.sort(key=lambda d: (d["y"], d["x"]))
print(f"\nAfter sort:")
for d in data:
    print(f"  y={d['y']:.0f} x={d['x']:.0f}")

# Group into lines
threshold = 20
lines = []
current_line = []
current_line.append(data[0])

print(f"\nStarting line grouping, threshold={threshold}")
for item in data[1:]:
    last_y = current_line[-1]["y"]
    diff = abs(item["y"] - last_y)
    if diff < threshold:
        current_line.append(item)
        print(f"  Added to line: y={item['y']:.0f} (diff={diff:.0f})")
    else:
        current_line.sort(key=lambda d: d["x"])
        lines.append(current_line)
        print(f"  New line: y={item['y']:.0f} vs {last_y:.0f} (diff={diff:.0f}) > {threshold}")
        current_line = [item]

if current_line:
    current_line.sort(key=lambda d: d["x"])
    lines.append(current_line)

print(f"\nTotal lines: {len(lines)}")
for i, line in enumerate(lines):
    line_text = " ".join([d["text"] for d in line])
    print(f"  Line {i}: {line_text[:50]}")