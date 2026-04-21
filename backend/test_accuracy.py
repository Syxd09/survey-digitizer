"""
Hydra v12.5 — Comprehensive Test Suite
========================================
Tests against:
  1. test-file.png (code screenshot - ground truth validated)
  2. Generated form image
  3. Generated invoice image
"""

import sys
import os
import json
import logging
import time
from PIL import Image, ImageDraw, ImageFont
from services.processor import SurveyProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_suite")


# ═══════════════════════════════════════════════════════════════════════════
# Ground Truth for test-file.png
# ═══════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_CODE = {
    "header_must_contain": ["PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL", "PORTS"],
    "file_context": "prg5.py",
    "entries": [
        {
            "message_fragment": '"[" was not closed',
            "rule": "Pylance",
            "location": "[Ln 14, Col 14]",
        },
        {
            "message_fragment": "Keyword arguments within subscripts are not supported",
            "rule": "Pylance",
            "location": "[Ln 14, Col 15]",
        },
        {
            "message_fragment": "Keyword arguments within subscripts are not supported",
            "rule": "Pylance",
            "location": "[Ln 14, Col 26]",
        },
        {
            "message_fragment": "sklearn.datasets",
            "rule": "Pylance(reportMissingModuleSource)",
            "location": "[Ln 4, Col 6]",
        },
        {
            "message_fragment": '"df" is not defined',
            "rule": "Pylance(reportUndefinedVariable)",
            "location": "[Ln 8, Col 13]",
        },
        {
            "message_fragment": '"df" is not defined',
            "rule": "Pylance(reportUndefinedVariable)",
            "location": "[Ln 8, Col 26]",
        },
        {
            "message_fragment": '"df" is not defined',
            "rule": "Pylance(reportUndefinedVariable)",
            "location": "[Ln 8, Col 41]",
        },
        {
            "message_fragment": '"df" is not defined',
            "rule": "Pylance(reportUndefinedVariable)",
            "location": "[Ln 14, Col 31]",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Test Image Generators
# ═══════════════════════════════════════════════════════════════════════════

def generate_form_image(path: str):
    """Generate a synthetic form image for testing."""
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font = ImageFont.load_default()
        font_bold = font

    # Title
    draw.text((250, 20), "Patient Registration Form", fill="black", font=font_bold)
    draw.line([(50, 60), (750, 60)], fill="gray", width=2)

    # Form fields
    fields = [
        ("Full Name:", "John Michael Smith"),
        ("Date of Birth:", "03/15/1987"),
        ("Phone Number:", "(555) 234-5678"),
        ("Email Address:", "john.smith@example.com"),
        ("Home Address:", "1234 Oak Street, Apt 5B"),
        ("City:", "San Francisco"),
        ("State:", "California"),
        ("Zip Code:", "94102"),
        ("Emergency Contact:", "Jane Smith (555) 987-6543"),
        ("Insurance ID:", "BC-12345678-XY"),
    ]

    y = 80
    for label, value in fields:
        draw.text((60, y), label, fill="black", font=font)
        draw.text((280, y), value, fill="darkblue", font=font)
        draw.line([(270, y + 25), (720, y + 25)], fill="lightgray", width=1)
        y += 45

    img.save(path)
    print(f"Generated form image: {path}")


def generate_invoice_image(path: str):
    """Generate a synthetic invoice image for testing."""
    img = Image.new("RGB", (800, 700), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except:
        font = ImageFont.load_default()
        font_bold = font
        font_small = font

    # Header
    draw.text((50, 20), "INVOICE", fill="black", font=font_bold)
    draw.text((550, 20), "Invoice #: INV-2024-0042", fill="black", font=font_small)
    draw.text((550, 40), "Date: 04/21/2026", fill="black", font=font_small)
    draw.text((550, 60), "Due Date: 05/21/2026", fill="black", font=font_small)
    
    draw.line([(50, 90), (750, 90)], fill="black", width=2)

    # Company info
    draw.text((50, 100), "From: Acme Corporation", fill="black", font=font)
    draw.text((50, 125), "123 Business Ave, Suite 200", fill="gray", font=font_small)
    draw.text((400, 100), "Bill To: Widget Industries", fill="black", font=font)
    draw.text((400, 125), "456 Commerce Blvd", fill="gray", font=font_small)
    
    draw.line([(50, 160), (750, 160)], fill="black", width=1)

    # Table header
    draw.text((60, 170), "Item", fill="black", font=font_bold)
    draw.text((350, 170), "Qty", fill="black", font=font_bold)
    draw.text((450, 170), "Unit Price", fill="black", font=font_bold)
    draw.text((600, 170), "Amount", fill="black", font=font_bold)
    draw.line([(50, 200), (750, 200)], fill="black", width=1)

    items = [
        ("Web Development Services", "40", "$125.00", "$5,000.00"),
        ("UI/UX Design Package", "1", "$2,500.00", "$2,500.00"),
        ("Cloud Hosting (Monthly)", "3", "$89.99", "$269.97"),
        ("SSL Certificate (Annual)", "1", "$149.00", "$149.00"),
        ("Technical Support Hours", "10", "$75.00", "$750.00"),
    ]

    y = 210
    for item, qty, price, amount in items:
        draw.text((60, y), item, fill="black", font=font)
        draw.text((365, y), qty, fill="black", font=font)
        draw.text((450, y), price, fill="black", font=font)
        draw.text((600, y), amount, fill="black", font=font)
        y += 35

    draw.line([(50, y), (750, y)], fill="black", width=1)
    y += 10
    
    draw.text((450, y), "Subtotal:", fill="black", font=font)
    draw.text((600, y), "$8,668.97", fill="black", font=font)
    y += 30
    draw.text((450, y), "Tax (8.5%):", fill="black", font=font)
    draw.text((600, y), "$736.86", fill="black", font=font)
    y += 30
    draw.text((450, y), "Total:", fill="black", font=font_bold)
    draw.text((600, y), "$9,405.83", fill="darkblue", font=font_bold)

    img.save(path)
    print(f"Generated invoice image: {path}")


def generate_simple_text_image(path: str):
    """Generate a simple text image for testing general extraction."""
    img = Image.new("RGB", (700, 300), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except:
        font = ImageFont.load_default()

    lines = [
        "The quick brown fox jumps over the lazy dog.",
        "Python 3.12 supports advanced type annotations.",
        "Machine learning requires large datasets.",
        "OpenCV processes images at 30 frames per second.",
        "Artificial Intelligence is transforming healthcare.",
    ]

    y = 30
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 45

    img.save(path)
    print(f"Generated text image: {path}")


# ═══════════════════════════════════════════════════════════════════════════
# Validation Logic
# ═══════════════════════════════════════════════════════════════════════════

def validate_code_screenshot(result: dict) -> dict:
    """Validate result against ground truth for test-file.png."""
    questions = result.get("questions", [])
    all_text = " ".join(q["selected"] for q in questions)

    report = {"total_checks": 0, "passed": 0, "failed": [], "details": []}

    # Check header keywords
    for kw in GROUND_TRUTH_CODE["header_must_contain"]:
        report["total_checks"] += 1
        if kw.upper() in all_text.upper():
            report["passed"] += 1
            report["details"].append(f"  ✅ Header keyword '{kw}' found")
        else:
            report["failed"].append(f"Header keyword '{kw}' NOT found")
            report["details"].append(f"  ❌ Header keyword '{kw}' NOT found")

    # Check file context
    report["total_checks"] += 1
    if GROUND_TRUTH_CODE["file_context"] in all_text:
        report["passed"] += 1
        report["details"].append(f"  ✅ File context '{GROUND_TRUTH_CODE['file_context']}' found")
    else:
        report["failed"].append(f"File context '{GROUND_TRUTH_CODE['file_context']}' NOT found")
        report["details"].append(f"  ❌ File context '{GROUND_TRUTH_CODE['file_context']}' NOT found")

    # Check each error entry
    for i, entry in enumerate(GROUND_TRUTH_CODE["entries"]):
        # Check message fragment
        report["total_checks"] += 1
        if entry["message_fragment"] in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Entry {i+1} message: '{entry['message_fragment'][:50]}...'")
        else:
            report["failed"].append(f"Entry {i+1} message: '{entry['message_fragment']}' NOT found")
            report["details"].append(f"  ❌ Entry {i+1} message: '{entry['message_fragment']}' NOT found")

        # Check rule
        report["total_checks"] += 1
        if entry["rule"] in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Entry {i+1} rule: '{entry['rule']}'")
        else:
            report["failed"].append(f"Entry {i+1} rule: '{entry['rule']}' NOT found")
            report["details"].append(f"  ❌ Entry {i+1} rule: '{entry['rule']}' NOT found")

        # Check location
        report["total_checks"] += 1
        if entry["location"] in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Entry {i+1} location: '{entry['location']}'")
        else:
            report["failed"].append(f"Entry {i+1} location: '{entry['location']}' NOT found")
            report["details"].append(f"  ❌ Entry {i+1} location: '{entry['location']}' NOT found")

    return report


def validate_form(result: dict) -> dict:
    """Validate form extraction."""
    questions = result.get("questions", [])
    all_text = " ".join(q["selected"] for q in questions).lower()

    expected_fields = [
        "john", "smith", "03/15/1987", "555", "234-5678",
        "john.smith@example.com", "1234 oak", "san francisco",
        "california", "94102", "bc-12345678", "insurance",
    ]

    report = {"total_checks": len(expected_fields), "passed": 0, "failed": [], "details": []}

    for field in expected_fields:
        if field.lower() in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Found: '{field}'")
        else:
            report["failed"].append(f"'{field}' NOT found")
            report["details"].append(f"  ❌ NOT found: '{field}'")

    return report


def validate_invoice(result: dict) -> dict:
    """Validate invoice extraction."""
    questions = result.get("questions", [])
    all_text = " ".join(q["selected"] for q in questions)

    expected = [
        "INVOICE", "INV-2024-0042", "04/21/2026",
        "Acme", "Widget", "Web Development",
        "$5,000", "$2,500", "$125", "$89.99",
        "Subtotal", "$8,668", "Tax", "$9,405",
    ]

    report = {"total_checks": len(expected), "passed": 0, "failed": [], "details": []}

    for field in expected:
        if field in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Found: '{field}'")
        else:
            report["failed"].append(f"'{field}' NOT found")
            report["details"].append(f"  ❌ NOT found: '{field}'")

    return report


def validate_simple_text(result: dict) -> dict:
    """Validate simple text extraction."""
    questions = result.get("questions", [])
    all_text = " ".join(q["selected"] for q in questions).lower()

    expected_phrases = [
        "quick brown fox", "lazy dog",
        "python", "type annotations",
        "machine learning", "datasets",
        "opencv", "frames per second",
        "artificial intelligence", "healthcare",
    ]

    report = {"total_checks": len(expected_phrases), "passed": 0, "failed": [], "details": []}

    for phrase in expected_phrases:
        if phrase.lower() in all_text:
            report["passed"] += 1
            report["details"].append(f"  ✅ Found: '{phrase}'")
        else:
            report["failed"].append(f"'{phrase}' NOT found")
            report["details"].append(f"  ❌ NOT found: '{phrase}'")

    return report


# ═══════════════════════════════════════════════════════════════════════════
# Main Test Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_all_tests():
    print("=" * 70)
    print("  HYDRA v12.5 — COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    # Generate test images
    generate_form_image("test_form.png")
    generate_invoice_image("test_invoice.png")
    generate_simple_text_image("test_simple.png")

    # Initialize processor once
    print("\n🔄 Loading processor...")
    t0 = time.time()
    processor = SurveyProcessor()
    print(f"   Loaded in {time.time() - t0:.1f}s\n")

    tests = [
        ("test-file.png", "CODE SCREENSHOT (VS Code Pylance)", validate_code_screenshot),
        ("test_form.png", "FORM (Patient Registration)", validate_form),
        ("test_invoice.png", "INVOICE (Business Invoice)", validate_invoice),
        ("test_simple.png", "GENERAL TEXT (Plain Sentences)", validate_simple_text),
    ]

    overall_passed = 0
    overall_total = 0

    for img_path, test_name, validator_fn in tests:
        print("─" * 70)
        print(f"📋 TEST: {test_name}")
        print(f"   File: {img_path}")
        print("─" * 70)

        if not os.path.exists(img_path):
            print(f"   ⚠️ SKIPPED — file not found\n")
            continue

        t_start = time.time()
        result = processor.process(img_path)
        elapsed = time.time() - t_start

        doc_type = result.get("diagnostics", {}).get("doc_type", {}).get("type", "unknown")
        ocr_counts = result.get("diagnostics", {}).get("ocr_counts", {})

        print(f"   ⏱️ Duration: {elapsed:.2f}s")
        print(f"   🏷️ Classified as: {doc_type}")
        print(f"   🔢 OCR counts: P={ocr_counts.get('paddle', 0)} E={ocr_counts.get('easyocr', 0)} T={ocr_counts.get('tesseract', 0)}")
        print(f"   📝 Extracted {len(result.get('questions', []))} fields\n")

        # Print extracted text
        for q in result.get("questions", []):
            val = q.get("selected", "")
            conf = q.get("confidence", 0)
            label = q.get("question", "")
            print(f"   [{conf:.2f}] {label}: {val}")

        print()

        # Validate
        report = validator_fn(result)
        for detail in report["details"]:
            print(detail)

        score = report["passed"]
        total = report["total_checks"]
        pct = (score / total * 100) if total > 0 else 0
        overall_passed += score
        overall_total += total

        print(f"\n   📊 Score: {score}/{total} ({pct:.1f}%)")
        if report["failed"]:
            print(f"   ❌ Failed checks: {len(report['failed'])}")
        else:
            print(f"   🎯 PERFECT SCORE!")
        print()

    # Overall summary
    print("=" * 70)
    print("  OVERALL RESULTS")
    print("=" * 70)
    overall_pct = (overall_passed / overall_total * 100) if overall_total > 0 else 0
    print(f"  Total: {overall_passed}/{overall_total} ({overall_pct:.1f}%)")
    
    if overall_pct >= 95:
        print("  🏆 PRODUCTION GRADE")
    elif overall_pct >= 80:
        print("  ✅ GOOD — needs minor refinement")
    elif overall_pct >= 60:
        print("  ⚠️ FAIR — significant gaps remain")
    else:
        print("  ❌ NEEDS WORK")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
