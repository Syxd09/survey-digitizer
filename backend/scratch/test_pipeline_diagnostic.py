"""
Pipeline Diagnostic Test
========================
Tests every image through the full pipeline with NO caching/idempotency,
reporting per-phase diagnostics so we can see exactly where failures occur.
Calls each service exactly as the orchestrator does.
"""

import os
import sys
import time
import base64
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.document_processor import get_document_processor
from services.ocr_engine import get_ocr_engine
from services.line_reconstructor import get_line_reconstructor
from services.grid_detector import GridDetector
from services.extraction_engine import ExtractionEngine
from services.validator import get_validator
from services.confidence_engine import get_confidence_engine
from services.decision_engine import get_decision_engine
from services.template_service import get_template_service


def run_diagnostic(img_path: str) -> dict:
    """Run the pipeline manually phase-by-phase, collecting diagnostics."""
    img_name = os.path.basename(img_path)
    result = {"image": img_name, "phases": {}, "errors": []}

    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        result["errors"].append(f"Failed to load image: {img_path}")
        return result

    h_orig, w_orig = img_bgr.shape[:2]
    result["original_size"] = f"{w_orig}x{h_orig}"

    # ── Phase 1: Preprocessing ──────────────────────────────────────────────
    t0 = time.time()
    try:
        doc_processor = get_document_processor()
        processed_img, p1_diag = doc_processor.process_document(img_bgr)
        dt = time.time() - t0

        quality = p1_diag.get("quality", {})
        orient = p1_diag.get("orientation", {})

        result["phases"]["1_preprocessing"] = {
            "status": quality.get("status"),
            "time_ms": int(dt * 1000),
            "quality": quality,
            "orientation": orient,
            "processed_size": f"{processed_img.shape[1]}x{processed_img.shape[0]}",
        }

        if quality.get("status") == "REJECT":
            result["phases"]["1_preprocessing"]["BLOCKED"] = True
            result["final_status"] = "REJECT"
            result["reject_reason"] = quality.get("rejection_reason", "Quality check failed")
            return result
    except Exception as e:
        result["errors"].append(f"Phase 1 crashed: {e}")
        import traceback; traceback.print_exc()
        return result

    quality_status = quality.get("status", "PASS")

    # ── Phase 2: OCR ────────────────────────────────────────────────────────
    t0 = time.time()
    try:
        _, img_encoded = cv2.imencode(".jpg", processed_img)
        img_bytes = img_encoded.tobytes()

        ocr_engine = get_ocr_engine()
        words = ocr_engine.execute_ocr(img_bytes)
        dt = time.time() - t0

        result["phases"]["2_ocr"] = {
            "status": "OK",
            "time_ms": int(dt * 1000),
            "word_count": len(words),
            "sample_words": [w.get("text", "") for w in words[:10]],
        }
    except Exception as e:
        result["errors"].append(f"Phase 2 crashed: {e}")
        import traceback; traceback.print_exc()
        return result

    # ── Phase 3: Line Reconstruction ────────────────────────────────────────
    t0 = time.time()
    try:
        reconstructor = get_line_reconstructor()
        lines = reconstructor.reconstruct_lines(words)
        dt = time.time() - t0

        result["phases"]["3_line_reconstruction"] = {
            "status": "OK",
            "time_ms": int(dt * 1000),
            "line_count": len(lines),
            "sample_lines": [l.get("text", "")[:80] for l in lines[:5]],
        }
    except Exception as e:
        result["errors"].append(f"Phase 3 crashed: {e}")
        return result

    # ── Phase 4: Grid Detection ─────────────────────────────────────────────
    t0 = time.time()
    try:
        grid_detector = GridDetector()
        grid_result = grid_detector.detect_grid(processed_img)
        dt = time.time() - t0

        result["phases"]["4_grid_detection"] = {
            "status": "OK" if grid_result.get("success") else "FAILED",
            "time_ms": int(dt * 1000),
            "success": grid_result.get("success", False),
            "table_bbox": grid_result.get("table_bbox"),
            "rows": len(grid_result.get("rows", [])),
            "option_columns": len(grid_result.get("option_columns", [])),
            "cells": len(grid_result.get("cells", [])),
        }
    except Exception as e:
        result["errors"].append(f"Phase 4 crashed: {e}")
        grid_result = {"success": False}
        result["phases"]["4_grid_detection"] = {"status": "CRASHED", "error": str(e)}

    # ── Phase 4 Extraction ──────────────────────────────────────────────────
    t0 = time.time()
    try:
        extraction_engine = ExtractionEngine()
        template_service = get_template_service()
        template = template_service.get_template()

        if grid_result.get("success"):
            extracted_fields = extraction_engine.extract_fields_dynamic(
                img_bgr=processed_img,
                grid_result=grid_result,
                template=template,
                lines=lines,
                all_words=words,
            )
            method = "dynamic_grid"
        else:
            extracted_fields = extraction_engine.extract_fields(
                lines, template, processed_img, all_words=words
            )
            method = "template_fallback"

        dt = time.time() - t0

        result["phases"]["4_extraction"] = {
            "status": "OK",
            "time_ms": int(dt * 1000),
            "method": method,
            "field_count": len(extracted_fields),
            "fields_summary": [],
        }
        for f in extracted_fields:
            result["phases"]["4_extraction"]["fields_summary"].append({
                "id": f.get("id"),
                "raw_value": f.get("raw_value"),
                "confidence": round(f.get("confidence", 0), 4),
                "status": f.get("status"),
            })
    except Exception as e:
        result["errors"].append(f"Phase 4 extraction crashed: {e}")
        import traceback; traceback.print_exc()
        extracted_fields = []
        result["phases"]["4_extraction"] = {"status": "CRASHED", "error": str(e)}

    # ── Phase 5/6/7: Validation & Confidence ────────────────────────────────
    # Call validator and confidence engine EXACTLY as the orchestrator does
    t0 = time.time()
    try:
        validator = get_validator()
        confidence_engine = get_confidence_engine()

        validated_fields = []
        for field in extracted_fields:
            # Phase 5 & 6: Validation (matches orchestrator._process_single_field)
            val_res = validator.validate_field(
                field_id=field["id"],
                raw_value=field.get("raw_value") or "",
                field_config=field
            )

            # Phase 7: Confidence Scoring (matches orchestrator._process_single_field)
            conf_res = confidence_engine.compute_field_confidence(
                ocr_conf=field.get("confidence", 0.5),
                quality_status=quality_status,
                validation_status=val_res["status"],
                extraction_method=field.get("strategy", "anchor"),
                pattern_match=(len(val_res["warnings"]) == 0),
                visual_diff=field.get("visual_diff")
            )

            field.update({
                "cleaned_value": val_res["cleaned"],
                "status": val_res["status"],
                "errors": val_res["errors"],
                "warnings": val_res["warnings"],
                "confidence": conf_res["score"],
                "signals": conf_res["signals"],
            })
            validated_fields.append(field)

        dt = time.time() - t0
        result["phases"]["5_6_7_validation"] = {
            "status": "OK",
            "time_ms": int(dt * 1000),
            "field_count": len(validated_fields),
            "fields_detail": [],
        }
        for f in validated_fields:
            result["phases"]["5_6_7_validation"]["fields_detail"].append({
                "id": f.get("id"),
                "raw_value": f.get("raw_value"),
                "cleaned": f.get("cleaned_value"),
                "confidence": round(f.get("confidence", 0), 4),
                "status": f.get("status"),
                "strategy": f.get("strategy"),
            })
    except Exception as e:
        result["errors"].append(f"Phase 5/6/7 crashed: {e}")
        import traceback; traceback.print_exc()
        validated_fields = []

    # ── Phase 8: Decision Engine ────────────────────────────────────────────
    try:
        decision_engine = get_decision_engine()
        decision = decision_engine.decide(validated_fields)

        result["phases"]["8_decision"] = decision
        result["final_status"] = decision.get("status")
        result["overall_confidence"] = decision.get("overall_confidence", 0)
    except Exception as e:
        result["errors"].append(f"Phase 8 crashed: {e}")
        result["final_status"] = "ERROR"

    return result


