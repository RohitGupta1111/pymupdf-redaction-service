"""Pydantic models for extraction API and structured output."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


SCHEMA_VERSION = "1.0.0"


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE_ROW = "table_row"
    FOOTER = "footer"
    HEADER = "header"
    UNKNOWN = "unknown"


class WarningCode(str, Enum):
    ENCRYPTED_PDF = "encrypted_pdf"
    LIKELY_MULTI_COLUMN = "likely_multi_column"
    EMPTY_PAGE = "empty_page"
    LOW_TEXT_DENSITY = "low_text_density"
    EXCESSIVE_HEADER_FOOTER = "excessive_header_footer"
    EXTRACTION_TRUNCATED = "extraction_truncated"
    MALFORMED_PDF_PARTIAL = "malformed_pdf_partial"


class ExtractionWarning(BaseModel):
    code: WarningCode
    message: str
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractPdfOptions(BaseModel):
    suppress_headers_footers: bool = True
    include_bboxes: bool = True
    detect_tables: bool = True
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Override server max pages when lower",
    )

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, v: int | None) -> int | None:
        return v


class ExtractPdfRequest(BaseModel):
    pdf_url: HttpUrl
    options: ExtractPdfOptions = Field(default_factory=ExtractPdfOptions)


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class ExtractedBlock(BaseModel):
    block_id: str
    type: BlockType
    text: str
    bbox: BBox | None = None
    reading_order: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class PageStats(BaseModel):
    block_count: int
    chars_extracted: int
    duration_ms: float
    headers_detected: int = 0
    footers_detected: int = 0
    table_rows_detected: int = 0


class ExtractedPage(BaseModel):
    page_number: int = Field(ge=1, description="1-based page number")
    width: float
    height: float
    blocks: list[ExtractedBlock]
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    stats: PageStats | None = None
    layout_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Column layout, coalescing stats, etc.",
    )


class DocumentMetadata(BaseModel):
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None
    page_count: int
    is_encrypted: bool = False
    source_url: str | None = None


class ExtractionStats(BaseModel):
    duration_ms: float
    pages_processed: int
    pages_total: int
    total_blocks: int
    chars_extracted: int
    headers_suppressed: int = 0
    footers_suppressed: int = 0
    table_rows_detected: int = 0
    fetch_duration_ms: float = 0.0
    pdf_bytes: int = 0


class ExtractedDocument(BaseModel):
    schema_version: str = SCHEMA_VERSION
    document_metadata: DocumentMetadata
    pages: list[ExtractedPage]
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    stats: ExtractionStats


class ExtractionErrorResponse(BaseModel):
    error: dict[str, Any]
