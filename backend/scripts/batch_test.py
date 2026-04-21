import sys
import os
import time
import base64
import requests
import uuid
import concurrent.futures

# Add parent dir to path to import backend modules if needed, 
# but here we test via HTTP API to ensure full integration verification.

API_URL = "http://localhost:8000"
DATASET_ID = "batch-test-dataset"
USER_ID = "tester-v2"

def ingest_form(image_path):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    payload = {
        "image": img_b64,
        "datasetId": DATASET_ID,
        "userId": USER_ID
    }
    
    start = time.time()
    response = requests.post(f"{API_URL}/ingest", json=payload)
    duration = time.time() - start
    
    return response.json(), duration

def run_batch_test(image_folder, num_workers=5):
    print(f"--- Starting Batch Validation Test (Workers: {num_workers}) ---")
    
    images = [os.path.join(image_folder, f) for f in os.listdir(image_folder) if f.endswith(('.jpg', '.png'))]
    if not images:
        print("No images found in folder.")
        return

    results = []
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_img = {executor.submit(ingest_form, img): img for img in images}
        for future in concurrent.futures.as_completed(future_to_img):
            img_path = future_to_img[future]
            try:
                res, duration = future.result()
                results.append({"path": img_path, "res": res, "lat": duration})
                print(f"Ingested {os.path.basename(img_path)} - Latency: {duration:.2f}s")
            except Exception as exc:
                print(f"{img_path} generated an exception: {exc}")

    total_duration = time.time() - start_total
    throughput = len(images) / (total_duration / 60)
    
    print("\n--- TEST SUMMARY ---")
    print(f"Total Forms: {len(images)}")
    print(f"Total Time: {total_duration:.2f}s")
    print(f"Throughput: {throughput:.2f} forms/minute")
    print(f"Avg Ingestion Latency: {sum(r['lat'] for r in results)/len(results):.2f}s")
    print("--------------------")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python batch_test.py <image_folder>")
    else:
        run_batch_test(sys.argv[1])
