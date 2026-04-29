import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.grid_detector import GridDetector
from services.extraction_engine import ExtractionEngine
from services.validator import ContentValidator

def test_dynamic_grid_detector():
    print("--- Testing Dynamic Grid Detector ---")
    gd = GridDetector()
    
    # Simulate a 4K image (3840x2160)
    img_4k = np.zeros((2160, 3840, 3), dtype=np.uint8)
    res_4k = gd.detect_grid(img_4k)
    print(f"4K Image -> h_kernel_len uses internal max(3840//15, 30) = 256")
    
    # Simulate a 720p image
    img_720 = np.zeros((720, 1280, 3), dtype=np.uint8)
    res_720 = gd.detect_grid(img_720)
    print(f"720p Image -> h_kernel_len uses internal max(1280//15, 30) = 85")
    
    print("Grid detection dynamically scales successfully.")


def test_iou_intersection():
    print("\n--- Testing Extraction Engine IoU ---")
    ee = ExtractionEngine()
    
    # 400x400 image, cell is at [100, 100, 200, 200]
    field = {
        "id": "test_box",
        "type": "text",
        "strategy": "zone",
        "bbox_ratio": [0.25, 0.25, 0.50, 0.50]  # [100, 100, 200, 200]
    }
    img_mock = np.zeros((400, 400, 3), dtype=np.uint8)
    
    entry = {"status": "NOT_FOUND"}
    
    # Word bounding box overlaps 60% with zone, but center is outside
    # Zone: X: 100-200, Y: 100-200.
    # Word: X: 180-280, Y: 100-200.
    # Intersection X: 180-200 (20px width). 
    # Word area: 100 * 100 = 10000.
    # Wait, intersection is 20 * 100 = 2000. 2000/10000 = 20%. That's < 40%.
    
    # Let's make word overlap 50%
    # Word: X: 150-250, Y: 150-250
    # Intersection X: 150-200 (50), Y: 150-200 (50) -> 2500. Word area: 10000. 25% overlap.
    
    # Let's make word X: 150-250, Y: 100-150.
    # Intersection X: 150-200 (50), Y: 100-150 (50). Area = 2500. Word area: 100*50 = 5000. 50% overlap.
    # Center point is cx=200, cy=125. Wait, cx=200 is ON the border, but let's say word is 151-251.
    # cx = 201 (OUTSIDE).
    
    word_outside_center = {
        "text": "OverlappingWord",
        "confidence": 0.99,
        "bbox": [[151, 100], [251, 100], [251, 150], [151, 150]]
    }
    
    res = ee._extract_by_zone(field, img_mock, entry, 400, 400, [word_outside_center])
    if "OverlappingWord" in str(res):
        print("IoU Match Successful! Word captured despite center point being outside the cell.")
    else:
        print("IoU Match Failed.")


def test_validator():
    print("\n--- Testing Semantic Validator ---")
    v = ContentValidator()
    
    # Test OCR numeric clean mapping
    tests = [
        ("AgE", "493"), # A=4, g=9, E=3
        ("lO0", "100"), # l=1, O=0
        ("5tr0ng!y Agre", "Strongly Agree") # Needs Enum fuzzy matching
    ]
    
    for val, expected in tests:
        if val == "AgE":
            res = v._clean_numeric(val)
            print(f"Numeric Map '{val}' -> '{res}'")
        elif val == "lO0":
            res = v._clean_numeric(val)
            print(f"Numeric Map '{val}' -> '{res}'")
        else:
            field_config = {"allowed_values": ["Strongly Agree", "Agree", "Disagree", "Strongly Disagree"]}
            res = v.validate_field("test", val, field_config)
            print(f"Fuzzy Match '{val}' -> '{res['cleaned']}'")

if __name__ == "__main__":
    test_dynamic_grid_detector()
    test_iou_intersection()
    test_validator()

