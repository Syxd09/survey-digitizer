"""
Test Survey Extractor against real images.
Validates table detection, column identification, and mark detection.
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))

from services.survey_extractor import SurveyExtractor
import cv2

def test_image(extractor, path, label):
    print(f"\n{'='*70}")
    print(f"  TESTING: {label} — {os.path.basename(path)}")
    print(f"{'='*70}")

    img = cv2.imread(path)
    if img is None:
        print(f"  ❌ Failed to load image: {path}")
        return None

    t0 = time.time()
    result = extractor.extract(img)
    elapsed = time.time() - t0

    print(f"  ⏱  Processing time: {elapsed:.2f}s")
    print(f"  📋 Form type: {result.form_type}")
    print(f"  📊 Columns detected: {result.columns}")
    print(f"  ❓ Questions found: {len(result.questions)}")
    print(f"  📄 Metadata: {result.form_metadata}")
    print()

    for q in result.questions:
        mark = "✓" if q.selected_column else "—"
        conf_bar = "█" * int(q.confidence * 10) + "░" * (10 - int(q.confidence * 10))
        print(f"  Q{q.number:>2}: {q.text[:60]:<60} → {str(q.selected_column or 'NONE'):>20} [{conf_bar}] {q.confidence:.2f}")

    return result


def main():
    print("=" * 70)
    print("  HYDRA SURVEY EXTRACTOR — REAL IMAGE VALIDATION")
    print("=" * 70)

    extractor = SurveyExtractor()

    test_dir = os.path.join(os.path.dirname(__file__), "test-images")
    if not os.path.isdir(test_dir):
        print(f"❌ test-images directory not found at {test_dir}")
        return

    images = sorted([
        f for f in os.listdir(test_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    if not images:
        print("❌ No images found in test-images/")
        return

    results = {}
    for img_file in images:
        img_path = os.path.join(test_dir, img_file)
        result = test_image(extractor, img_path, img_file)
        if result:
            results[img_file] = result.to_dict()

    # Save results
    out_dir = os.path.join(os.path.dirname(__file__), "test-results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "survey_extraction_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    total_q = sum(len(r.get("questions", [])) for r in results.values())
    total_answered = sum(
        1 for r in results.values()
        for q in r.get("questions", [])
        if q.get("selected_column")
    )
    print(f"  Images processed: {len(results)}")
    print(f"  Total questions: {total_q}")
    print(f"  Questions with answers: {total_answered}")
    print(f"  Results saved to: {out_path}")


if __name__ == "__main__":
    main()
