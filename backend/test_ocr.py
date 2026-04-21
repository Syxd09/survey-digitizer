import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.orchestrator import ExtractionOrchestrator
import base64
import asyncio

async def test_handwriting():
    print("[TEST] Loading test image...")
    
    with open("test-file.png", "rb") as f:
        img_data = f.read()
    
    image_b64 = base64.b64encode(img_data).decode('utf-8')
    
    print("[TEST] Initializing orchestrator...")
    orchestrator = ExtractionOrchestrator()
    
    print("[TEST] Running digitize()...")
    result = await orchestrator.digitize(image_b64)
    
    print("\n" + "="*60)
    print("[RESULT]")
    print(f"Questions found: {len(result.get('questions', []))}")
    print(f"Engine used: {result.get('diagnostics', {}).get('engine', 'NONE')}")
    print(f"Handwriting mode: {result.get('diagnostics', {}).get('handwriting_mode', 'unknown')}")
    print(f"Avg confidence: {result.get('diagnostics', {}).get('avg_confidence', 0):.2f}")
    print(f"Null rate: {result.get('diagnostics', {}).get('null_rate', 1):.2f}")
    
    if result.get('diagnostics', {}).get('error'):
        print(f"ERROR: {result['diagnostics']['error']}")
        if result['diagnostics'].get('details'):
            print(f"Details: {result['diagnostics']['details']}")
    
    print("\n[QUESTIONS]")
    for q in result.get('questions', [])[:10]:
        print(f"  - Q: {q.get('question', 'N/A')[:60]}...")
        print(f"    Selected: {q.get('selected', 'None')}")
        print(f"    Confidence: {q.get('confidence', 0):.2f}")
        print()
    
    return result

if __name__ == "__main__":
    result = asyncio.run(test_handwriting())
