# PyMuPDF PDF Redaction Service

A production-ready microservice for applying true redactions to PDFs using PyMuPDF (fitz). This service accepts a PDF and a list of rectangles, applies redactions that permanently remove text, and returns the redacted PDF.

## Features

- **True PDF redaction** using PyMuPDF's redaction annotations
- **API key authentication** via `X-Redaction-Key` header
- **Robust validation** with bounds checking and error handling
- **Dockerized** for easy deployment
- **Fast and efficient** for resume PDFs

## API Contract

### Request Format

```json
{
  "pdf_data": "<base64_encoded_pdf_bytes>",
  "redaction_rectangles": [
    {"page_index": 0, "bbox": [x0, y0, x1, y1]},
    {"page_index": 1, "bbox": [x0, y0, x1, y1]}
  ]
}
```

**Important Notes:**
- `bbox` format: `[x0, y0, x1, y1]` in PDF points
- Origin: **bottom-left** (PDF coordinate system)
- Pages are **0-indexed**
- `x0 < x1` and `y0 < y1` must be true

### Response Format

```json
{
  "redacted_pdf": "<base64_encoded_redacted_pdf_bytes>",
  "stats": {
    "pages": 2,
    "rectangles_requested": 7,
    "rectangles_applied": 7,
    "rectangles_skipped_out_of_bounds": 0
  }
}
```

### Authentication

All endpoints except `/health` require the `X-Redaction-Key` header:

```
X-Redaction-Key: <your-api-key>
```

Missing or invalid keys return `401 Unauthorized`.

## Endpoints

### GET /health

Health check endpoint. No authentication required.

**Response:**
```json
{
  "status": "ok"
}
```

### POST /redact

Apply redactions to a PDF. Requires authentication.

**Headers:**
- `X-Redaction-Key`: API key (required)
- `Content-Type`: `application/json`

**Request Body:** See Request Format above

**Response:** See Response Format above

**Error Codes:**
- `400`: Invalid PDF, size exceeds limit, or redaction error
- `401`: Missing or invalid API key
- `422`: Validation error (invalid bbox format, etc.)
- `500`: Internal server error

## Local Development

### Prerequisites

- Python 3.11+
- pip

### Setup

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set environment variables:

```bash
export REDACTION_SERVICE_API_KEY=dev-secret
export LOG_LEVEL=INFO
export MAX_PDF_MB=10
export MAX_PAGES=30
```

Or create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
# Edit .env with your values
```

4. Run the service:

```bash
uvicorn app.main:app --reload --port 8080
```

The service will be available at `http://localhost:8080`

### Testing

Run tests with pytest:

```bash
pytest
```

Or with coverage:

```bash
pytest --cov=app tests/
```

## Docker Deployment

### Build

```bash
docker build -t pymupdf-redactor .
```

### Run

```bash
docker run -p 8080:8080 \
  -e REDACTION_SERVICE_API_KEY=your-secret-key \
  -e LOG_LEVEL=INFO \
  -e MAX_PDF_MB=10 \
  -e MAX_PAGES=30 \
  -e PORT=8080 \
  pymupdf-redactor
```

The service will be available at `http://localhost:8080`

## Usage Examples

### Health Check

```bash
curl http://localhost:8080/health
```

**Response:**
```json
{"status": "ok"}
```

### Redact PDF

```bash
curl -X POST http://localhost:8080/redact \
  -H "X-Redaction-Key: dev-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_data": "<base64_encoded_pdf>",
    "redaction_rectangles": [
      {
        "page_index": 0,
        "bbox": [100, 700, 200, 720]
      }
    ]
  }'
```

### Python Example

```python
import requests
import base64

# Read PDF file
with open("resume.pdf", "rb") as f:
    pdf_bytes = f.read()

# Encode to base64
pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

# Prepare request
payload = {
    "pdf_data": pdf_base64,
    "redaction_rectangles": [
        {
            "page_index": 0,
            "bbox": [100, 700, 200, 720]  # Bottom-left origin
        }
    ]
}

# Make request
response = requests.post(
    "http://localhost:8080/redact",
    headers={"X-Redaction-Key": "dev-secret"},
    json=payload
)

if response.status_code == 200:
    result = response.json()
    redacted_pdf = base64.b64decode(result["redacted_pdf"])
    
    # Save redacted PDF
    with open("resume_redacted.pdf", "wb") as f:
        f.write(redacted_pdf)
    
    print(f"Stats: {result['stats']}")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

## Configuration

Environment variables (all optional except `REDACTION_SERVICE_API_KEY`):

- `REDACTION_SERVICE_API_KEY` (required): API key for authentication
- `MAX_PDF_MB` (default: 10): Maximum PDF size in MB
- `MAX_PAGES` (default: 30): Maximum number of pages allowed
- `REQUEST_TIMEOUT_SECONDS` (default: 30): Request timeout
- `LOG_LEVEL` (default: INFO): Logging level (DEBUG, INFO, WARNING, ERROR)
- `PORT` (default: 8080): Server port number

## Bounding Box Coordinate System

**Important:** The service uses PDF's native coordinate system:

- **Origin**: Bottom-left corner
- **Units**: PDF points (1/72 inch)
- **Format**: `[x0, y0, x1, y1]` where:
  - `x0, y0`: Bottom-left corner
  - `x1, y1`: Top-right corner
  - `x0 < x1` and `y0 < y1`

Example for a US Letter page (612 × 792 points):
- Bottom-left corner: `[0, 0]`
- Top-right corner: `[612, 792]`
- Text at 1 inch from bottom-left: `[72, 72]` (bottom-left) to `[200, 84]` (top-right)

## Project Structure

```
pymupdf-redaction-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── schemas.py           # Pydantic models
│   ├── redactor.py          # Redaction engine
│   ├── security.py          # API key authentication
│   └── logging_config.py    # Logging setup
├── tests/
│   ├── __init__.py
│   ├── test_health.py       # Health endpoint tests
│   ├── test_auth.py         # Authentication tests
│   └── test_redact_smoke.py # Redaction smoke tests
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .env.example
└── README.md
```

## License

MIT
