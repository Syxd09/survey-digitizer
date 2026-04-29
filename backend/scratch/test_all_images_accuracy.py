import os
import sys
import time
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.orchestrator import ExtractionOrchestrator

async def main():
    img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-images")
    if not os.path.exists(img_dir):
        print(f"Directory {img_dir} not found.")
        sys.exit(1)

    images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    print(f"Found {len(images)} images to test.\n")

    results = []

    executor = ThreadPoolExecutor(max_workers=2)
    orchestrator = ExtractionOrchestrator(executor)

    for img_name in sorted(images):
        img_path = os.path.join(img_dir, img_name)
        print(f"\n{'='*60}")
        print(f"Testing: {img_name}")
        print(f"{'='*60}")
        
        with open(img_path, "rb") as f:
            img_bytes = f.read()
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')

        start_time = time.time()
        try:
            result = await orchestrator.digitize(img_b64, request_id=img_name)
            latency = time.time() - start_time
            
            # DB returns flat structure, raw pipeline returns nested 'decision'
            if "decision" in result:
                status = result["decision"].get("status")
                confidence = result["decision"].get("confidence", 0)
            else:
                status = result.get("status")
                confidence = result.get("overall_conf", 0)
                
            success = status in ["ACCEPT", "REVIEW", "NEEDS_REVIEW"] 
            
            # Print breakdown
            if success:
                print(f"✅ SUCCESS ({latency:.2f}s) - Status: {status} - Confidence: {confidence:.2f}")
                print(f"Extracted fields:")
                for field in result.get("fields", []):
                    cleaned = field.get("cleaned") or field.get("cleaned_value") or field.get("cleaned_text")
                    raw = field.get("raw_value") or field.get("raw_text")
                    f_conf = field.get("confidence") or field.get("field_conf", 0)
                    print(f"  {field.get('id')}: {cleaned} (raw: {raw}, conf: {f_conf:.2f})")
                print("")
            else:
                print(f"❌ FAILED ({latency:.2f}s) - Status: {status}")
                print(f"Result: {result}\nError: {result.get('error')}")

            results.append({
                "image": img_name,
                "status": "success" if success else "failed",
                "confidence": confidence,
                "latency": latency
            })
            
        except Exception as e:
            latency = time.time() - start_time
            print(f"❌ CRASH ({latency:.2f}s) - Exception: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "image": img_name,
                "status": "crash",
                "error": str(e),
                "latency": latency
            })

    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    
    total = len(results)
    successes = sum(1 for r in results if r["status"] == "success")
    failures = sum(1 for r in results if r["status"] == "failed")
    crashes = sum(1 for r in results if r["status"] == "crash")
    
    avg_conf = sum(r.get("confidence", 0) for r in results if r["status"] == "success") / max(1, successes)
    avg_lat = sum(r.get("latency", 0) for r in results) / max(1, total)
    
    print(f"Total Images Processed: {total}")
    print(f"Successes: {successes}")
    print(f"Failures (Pipeline Logic): {failures}")
    print(f"Crashes (Exceptions): {crashes}")
    print(f"Accuracy Rate: {(successes / max(1, total)) * 100:.2f}%")
    print(f"Average Confidence (Successes): {avg_conf:.2f}")
    print(f"Average Latency: {avg_lat:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
