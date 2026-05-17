"""Extraction API router — isolated from redaction."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.extraction.exceptions import ExtractionError
from app.extraction.schemas import ExtractPdfRequest, ExtractedDocument
from app.extraction.service import extract_document_from_url, map_extraction_error
from app.security import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction"])


@router.post("/extract", response_model=ExtractedDocument)
async def extract_pdf(
    request: ExtractPdfRequest,
    _: None = Depends(require_api_key),
) -> ExtractedDocument:
    """
    Extract structured document JSON from a PDF at a presigned/S3 URL.

    Requires X-Redaction-Key header (same API key as redaction endpoints).
    """
    start = time.perf_counter()
    pdf_url = str(request.pdf_url)

    logger.info("[extract] request url_host=%s", request.pdf_url.host)

    try:
        document = await extract_document_from_url(pdf_url, request.options)
    except ExtractionError as e:
        status, body = map_extraction_error(e)
        logger.warning("[extract] failed code=%s: %s", e.code, e.message)
        raise HTTPException(status_code=status, detail=body) from e
    except Exception as e:
        logger.error("[extract] unexpected error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "internal_error",
                    "message": str(e),
                    "retryable": True,
                }
            },
        ) from e

    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "[extract] response pages=%s blocks=%s elapsed_ms=%.1f",
        document.stats.pages_processed,
        document.stats.total_blocks,
        elapsed,
    )
    return document
