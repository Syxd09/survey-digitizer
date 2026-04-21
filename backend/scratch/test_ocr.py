import asyncio
import base64
import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from services.orchestrator import ExtractionOrchestrator

async def run_test():
    print("Initializing Orchestrator...")
    orchestrator = ExtractionOrchestrator()
    
    image_path = "test-file.png"
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found.")
        return

    print(f"Loading {image_path}...")
    with open(image_path, "rb") as f:
        image_data = f.read()
        image_b64 = base64.b64encode(image_data).decode("utf-8")

    print("Running Digitization (Hydra Engine)...")
    result = await orchestrator.digitize(image_b64)
    
    print("\n--- RESULTS ---")
    # Truncate debug image for readability if it exists
    if "diagnostics" in result and "debug_image" in result["diagnostics"]:
        result["diagnostics"]["debug_image"] = "[TRUNCATED]"
        
    print(json.dumps(result, indent=2))
    print("\n--- DIAGNOSTICS ---")
    print(f"Engine Used: {result.get('diagnostics', {}).get('engine')}")
    print(f"Confidence: {result.get('diagnostics', {}).get('avg_confidence')}")
    print(f"Logic Version: {result.get('diagnostics', {}).get('logic_version')}")

if __name__ == "__main__":
    asyncio.run(run_test())
