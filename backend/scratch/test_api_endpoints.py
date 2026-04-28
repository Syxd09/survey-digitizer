import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from config import settings

headers = {"X-API-Key": settings.API_KEY}

def test_health(client):
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("Health check passed.")

def test_forms_list(client):
    response = client.get("/forms", headers=headers)
    assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
    assert "data" in response.json()
    print("Forms list passed.")

def test_metrics(client):
    response = client.get("/metrics/default", headers=headers)
    assert response.status_code == 200
    print("Metrics endpoint passed.")

if __name__ == "__main__":
    with TestClient(app) as client:
        test_health(client)
        test_forms_list(client)
        test_metrics(client)
        print("All API sanity checks passed.")
