"""Repetition-based header and footer detection across pages."""

from __future__ import annotations

import re
from collections import Counter

from app.extraction.logging import log_suppression_diagnostics
from app.extraction.normalization import normalize_for_comparison
from app.extraction.reading_order import RawBlock

_PAGE_NUM_RE = re.compile(
    r"^(?:page\s*)?\d{1,4}(?:\s*/\s*\d{1,4})?$",
    re.IGNORECASE,
)


def _is_page_number_like(text: str) -> bool:
    normalized = normalize_for_comparison(text)
    if not normalized:
        return False
    if _PAGE_NUM_RE.match(normalized):
        return True
    # Pure digits
    return bool(re.match(r"^\d{1,4}$", normalized))


def detect_repeated_regions(
    pages_blocks: list[list[RawBlock]],
    page_heights: list[float],
    *,
    min_page_ratio: float = 0.4,
    min_occurrences: int = 2,
) -> tuple[set[str], set[str]]:
    """
    Return (header_fingerprints, footer_fingerprints) for text repeated across pages.
    Fingerprints are normalized comparison strings.
    """
    header_counter: Counter[str] = Counter()
    footer_counter: Counter[str] = Counter()
    page_count = len(pages_blocks)

    if page_count == 0:
        return set(), set()

    for page_idx, blocks in enumerate(pages_blocks):
        if not blocks:
            continue
        page_height = (
            page_heights[page_idx] if page_idx < len(page_heights) else 792.0
        )
        top_band = page_height * 0.15
        bottom_band = page_height * 0.85

        for block in blocks:
            fp = normalize_for_comparison(block.text)
            if not fp or len(fp) < 2:
                continue
            x0, y0, x1, y1 = block.bbox
            if y0 <= top_band:
                header_counter[fp] += 1
            if y1 >= bottom_band:
                footer_counter[fp] += 1

    threshold = max(min_occurrences, int(page_count * min_page_ratio))

    header_fps = {
        fp
        for fp, c in header_counter.items()
        if c >= threshold and len(fp) >= 4
    }
    footer_fps = {
        fp
        for fp, c in footer_counter.items()
        if c >= threshold and len(fp) >= 4
    }

    # Page-number-like text in footer band on many pages
    for blocks in pages_blocks:
        for block in blocks:
            if _is_page_number_like(block.text):
                fp = normalize_for_comparison(block.text)
                if fp:
                    footer_fps.add(fp)

    return header_fps, footer_fps


def mark_page_headers_footers(
    blocks: list[RawBlock],
    header_fps: set[str],
    footer_fps: set[str],
    page_number: int,
    page_height: float,
) -> tuple[int, int]:
    """Mark blocks on a single page."""
    headers = 0
    footers = 0
    header_texts: list[str] = []
    footer_texts: list[str] = []

    for block in blocks:
        fp = normalize_for_comparison(block.text)
        x0, y0, x1, y1 = block.bbox
        in_top = y0 <= page_height * 0.15 if page_height else False
        in_bottom = y1 >= page_height * 0.85 if page_height else False

        if fp in footer_fps and (in_bottom or _is_page_number_like(block.text)):
            block.block_type = "footer"
            footers += 1
            footer_texts.append(block.text[:40])
        elif fp in header_fps and in_top:
            block.block_type = "header"
            headers += 1
            header_texts.append(block.text[:40])
        elif _is_page_number_like(block.text) and in_bottom:
            block.block_type = "footer"
            footers += 1
            footer_texts.append(block.text[:40])

    log_suppression_diagnostics(page_number, header_texts, footer_texts)
    return headers, footers
