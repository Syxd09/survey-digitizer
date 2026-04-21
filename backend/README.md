# Survey Digitizer - Python Backend

This backend replaces the cloud AI (Groq/OpenRouter) with a local deterministic extraction pipeline.

## Prerequisites
- Python 3.9 or higher
- (Recommended) NVIDIA GPU with CUDA for faster OCR

## Setup Instructions

1. **Install Dependencies**:
   Open a terminal in the `backend` folder and run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Server**:
   ```bash
   python main.py
   ```
   The backend will start at `http://localhost:8000`.

## How it Works
- **FastAPI**: Handles communication with the React frontend.
- **img2table**: Automatically detects the survey grid and identifies question rows.
- **EasyOCR**: Extracts high-quality text from table cells without cloud hallucination.
- **Pixel Density Detection**: Deterministically detects "marked" answers by analyzing ink density in checkbox regions.

## Troubleshooting
- **Model Download**: On the first run, EasyOCR will download language models (~100MB). This may take a minute.
- **Accuracy**: Ensure the forms are reasonably aligned. The backend works best on clear, well-lit photos.
