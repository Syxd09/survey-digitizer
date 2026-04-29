import cv2
import numpy as np
from services.document_processor import get_document_processor
from services.validator import get_validator
import logging

logging.basicConfig(level=logging.INFO)

def create_mock_table_image():
    # Create a 800x1200 white image
    img = np.ones((1200, 800, 3), dtype=np.uint8) * 255
    
    # Draw a black table
    cv2.rectangle(img, (100, 200), (700, 1000), (0, 0, 0), 2)
    for y in range(300, 1000, 100):
        cv2.line(img, (100, y), (700, y), (0, 0, 0), 2)
    for x in range(200, 700, 100):
        cv2.line(img, (x, 200), (x, 1000), (0, 0, 0), 2)
        
    return img

def test_perspective_deskew():
    print("\n--- Testing Arbitrary Perspective Deskew ---")
    processor = get_document_processor()
    img = create_mock_table_image()
    
    # Warp it randomly
    h, w = img.shape[:2]
    src_pts = np.float32([[0,0], [w,0], [0,h], [w,h]])
    dst_pts = np.float32([[50,50], [w-100,20], [20,h-50], [w-50,h-100]]) # Random 3D tilt
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img, M, (w, h), borderValue=(255,255,255))
    
    # Process it
    deskewed, diag = processor._fine_deskew(warped)
    
    if diag["fine_deskew_applied"]:
        print("✅ 4-Point Perspective Warp Deskew Applied.")
    else:
        print("❌ Deskew Failed to Apply.")

def test_180_orientation():
    print("\n--- Testing 180-Degree Upside Down Detection ---")
    processor = get_document_processor()
    img = create_mock_table_image()
    
    # Rotate 180
    img_180 = cv2.rotate(img, cv2.ROTATE_180)
    
    # Process orientation
    rotated, diag = processor._correct_orientation(img_180)
    
    if diag.get("rotation_degrees", 0) == 180:
        print("✅ Upside Down Image Corrected by 180 degrees.")
    else:
        print("❌ Upside Down Detection Failed (Note: expected if OCR heuristic didn't trigger perfectly on blank table).")

def test_median_blur_noise():
    print("\n--- Testing Median Blur Noise Reduction ---")
    processor = get_document_processor()
    img = create_mock_table_image()
    
    # Add salt and pepper noise
    noise = np.random.randint(0, 2, img.shape, dtype=np.uint8) * 255
    noisy_img = cv2.bitwise_or(img, noise)
    
    enhanced, diag = processor._conditional_enhance(noisy_img)
    if diag.get("median_blur_applied"):
        print("✅ Median Blur Noise Reduction Applied.")
    else:
        print("❌ Noise Reduction Failed.")

def test_llm_recovery():
    print("\n--- Testing Zero-Shot LLM Semantic Recovery ---")
    validator = get_validator()
    
    # Highly mangled string that would normally fail fuzzy matching (< 70 ratio)
    mangled_string = "5trong1yy D!s4gR3e"
    allowed_values = ["Strongly Agree", "Agree", "Neutral", "Disagree", "Strongly Disagree"]
    
    # We simulate this field being validated
    result = validator.validate_field(
        "q1", mangled_string, {"type": "text", "allowed_values": allowed_values}
    )
    
    if result["status"] == "OK" and result["cleaned"] == "Strongly Disagree":
        print(f"✅ LLM successfully recovered mangled string '{mangled_string}' -> 'Strongly Disagree'")
    else:
        print(f"❌ Recovery Failed. Result: {result['cleaned']}")

if __name__ == "__main__":
    test_perspective_deskew()
    test_180_orientation()
    test_median_blur_noise()
    test_llm_recovery()
