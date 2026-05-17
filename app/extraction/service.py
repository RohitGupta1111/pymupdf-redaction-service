"""Extraction service: PDF fetch + threaded pipeline execution."""

from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.extraction.exceptions import (
    ExtractionError,
    ExtractionTimeoutError,
    InvalidPdfUrlError,
    PdfFetchError,
    PdfTooLargeError,
)
from app.extraction.pipeline import run_extraction_pipeline
from app.extraction.schemas import ExtractPdfOptions, ExtractedDocument

logger = logging.getLogger("app.extraction.service")

PDF_CONTENT_TYPES = (
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
)


async def fetch_pdf_bytes(url: str) -> tuple[bytes, float]:
    """
    Download PDF from presigned/S3 URL with size and timeout limits.
    Returns (bytes, fetch_duration_ms).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidPdfUrlError(f"Unsupported URL scheme: {parsed.scheme}")

    max_bytes = settings.MAX_EXTRACT_PDF_MB * 1024 * 1024
    timeout = httpx.Timeout(
        connect=10.0,
        read=float(settings.EXTRACT_FETCH_TIMEOUT_SECONDS),
        write=10.0,
        pool=10.0,
    )

    fetch_start = time.perf_counter()
    chunks: list[bytes] = []
    total = 0

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise PdfFetchError(
                        f"Failed to fetch PDF: HTTP {response.status_code}",
                        details={"status_code": response.status_code},
                    )

                content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                if content_type and content_type not in PDF_CONTENT_TYPES:
                    logger.warning(
                        "Unexpected content-type %s for PDF URL", content_type
                    )

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        cl = int(content_length)
                        if cl > max_bytes:
                            raise PdfTooLargeError(
                                f"Content-Length {cl} exceeds max {max_bytes} bytes",
                                details={"content_length": cl},
                            )
                    except ValueError:
                        pass

                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > max_bytes:
                        raise PdfTooLargeError(
                            f"PDF exceeds maximum size of {settings.MAX_EXTRACT_PDF_MB} MB",
                            details={"bytes_read": total},
                        )
                    chunks.append(chunk)

    except httpx.TimeoutException as e:
        raise PdfFetchError(f"PDF fetch timed out: {e}", details={"retryable": True}) from e
    except httpx.HTTPError as e:
        raise PdfFetchError(f"PDF fetch failed: {e}") from e

    if total == 0:
        raise PdfFetchError("Fetched PDF is empty")

    # Magic bytes check
    pdf_bytes = b"".join(chunks)
    if not pdf_bytes.startswith(b"%PDF"):
        raise PdfFetchError("Fetched content does not appear to be a PDF")

    fetch_ms = (time.perf_counter() - fetch_start) * 1000
    logger.info("[extract] fetched pdf bytes=%s duration_ms=%.1f", total, fetch_ms)
    return pdf_bytes, fetch_ms


def _effective_max_pages(options: ExtractPdfOptions) -> int:
    server_max = settings.MAX_EXTRACT_PAGES
    if options.max_pages is not None:
        return min(options.max_pages, server_max)
    return server_max


async def extract_document_from_url(
    pdf_url: str,
    options: ExtractPdfOptions,
) -> ExtractedDocument:
    """Full async extraction: fetch URL then run pipeline in worker thread."""
    pdf_bytes, fetch_ms = await fetch_pdf_bytes(pdf_url)
    max_pages = _effective_max_pages(options)

    try:
        document = await asyncio.wait_for(
            asyncio.to_thread(
                run_extraction_pipeline,
                pdf_bytes,
                options,
                max_pages=max_pages,
                source_url=pdf_url,
                process_timeout_seconds=float(settings.EXTRACT_PROCESS_TIMEOUT_SECONDS),
            ),
            timeout=float(settings.EXTRACT_PROCESS_TIMEOUT_SECONDS) + 5.0,
        )
    except asyncio.TimeoutError as e:
        raise ExtractionTimeoutError(
            "Extraction processing timed out",
        ) from e

    document.stats.fetch_duration_ms = fetch_ms
    return document


def map_extraction_error(exc: ExtractionError) -> tuple[int, dict]:
    return exc.http_status, {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "details": exc.details,
        }
    }
