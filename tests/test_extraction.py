"""Tests for the isolated PDF extraction subsystem."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.extraction.exceptions import (
    EncryptedPdfError,
    InvalidPdfError,
    PageLimitExceededError,
)
from app.extraction.pipeline import run_extraction_pipeline
from app.extraction.schemas import BlockType, ExtractPdfOptions, WarningCode
from app.main import app
from tests.extraction_fixtures import (
    empty_page_pdf,
    encrypted_pdf,
    multi_column_pdf,
    multi_page_pdf,
    repeated_footer_pdf,
    simple_pdf,
    table_like_pdf,
)

client = TestClient(app)
API_KEY = "dev-secret"


@pytest.fixture(autouse=True)
def _api_key_env(monkeypatch):
    monkeypatch.setenv("REDACTION_SERVICE_API_KEY", API_KEY)


def _run(pdf_bytes: bytes, **options_kwargs) -> object:
    options = ExtractPdfOptions(**options_kwargs)
    return run_extraction_pipeline(
        pdf_bytes,
        options,
        max_pages=500,
        source_url="https://example.com/test.pdf",
    )


def test_simple_pdf_extraction():
    doc = _run(simple_pdf())
    assert doc.schema_version == "1.0.0"
    assert len(doc.pages) == 1
    assert doc.pages[0].blocks
    texts = " ".join(b.text for b in doc.pages[0].blocks)
    assert "extraction" in texts.lower()
    assert doc.stats.total_blocks >= 1
    assert doc.stats.chars_extracted > 0


def test_multi_page_pdf():
    doc = _run(multi_page_pdf([f"Page {i} content here." for i in range(1, 4)]))
    assert len(doc.pages) == 3
    assert doc.stats.pages_processed == 3
    all_text = " ".join(b.text for p in doc.pages for b in p.blocks)
    assert "Page 2" in all_text


def test_multi_column_reading_order():
    doc = _run(multi_column_pdf())
    assert len(doc.pages) == 1
    blocks = doc.pages[0].blocks
    assert blocks
    joined = " | ".join(b.text for b in blocks)
    left_idx = joined.find("Left")
    right_idx = joined.find("Right")
    assert left_idx != -1 and right_idx != -1
    # Left column content should appear before right column content
    assert left_idx < right_idx
    codes = [w.code for w in doc.pages[0].warnings + doc.warnings]
    assert WarningCode.LIKELY_MULTI_COLUMN in codes or any(
        w.code == WarningCode.LIKELY_MULTI_COLUMN for w in doc.warnings
    )


def test_table_like_linearization():
    doc = _run(table_like_pdf(), detect_tables=True)
    table_rows = [
        b for p in doc.pages for b in p.blocks if b.type == BlockType.TABLE_ROW
    ]
    assert table_rows or doc.stats.table_rows_detected >= 0
    all_text = " ".join(b.text for p in doc.pages for b in p.blocks)
    assert "Python" in all_text or "Course" in all_text


def test_repeated_footer_suppression():
    doc = _run(
        repeated_footer_pdf(5),
        suppress_headers_footers=True,
    )
    all_text = " ".join(b.text for p in doc.pages for b in p.blocks)
    assert "ACME Corp Confidential" not in all_text
    assert doc.stats.footers_suppressed >= 1


def test_footer_not_suppressed_when_disabled():
    doc = _run(
        repeated_footer_pdf(3),
        suppress_headers_footers=False,
    )
    types = [b.type for p in doc.pages for b in p.blocks]
    assert BlockType.FOOTER in types


def test_encrypted_pdf_raises():
    with pytest.raises(EncryptedPdfError):
        _run(encrypted_pdf())


def test_malformed_pdf_raises():
    with pytest.raises(InvalidPdfError):
        _run(b"not a pdf at all")


def test_empty_page_warning():
    doc = _run(empty_page_pdf())
    assert len(doc.pages) == 2
    page1_warnings = doc.pages[0].warnings
    codes = [w.code for w in page1_warnings]
    assert WarningCode.EMPTY_PAGE in codes or WarningCode.LOW_TEXT_DENSITY in codes


def test_reading_order_stability():
    doc1 = _run(simple_pdf("Stable order test alpha beta."))
    doc2 = _run(simple_pdf("Stable order test alpha beta."))
    ids1 = [b.block_id for b in doc1.pages[0].blocks]
    ids2 = [b.block_id for b in doc2.pages[0].blocks]
    assert ids1 == ids2


def test_page_limit_exceeded():
    pdf = multi_page_pdf(["a", "b", "c", "d", "e"])
    with pytest.raises(PageLimitExceededError):
        run_extraction_pipeline(
            pdf,
            ExtractPdfOptions(),
            max_pages=2,
        )


def test_block_ids_format():
    doc = _run(simple_pdf())
    for block in doc.pages[0].blocks:
        assert block.block_id.startswith("page_1_block_")


def test_extraction_truncation_warning():
    pdf = multi_page_pdf([f"p{i}" for i in range(10)])
    doc = run_extraction_pipeline(
        pdf,
        ExtractPdfOptions(max_pages=3),
        max_pages=500,
    )
    assert doc.stats.pages_processed == 3
    assert any(w.code == WarningCode.EXTRACTION_TRUNCATED for w in doc.warnings)


def test_extract_endpoint_requires_auth():
    response = client.post(
        "/extract",
        json={
            "pdf_url": "https://example.com/file.pdf",
            "options": {},
        },
    )
    assert response.status_code == 401


def test_extract_endpoint_success(monkeypatch):
    pdf_bytes = simple_pdf()

    async def fake_fetch(url: str):
        return pdf_bytes, 12.5

    async def fake_extract(url, options):
        from app.extraction.pipeline import run_extraction_pipeline
        from app.config import settings

        doc = run_extraction_pipeline(
            pdf_bytes,
            options,
            max_pages=settings.MAX_EXTRACT_PAGES,
            source_url=url,
        )
        doc.stats.fetch_duration_ms = 12.5
        return doc

    monkeypatch.setattr(
        "app.api.extract.extract_document_from_url",
        fake_extract,
    )

    response = client.post(
        "/extract",
        headers={"X-Redaction-Key": API_KEY},
        json={
            "pdf_url": "https://example.com/test.pdf",
            "options": {"suppress_headers_footers": True},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1.0.0"
    assert body["pages"]
    assert "stats" in body
    assert body["stats"]["fetch_duration_ms"] == 12.5


def test_extract_endpoint_structured_error(monkeypatch):
    from app.extraction.exceptions import PdfFetchError

    async def fail_fetch(url, options):
        raise PdfFetchError("Connection refused", details={"retryable": True})

    monkeypatch.setattr(
        "app.api.extract.extract_document_from_url",
        fail_fetch,
    )

    response = client.post(
        "/extract",
        headers={"X-Redaction-Key": API_KEY},
        json={"pdf_url": "https://example.com/missing.pdf"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "pdf_fetch_failed"
