"""Extraction-specific logging helpers."""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("app.extraction")

_PREVIEW_MAX_LEN = 120


def extraction_debug_enabled() -> bool:
    return (
        settings.LOG_LEVEL.upper() == "DEBUG"
        or settings.ENABLE_DEBUG_EXTRACTION_LOGS is True
    )


def log_block_preview(page_number: int, block_id: str, text: str) -> None:
    if not extraction_debug_enabled():
        return
    preview = text.replace("\n", " ").strip()
    if len(preview) > _PREVIEW_MAX_LEN:
        preview = preview[:_PREVIEW_MAX_LEN] + "..."
    logger.debug(
        "[extract] page=%s block=%s preview=%r",
        page_number,
        block_id,
        preview,
    )


def log_reading_order_diagnostics(page_number: int, orders: list[tuple[str, int]]) -> None:
    if not extraction_debug_enabled():
        return
    sample = orders[:8]
    logger.debug("[extract] page=%s reading_order_sample=%s", page_number, sample)


def log_suppression_diagnostics(
    page_number: int,
    headers: list[str],
    footers: list[str],
) -> None:
    if not extraction_debug_enabled():
        return
    logger.debug(
        "[extract] page=%s headers=%s footers=%s",
        page_number,
        headers[:3],
        footers[:3],
    )


def log_coalescing_diagnostics(page_number: int, stats: dict) -> None:
    if not extraction_debug_enabled():
        return
    logger.debug(
        "[extract] page=%s coalescing blocks_before=%s blocks_after=%s merge_count=%s",
        page_number,
        stats.get("blocks_before"),
        stats.get("blocks_after"),
        stats.get("merge_count"),
    )


def log_column_layout_diagnostics(page_number: int, layout) -> None:
    if not extraction_debug_enabled():
        return
    logger.debug(
        "[extract] page=%s columns count=%s split_x=%s fallback=%s columns=%s",
        page_number,
        layout.column_count,
        layout.split_x,
        layout.fallback_used,
        layout.columns,
    )
