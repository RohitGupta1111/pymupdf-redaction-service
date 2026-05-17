"""Deterministic structured PDF extraction pipeline."""

from __future__ import annotations

import logging
import time
from statistics import median

import fitz  # PyMuPDF

from app.extraction.exceptions import (
    EncryptedPdfError,
    ExtractionTimeoutError,
    InvalidPdfError,
    PageLimitExceededError,
)
from app.extraction.header_footer import (
    detect_repeated_regions,
    mark_page_headers_footers,
)
from app.extraction.layout import classify_block_types, parse_dict_blocks
from app.extraction.logging import extraction_debug_enabled, log_block_preview, logger
from app.extraction.coalescing import coalesce_paragraphs
from app.extraction.reading_order import assign_reading_order, make_block_id
from app.extraction.schemas import (
    SCHEMA_VERSION,
    BBox,
    BlockType,
    DocumentMetadata,
    ExtractedBlock,
    ExtractedDocument,
    ExtractedPage,
    ExtractionStats,
    ExtractionWarning,
    ExtractPdfOptions,
    PageStats,
    WarningCode,
)
from app.extraction.tables import detect_table_row_blocks, try_find_tables

_LOW_TEXT_CHARS_PER_PAGE = 30
_HEADER_FOOTER_RATIO_WARN = 0.35


def _map_block_type(type_str: str) -> BlockType:
    try:
        return BlockType(type_str)
    except ValueError:
        return BlockType.UNKNOWN


def _metadata_from_doc(doc: fitz.Document, source_url: str | None) -> DocumentMetadata:
    meta = doc.metadata or {}
    return DocumentMetadata(
        title=meta.get("title") or None,
        author=meta.get("author") or None,
        subject=meta.get("subject") or None,
        creator=meta.get("creator") or None,
        producer=meta.get("producer") or None,
        creation_date=meta.get("creationDate") or None,
        modification_date=meta.get("modDate") or None,
        page_count=len(doc),
        is_encrypted=bool(doc.is_encrypted),
        source_url=source_url,
    )


def _page_warnings(
    page_number: int,
    blocks: list,
    likely_multi_column: bool,
    page_height: float,
) -> list[ExtractionWarning]:
    warnings: list[ExtractionWarning] = []
    chars = sum(len(b.text) for b in blocks)

    if chars < _LOW_TEXT_CHARS_PER_PAGE:
        warnings.append(
            ExtractionWarning(
                code=WarningCode.EMPTY_PAGE if chars == 0 else WarningCode.LOW_TEXT_DENSITY,
                message=f"Page {page_number} has low text content ({chars} chars)",
                page_number=page_number,
                metadata={"chars": chars},
            )
        )

    if likely_multi_column:
        warnings.append(
            ExtractionWarning(
                code=WarningCode.LIKELY_MULTI_COLUMN,
                message=f"Page {page_number} appears to use multi-column layout",
                page_number=page_number,
            )
        )

    hf_count = sum(1 for b in blocks if b.block_type in ("header", "footer"))
    if blocks and hf_count / len(blocks) > _HEADER_FOOTER_RATIO_WARN:
        warnings.append(
            ExtractionWarning(
                code=WarningCode.EXCESSIVE_HEADER_FOOTER,
                message=f"Page {page_number} has high header/footer block ratio",
                page_number=page_number,
                metadata={"ratio": round(hf_count / len(blocks), 2)},
            )
        )

    return warnings


