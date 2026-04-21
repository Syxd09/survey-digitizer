# Survey Digitizer OCR API — Hydra v11.0

High-accuracy local OCR pipeline for survey forms:
handwritten, printed, tabular, multilingual, signatures.

---

## Project structure

```
survey_ocr/
├── main.py                  ← FastAPI app (lifespan singleton, all routes)
├── services/
│   ├── __init__.py
│   ├── processor.py         ← Full OCR pipeline (PaddleOCR + TrOCR + Claude)
│   ├── orchestrator.py      ← Async wrapper / thread-pool dispatch
│   ├── storage.py           ← Atomic JSON file storage
│   ├── metrics.py           ← Dataset performance metrics
│   └── export.py            ← Excel export
├── feedback_loop/           ← Created automatically (SQLite memory)
├── data/                    ← Created automatically (scan JSON files)
├── temp_exports/            ← Created automatically (Excel exports)
├── requirements.txt
└── .env.example
```

---

## Quick start

### 1. Python version
Python 3.10 or 3.11 recommended.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **GPU note (NVIDIA):** replace `paddlepaddle` with `paddlepaddle-gpu` in
> `requirements.txt` before installing, then install the matching CUDA torch:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
> ```
>
> **Apple Silicon (MPS):** standard `torch` wheels include MPS support
> automatically.  No extra steps needed.

### 3. Environment variables

```bash
cp .env.example .env
# Edit .env — only ANTHROPIC_API_KEY is optional but recommended
```

### 4. Start the server

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000
```

The first startup downloads OCR model weights (~2 GB total).
Subsequent starts load from cache and take 20–40 s.

---

## API reference

### POST /process
Process an image synchronously and return OCR results.

```json
{
  "image": "<base64 string or data:image/...;base64,...>",
  "datasetId": "my-dataset",
  "userId": "user-123"
}
```

Response:
```json
{
  "success": true,
  "scanId": "uuid",
  "questions": [
    {
      "question": "Name",
      "selected": "John Smith",
      "options": [],
      "confidence": 0.94,
      "status": "LIST_PAIR",
      "imageHash": "abc123"
    }
  ],
  "total": 12,
  "avgConfidence": 0.89,
  "nullRate": 0.08,
  "diagnostics": { ... }
}
```

### POST /ingest
Fire-and-forget background processing.  Returns a scanId immediately.

### GET /scan/{dataset_id}/{scan_id}
Poll for scan status and results.

### POST /feedback
Teach Hydra a correction.  Send the `imageHash` from any question plus
the correct text.

```json
{
  "scanId": "uuid",
  "questionId": "q3",
  "correctedText": "Full Access",
  "imageHash": "abc123"
}
```

### GET /metrics/{dataset_id}
Aggregate stats (avg confidence, throughput, status distribution).

### POST /export
Download validated scans as a multi-sheet Excel file.

```json
{ "datasetId": "my-dataset" }
```

---

## Engine routing logic

| Content type          | Primary engine  | Fallback           |
|-----------------------|-----------------|--------------------|
| Printed / typed       | PaddleOCR       | EasyOCR            |
| Handwritten (>40%)    | EasyOCR         | TrOCR (per crop)   |
| Tables (any)          | img2table       | Contour detection  |
| Low confidence (<45%) | Claude vision   | Best available     |
| Multilingual          | EasyOCR (6 lang)| langdetect routing |

---

## Tuning tips

- **Increase `OCR_WORKERS`** in `.env` to match your physical CPU core count
  for higher throughput on batch jobs.
- **Claude fallback** is triggered for crops with confidence below
  `CLAUDE_FALLBACK_THRESHOLD` (default 0.45). Set to 0.0 to disable.
- **Sauvola binarisation** activates automatically when blur_score < 80.
  It handles scans with uneven lighting far better than OTSU.
- **Perspective correction** activates when a valid 4-point quadrilateral
  covering 20–97% of the image is detected (phone-shot documents).
- **Active learning**: every `/feedback` call is persisted in SQLite and
  returned immediately on the next scan containing the same visual hash.
  The top 2000 patterns are kept warm in RAM.