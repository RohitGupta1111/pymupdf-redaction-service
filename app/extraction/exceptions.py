"""Typed exceptions for the extraction subsystem."""

from __future__ import annotations


class ExtractionError(Exception):
    """Base extraction error with machine-readable code."""

    code: str = "extraction_error"
    retryable: bool = False
    http_status: int = 400

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidPdfError(ExtractionError):
    code = "invalid_pdf"
    http_status = 400


class EncryptedPdfError(ExtractionError):
    code = "encrypted_pdf"
    http_status = 400


class PdfTooLargeError(ExtractionError):
    code = "pdf_too_large"
    http_status = 413


class PageLimitExceededError(ExtractionError):
    code = "page_limit_exceeded"
    http_status = 400


class ExtractionTimeoutError(ExtractionError):
    code = "extraction_timeout"
    retryable = True
    http_status = 504


class PdfFetchError(ExtractionError):
    code = "pdf_fetch_failed"
    retryable = True
    http_status = 400


class InvalidPdfUrlError(ExtractionError):
    code = "invalid_pdf_url"
    http_status = 400
