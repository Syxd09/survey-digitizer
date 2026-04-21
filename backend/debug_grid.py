"""Debug grid detection on real images."""
import cv2
import numpy as np
import sys, os

img_path = os.path.join(os.path.dirname(__file__), "test-images", "1.jpeg")
img = cv2.imread(img_path)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape

print(f"Image size: {w}x{h}")
print(f"Mean brightness: {np.mean(gray):.1f}")

# Binarize
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
print(f"OTSU threshold applied. Dark pixel ratio: {np.mean(binary > 0):.3f}")

# Try different kernel sizes for horizontal lines
for div in [4, 6, 8, 12, 16, 20]:
    kw = max(w // div, 20)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    h_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=2)
    # Count horizontal line rows
    proj = np.sum(h_mask, axis=1)
    threshold = w * 0.10
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  H-lines (kernel_w={kw}, div={div}): {line_count} lines detected (threshold={threshold:.0f})")

print()

# Try different kernel sizes for vertical lines
for div in [4, 6, 8, 12, 16, 20]:
    kh = max(h // div, 20)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
    v_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=2)
    proj = np.sum(v_mask, axis=0)
    threshold = h * 0.05
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  V-lines (kernel_h={kh}, div={div}): {line_count} lines detected (threshold={threshold:.0f})")

# Also try adaptive threshold
print("\n--- Adaptive threshold ---")
adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
for div in [8, 12, 16]:
    kw = max(w // div, 20)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    h_mask = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, h_kernel, iterations=2)
    proj = np.sum(h_mask, axis=1)
    threshold = w * 0.10
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  H-lines adaptive (kernel_w={kw}, div={div}): {line_count} lines detected")

for div in [8, 12, 16]:
    kh = max(h // div, 20)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
    v_mask = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, v_kernel, iterations=2)
    proj = np.sum(v_mask, axis=0)
    threshold = h * 0.05
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  V-lines adaptive (kernel_h={kh}, div={div}): {line_count} lines detected")

# Try with more aggressive preprocessing - denoise + sharpen
print("\n--- With preprocessing ---")
denoised = cv2.GaussianBlur(gray, (3,3), 0)
sharpened = cv2.addWeighted(gray, 1.5, denoised, -0.5, 0)
_, binary2 = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

for div in [12, 16, 20, 25, 30]:
    kw = max(w // div, 20)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    h_mask = cv2.morphologyEx(binary2, cv2.MORPH_OPEN, h_kernel, iterations=1)
    proj = np.sum(h_mask, axis=1)
    threshold = w * 0.08
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  H-lines sharp (kernel_w={kw}, div={div}, iter=1): {line_count} lines detected")

for div in [12, 16, 20, 25, 30]:
    kh = max(h // div, 20)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))
    v_mask = cv2.morphologyEx(binary2, cv2.MORPH_OPEN, v_kernel, iterations=1)
    proj = np.sum(v_mask, axis=0)
    threshold = h * 0.03
    line_count = 0
    in_peak = False
    for val in proj:
        if val > threshold and not in_peak:
            in_peak = True
            line_count += 1
        elif val <= threshold:
            in_peak = False
    print(f"  V-lines sharp (kernel_h={kh}, div={div}, iter=1): {line_count} lines detected")