def main():
    img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-images")
    images = sorted([
        f for f in os.listdir(img_dir)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ])

    print(f"Found {len(images)} images to test.\n")

    all_results = []

    for img_name in images:
        img_path = os.path.join(img_dir, img_name)
        print(f"\n{'='*70}")
        print(f"  {img_name}")
        print(f"{'='*70}")

        t0 = time.time()
        result = run_diagnostic(img_path)
        total_ms = int((time.time() - t0) * 1000)
        result["total_ms"] = total_ms

        # Print phase-by-phase summary
        for phase_name, phase_data in result.get("phases", {}).items():
            if isinstance(phase_data, dict):
                status = phase_data.get("status", "?")
                time_ms = phase_data.get("time_ms", "?")
                icon = "✅" if status in ("OK", "PASS", "AUTO_ACCEPT") else "⚠️" if status in ("NEEDS_REVIEW", "FAILED", "FAIL") else "❌"
                extra = ""
                if "word_count" in phase_data:
                    extra = f" ({phase_data['word_count']} words)"
                elif "line_count" in phase_data:
                    extra = f" ({phase_data['line_count']} lines)"
                elif "field_count" in phase_data:
                    extra = f" ({phase_data['field_count']} fields, method={phase_data.get('method', '?')})"
                elif "rows" in phase_data and "option_columns" in phase_data:
                    extra = f" ({phase_data['rows']} rows × {phase_data['option_columns']} cols = {phase_data.get('cells', '?')} cells)"
                elif "reason" in phase_data:
                    extra = f" - {phase_data.get('reason', '')[:100]}"
                print(f"  {icon} {phase_name}: {status} ({time_ms}ms){extra}")

        # Print final decision
        final = result.get("final_status", "UNKNOWN")
        conf = result.get("overall_confidence", 0)
        icon = "✅" if final == "AUTO_ACCEPT" else "⚠️" if final == "NEEDS_REVIEW" else "❌"
        print(f"\n  {icon} FINAL: {final} (conf={conf:.4f}) [{total_ms}ms total]")

        # Print extracted fields
        field_detail = result.get("phases", {}).get("5_6_7_validation", {}).get("fields_detail", [])
        if field_detail:
            print(f"\n  {'ID':<8} {'Raw Value':<20} {'Cleaned':<20} {'Conf':>8} {'Status':<12} {'Strategy':<15}")
            print(f"  {'─'*8} {'─'*20} {'─'*20} {'─':─>8} {'─'*12} {'─'*15}")
            for f in field_detail:
                raw = str(f.get("raw_value", ""))[:18]
                cleaned = str(f.get("cleaned", ""))[:18]
                conf_val = f.get("confidence", 0)
                st = f.get("status", "?")
                strat = f.get("strategy", "?")[:13]
                print(f"  {f.get('id', '?'):<8} {raw:<20} {cleaned:<20} {conf_val:>8.4f} {st:<12} {strat:<15}")

        if result.get("errors"):
            print(f"\n  ⚠️  ERRORS:")
            for err in result["errors"]:
                print(f"    - {err}")

        all_results.append(result)

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")

    total = len(all_results)
    accepts = sum(1 for r in all_results if r.get("final_status") == "AUTO_ACCEPT")
    reviews = sum(1 for r in all_results if r.get("final_status") == "NEEDS_REVIEW")
    rejects = sum(1 for r in all_results if r.get("final_status") == "REJECT")
    errors_count = sum(1 for r in all_results if r.get("final_status") in ("ERROR", "UNKNOWN"))

    print(f"  Total:        {total}")
    print(f"  AUTO_ACCEPT:  {accepts}  ({accepts/total*100:.0f}%)")
    print(f"  NEEDS_REVIEW: {reviews}  ({reviews/total*100:.0f}%)")
    print(f"  REJECT:       {rejects}  ({rejects/total*100:.0f}%)")
    print(f"  ERROR:        {errors_count}  ({errors_count/total*100:.0f}%)")

    passing = accepts + reviews  # Both are valid pipeline outcomes
    print(f"\n  Pipeline Success Rate: {passing}/{total} ({passing/total*100:.0f}%)")

    avg_conf = sum(r.get("overall_confidence", 0) for r in all_results if r.get("final_status") in ("AUTO_ACCEPT", "NEEDS_REVIEW")) / max(passing, 1)
    avg_time = sum(r.get("total_ms", 0) for r in all_results) / max(total, 1)
    print(f"  Avg Confidence (passing): {avg_conf:.4f}")
    print(f"  Avg Latency:              {avg_time:.0f}ms")

    # Per-image summary table
    print(f"\n  {'Image':<20} {'Status':<15} {'Conf':>8} {'Fields':>7} {'Time':>8}")
    print(f"  {'─'*20} {'─'*15} {'─':─>8} {'─':─>7} {'─':─>8}")
    for r in all_results:
        name = r["image"][:18]
        st = r.get("final_status", "?")
        conf = r.get("overall_confidence", 0)
        fc = len(r.get("phases", {}).get("5_6_7_validation", {}).get("fields_detail", []))
        ms = r.get("total_ms", 0)
        print(f"  {name:<20} {st:<15} {conf:>8.4f} {fc:>7} {ms:>7}ms")


if __name__ == "__main__":
    main()
