@echo off
cd /d E:\webProgramming\survey-digitizer\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001