def run_extraction_pipeline(
    pdf_bytes: bytes,
    options: ExtractPdfOptions,
    *,
    max_pages: int,
    source_url: str | None = None,
    process_timeout_seconds: float | None = None,
) -> ExtractedDocument:
    """
    Synchronous extraction entry point (call via asyncio.to_thread).
    """
    pipeline_start = time.perf_counter()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error("Failed to open PDF for extraction: %s", e)
        raise InvalidPdfError(f"Invalid or corrupted PDF: {e}") from e

    warnings: list[ExtractionWarning] = []

    try:
        if doc.is_encrypted:
            if doc.needs_pass:
                raise EncryptedPdfError(
                    "PDF is encrypted and requires a password",
                )
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.ENCRYPTED_PDF,
                    message="PDF is marked encrypted but opened without password",
                )
            )

        total_pages = len(doc)
        if total_pages > max_pages:
            raise PageLimitExceededError(
                f"PDF has {total_pages} pages, exceeds maximum of {max_pages}",
                details={"page_count": total_pages, "max_pages": max_pages},
            )

        effective_max = options.max_pages or max_pages
        pages_to_process = min(total_pages, effective_max, max_pages)

        if pages_to_process < total_pages:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.EXTRACTION_TRUNCATED,
                    message=f"Processed {pages_to_process} of {total_pages} pages",
                    metadata={
                        "pages_processed": pages_to_process,
                        "pages_total": total_pages,
                    },
                )
            )

        doc_metadata = _metadata_from_doc(doc, source_url)

        # Pass 1: extract raw blocks per page
        all_page_blocks: list[list] = []
        page_dims: list[tuple[float, float]] = []
        multi_column_pages = 0

        for page_index in range(pages_to_process):
            if process_timeout_seconds:
                elapsed = time.perf_counter() - pipeline_start
                if elapsed > process_timeout_seconds:
                    raise ExtractionTimeoutError(
                        f"Extraction exceeded timeout ({process_timeout_seconds}s)",
                    )

            page = doc[page_index]
            page_number = page_index + 1
            rect = page.rect
            width, height = float(rect.width), float(rect.height)
            page_dims.append((width, height))

            page_start = time.perf_counter()
            try:
                page_dict = page.get_text("dict")
            except Exception as e:
                logger.warning("Page %s get_text failed: %s", page_number, e)
                warnings.append(
                    ExtractionWarning(
                        code=WarningCode.MALFORMED_PDF_PARTIAL,
                        message=f"Partial extraction failure on page {page_number}",
                        page_number=page_number,
                        metadata={"error": str(e)},
                    )
                )
                all_page_blocks.append([])
                continue

            blocks = parse_dict_blocks(page_dict, page_index)

            if options.detect_tables:
                blocks = try_find_tables(page, blocks)
                blocks = detect_table_row_blocks(blocks)

            sizes = [b.font_size for b in blocks if b.font_size > 0]
            page_median_font = median(sizes) if sizes else 12.0
            classify_block_types(blocks, height, page_median_font)

            all_page_blocks.append(blocks)

            if extraction_debug_enabled():
                logger.debug(
                    "[extract] page=%s raw_blocks=%s duration_ms=%.1f",
                    page_number,
                    len(blocks),
                    (time.perf_counter() - page_start) * 1000,
                )

        # Pass 2: cross-page header/footer fingerprints
        header_fps, footer_fps = detect_repeated_regions(
            all_page_blocks,
            [h for _, h in page_dims],
        )

        extracted_pages: list[ExtractedPage] = []
        total_blocks = 0
        total_chars = 0
        headers_suppressed = 0
        footers_suppressed = 0
        table_rows_detected = 0

        # Pass 3: reading order, labeling, serialization
        for page_index in range(pages_to_process):
            page_number = page_index + 1
            page_start = time.perf_counter()
            blocks = all_page_blocks[page_index]
            width, height = page_dims[page_index]

            h_marked, f_marked = mark_page_headers_footers(
                blocks, header_fps, footer_fps, page_number, height
            )

            ordered, likely_multi_column, column_layout = assign_reading_order(
                blocks, width, page_number
            )
            if likely_multi_column:
                multi_column_pages += 1

            coalesced, coalesce_stats = coalesce_paragraphs(
                ordered, height, page_number
            )

            layout_metadata: dict = {}
            if column_layout.likely_multi_column:
                layout_metadata["column_layout"] = {
                    "likely_multi_column": column_layout.likely_multi_column,
                    "column_count": column_layout.column_count,
                    "split_x": column_layout.split_x,
                    "columns": column_layout.columns,
                    "fallback_used": column_layout.fallback_used,
                }
            if coalesce_stats.get("merge_count", 0) > 0:
                layout_metadata["coalescing"] = coalesce_stats

            page_warnings = _page_warnings(
                page_number, coalesced, likely_multi_column, height
            )

            output_blocks: list[ExtractedBlock] = []
            order_idx = 0
            page_table_rows = 0

            for block in coalesced:
                if (
                    options.suppress_headers_footers
                    and block.block_type in ("header", "footer")
                ):
                    if block.block_type == "header":
                        headers_suppressed += 1
                    else:
                        footers_suppressed += 1
                    continue

                order_idx += 1
                block_id = make_block_id(page_number, order_idx)
                log_block_preview(page_number, block_id, block.text)

                bbox_model = None
                if options.include_bboxes:
                    x0, y0, x1, y1 = block.bbox
                    bbox_model = BBox(x0=x0, y0=y0, x1=x1, y1=y1)

                if block.block_type == "table_row":
                    page_table_rows += 1

                output_blocks.append(
                    ExtractedBlock(
                        block_id=block_id,
                        type=_map_block_type(block.block_type),
                        text=block.text,
                        bbox=bbox_model,
                        reading_order=order_idx,
                        metadata=dict(block.metadata or {}),
                    )
                )

            page_chars = sum(len(b.text) for b in output_blocks)
            total_blocks += len(output_blocks)
            total_chars += page_chars
            table_rows_detected += page_table_rows

            page_stats = PageStats(
                block_count=len(output_blocks),
                chars_extracted=page_chars,
                duration_ms=(time.perf_counter() - page_start) * 1000,
                headers_detected=h_marked,
                footers_detected=f_marked,
                table_rows_detected=page_table_rows,
            )

            extracted_pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width=width,
                    height=height,
                    blocks=output_blocks,
                    warnings=page_warnings,
                    stats=page_stats,
                    layout_metadata=layout_metadata,
                )
            )

        if multi_column_pages > 0:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.LIKELY_MULTI_COLUMN,
                    message=f"Multi-column layout detected on {multi_column_pages} page(s)",
                    metadata={"pages": multi_column_pages},
                )
            )

        duration_ms = (time.perf_counter() - pipeline_start) * 1000

        stats = ExtractionStats(
            duration_ms=duration_ms,
            pages_processed=pages_to_process,
            pages_total=total_pages,
            total_blocks=total_blocks,
            chars_extracted=total_chars,
            headers_suppressed=headers_suppressed,
            footers_suppressed=footers_suppressed,
            table_rows_detected=table_rows_detected,
            pdf_bytes=len(pdf_bytes),
        )

        logger.info(
            "[extract] complete pages=%s blocks=%s chars=%s duration_ms=%.1f",
            pages_to_process,
            total_blocks,
            total_chars,
            duration_ms,
        )

        return ExtractedDocument(
            schema_version=SCHEMA_VERSION,
            document_metadata=doc_metadata,
            pages=extracted_pages,
            warnings=warnings,
            stats=stats,
        )

    finally:
        doc.close()
