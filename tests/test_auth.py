"""Tests for API key authentication."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
import os

client = TestClient(app)


def test_redact_without_api_key():
    """Test that /redact without API key returns 401."""
    response = client.post(
        "/redact",
        json={
            "pdf_data": "dummy",
            "redaction_rectangles": []
        }
    )
    assert response.status_code == 401
    assert "Missing" in response.json()["detail"] or "Invalid" in response.json()["detail"]


def test_redact_with_wrong_api_key():
    """Test that /redact with wrong API key returns 401."""
    response = client.post(
        "/redact",
        headers={"X-Redaction-Key": "wrong-key"},
        json={
            "pdf_data": "dummy",
            "redaction_rectangles": []
        }
    )
    assert response.status_code == 401
    assert "Invalid" in response.json()["detail"]


def test_redact_with_correct_api_key():
    """Test that /redact with correct API key doesn't return 401 (may return other errors)."""
    # Get the API key from environment
    api_key = os.getenv("REDACTION_SERVICE_API_KEY", "dev-secret")
    
    response = client.post(
        "/redact",
        headers={"X-Redaction-Key": api_key},
        json={
            "pdf_data": "invalid_base64",
            "redaction_rectangles": []
        }
    )
    # Should not be 401 (authentication passed), but may be 400/422 for invalid data
    assert response.status_code != 401
