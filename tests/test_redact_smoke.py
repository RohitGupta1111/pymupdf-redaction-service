"""Smoke tests for redaction functionality."""

import pytest
import base64
import fitz  # PyMuPDF
from fastapi.testclient import TestClient
from app.main import app
import os

client = TestClient(app)


def create_simple_pdf() -> bytes:
    """Create a simple 1-page PDF in memory."""
    doc = fitz.open()  # Create new PDF
    page = doc.new_page(width=612, height=792)  # US Letter size
    
    # Add some text
    text = "This is a test PDF with sensitive information."
    page.insert_text((72, 72), text, fontsize=12)
    
    # Save to bytes
    pdf_bytes = doc.tobytes()
    doc.close()
    
    return pdf_bytes


def test_redact_smoke():
    """Smoke test: create PDF, redact it, verify output."""
    api_key = os.getenv("REDACTION_SERVICE_API_KEY", "dev-secret")
    
    # Create test PDF
    pdf_bytes = create_simple_pdf()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    # Define redaction rectangle (covering the text area)
    # bbox format: [x0, y0, x1, y1] in PDF points, bottom-left origin
    # Text is at (72, 72) from top-left, so from bottom-left it's:
    # x0=72, y0=792-72-12=708, x1=72+200=272, y1=792-72=720
    redaction_rectangles = [
        {
            "page_index": 0,
            "bbox": [72, 708, 272, 720]  # Cover the text area
        }
    ]
    
    # Make request
    response = client.post(
        "/redact",
        headers={"X-Redaction-Key": api_key},
        json={
            "pdf_data": pdf_base64,
            "redaction_rectangles": redaction_rectangles
        }
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    result = response.json()
    
    # Verify response structure
    assert "redacted_pdf" in result
    assert "stats" in result
    
    # Verify stats
    stats = result["stats"]
    assert stats["pages"] == 1
    assert stats["rectangles_requested"] == 1
    assert stats["rectangles_applied"] == 1
    
    # Verify output PDF can be opened
    redacted_base64 = result["redacted_pdf"]
    redacted_bytes = base64.b64decode(redacted_base64)
    
    doc = fitz.open(stream=redacted_bytes, filetype="pdf")
    try:
        assert len(doc) == 1
        # PDF should be valid and openable
    finally:
        doc.close()


def test_redact_invalid_request():
    """Test that invalid requests return 422."""
    api_key = os.getenv("REDACTION_SERVICE_API_KEY", "dev-secret")
    
    # Invalid bbox (x0 >= x1)
    response = client.post(
        "/redact",
        headers={"X-Redaction-Key": api_key},
        json={
            "pdf_data": base64.b64encode(b"dummy").decode("utf-8"),
            "redaction_rectangles": [
                {
                    "page_index": 0,
                    "bbox": [100, 100, 50, 150]  # Invalid: x0 > x1
                }
            ]
        }
    )
    
    assert response.status_code == 422  # Validation error


def test_redact_empty_rectangles():
    """Test redaction with no rectangles (should still work)."""
    api_key = os.getenv("REDACTION_SERVICE_API_KEY", "dev-secret")
    
    pdf_bytes = create_simple_pdf()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    response = client.post(
        "/redact",
        headers={"X-Redaction-Key": api_key},
        json={
            "pdf_data": pdf_base64,
            "redaction_rectangles": []
        }
    )
    
    assert response.status_code == 200
    result = response.json()
    assert result["stats"]["rectangles_requested"] == 0
    assert result["stats"]["rectangles_applied"] == 0
