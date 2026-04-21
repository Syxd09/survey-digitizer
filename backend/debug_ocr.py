import easyocr
import cv2

reader = easyocr.Reader(['en'], gpu=False)
img = cv2.imread('test-file.png')
results = reader.readtext(img, paragraph=False)

print(f"Total results: {len(results)}")
print("\nFirst 20 items:")
for i, (bbox, text, prob) in enumerate(results[:20]):
    y1 = bbox[0][1]
    y2 = bbox[2][1]
    x1 = bbox[0][0]
    x2 = bbox[2][0]
    print(f"{i}: y={(y1+y2)//2} x={(x1+x2)//2} conf={prob:.2f} text={text[:30]}")
