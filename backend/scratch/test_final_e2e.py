import base64
import requests
import json
import os

API_KEY = "pipeline_secret_v2"
URL = "http://localhost:8000/process"
IMAGE_PATH = "/Users/deepstacker/WorkSpace/survey-digitizer/backend/test_survey.jpg"

def test_digitize():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Image not found at {IMAGE_PATH}")
        return

    with open(IMAGE_PATH, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "image": img_b64,
        "datasetId": "final_test_dataset"
    }

    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    print(f"Sending request to {URL}...")
    try:
        response = requests.post(URL, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("Success! Summary of results:")
            print(f"Request ID: {result.get('request_id')}")
            print(f"Status: {result.get('status')}")
            print(f"Overall Confidence: {result.get('overall_conf')}")
            print(f"Fields extracted: {len(result.get('fields', []))}")
            
            # Save full result for inspection
            with open("scratch/final_e2e_result.json", "w") as f:
                json.dump(result, f, indent=2)
            print("Full result saved to scratch/final_e2e_result.json")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_digitize()
