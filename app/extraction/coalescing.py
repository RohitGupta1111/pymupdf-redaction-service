"""Paragraph coalescing — merge adjacent line-level blocks into semantic units."""

from __future__ import annotations

import re

from app.extraction.logging import log_coalescing_diagnostics
from app.extraction.reading_order import RawBlock

_BULLET_START_RE = re.compile(
    r"^[\s]*(?:[•\-\*\u2022]|\d+[\.\)]|[a-zA-Z][\.\)])\s+\S",
    re.UNICODE,
)

_MERGEABLE_TYPES = frozenset({"paragraph", "list_item"})
_NEVER_MERGE_TYPES = frozenset({"heading", "table_row", "header", "footer"})

# Page-relative vertical gap threshold (fraction of page height)
_VERTICAL_GAP_RATIO = 0.025
_VERTICAL_GAP_MIN_PT = 6.0
_VERTICAL_GAP_MAX_PT = 18.0

# Left-edge alignment tolerance (points)
_LEFT_ALIGN_TOLERANCE_PT = 18.0

# Font size compatibility (relative)
_FONT_SIZE_TOLERANCE_RATIO = 0.18
_FONT_SIZE_TOLERANCE_MIN_PT = 1.5


def _vertical_gap_threshold(page_height: float) -> float:
    return min(
        _VERTICAL_GAP_MAX_PT,
        max(_VERTICAL_GAP_MIN_PT, page_height * _VERTICAL_GAP_RATIO),
    )


def _is_bullet_start(text: str) -> bool:
    return bool(_BULLET_START_RE.match(text))


def _ends_hard(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.endswith(":"):
        return True
    # Short ALL CAPS line (section label)
    letters = [c for c in stripped if c.isalpha()]
    if letters and len(stripped) < 80:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio >= 0.85 and len(stripped) < 50:
            return True
    return False


def _is_heading_like(block: RawBlock) -> bool:
    if block.block_type in _NEVER_MERGE_TYPES:
        return block.block_type == "heading"
    text = block.text.strip()
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if letters and len(text) < 60:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio >= 0.9:
            return True
    return False


def _font_compatible(current: RawBlock, nxt: RawBlock) -> bool:
    if current.font_size <= 0 or nxt.font_size <= 0:
        return True
    delta = abs(current.font_size - nxt.font_size)
    limit = max(
        _FONT_SIZE_TOLERANCE_MIN_PT,
        current.font_size * _FONT_SIZE_TOLERANCE_RATIO,
    )
    return delta <= limit


def _horizontal_aligned(current: RawBlock, nxt: RawBlock) -> bool:
    return abs(current.bbox[0] - nxt.bbox[0]) <= _LEFT_ALIGN_TOLERANCE_PT


def _vertical_gap(current: RawBlock, nxt: RawBlock) -> float:
    return nxt.bbox[1] - current.bbox[3]


def _can_merge_pair(
    current: RawBlock,
    nxt: RawBlock,
    page_height: float,
) -> bool:
    if current.block_type in _NEVER_MERGE_TYPES:
        return False
    if nxt.block_type in _NEVER_MERGE_TYPES:
        return False

    # New bullet or numbered item starts a new logical block
    if _is_bullet_start(nxt.text):
        return False
    # Do not absorb a second list_item into the first
    if current.block_type == "list_item" and nxt.block_type == "list_item":
        return False

    # Do not merge into heading-like next line
    if _is_heading_like(nxt):
        return False

    # Current ends a semantic unit
    if _ends_hard(current.text):
        return False

    gap_threshold = _vertical_gap_threshold(page_height)
    gap = _vertical_gap(current, nxt)
    if gap > gap_threshold:
        return False

    if not _horizontal_aligned(current, nxt):
        return False

    if not _font_compatible(current, nxt):
        return False

    # list_item: merge continuation paragraphs only
    if current.block_type == "list_item":
        return nxt.block_type == "paragraph"
    if current.block_type == "paragraph":
        return nxt.block_type in _MERGEABLE_TYPES

    return False


def _merge_blocks(current: RawBlock, nxt: RawBlock) -> RawBlock:
    """Merge nxt into current; return new RawBlock."""
    x0 = min(current.bbox[0], nxt.bbox[0])
    y0 = min(current.bbox[1], nxt.bbox[1])
    x1 = max(current.bbox[2], nxt.bbox[2])
    y1 = max(current.bbox[3], nxt.bbox[3])

    sep = " " if not current.text.endswith("-") else ""
    merged_text = f"{current.text.rstrip()}{sep}{nxt.text.lstrip()}"

    merged_meta = dict(current.metadata or {})
    merged_meta["coalesced_from"] = merged_meta.get("coalesced_from", 1) + 1

    font_size = current.font_size
    if nxt.font_size > 0:
        if font_size <= 0:
            font_size = nxt.font_size
        else:
            font_size = (current.font_size + nxt.font_size) / 2.0

    return RawBlock(
        index=current.index,
        text=merged_text,
        bbox=(x0, y0, x1, y1),
        font_size=font_size,
        block_type=current.block_type,
        metadata=merged_meta,
    )


def coalesce_paragraphs(
    blocks: list[RawBlock],
    page_height: float,
    page_number: int,
) -> tuple[list[RawBlock], dict]:
    """
    Merge adjacent paragraph-like blocks on the same page.

    Returns (coalesced_blocks, stats_dict).
    """
    if not blocks:
        return [], {"blocks_before": 0, "blocks_after": 0, "merge_count": 0}

    blocks_before = len(blocks)
    result: list[RawBlock] = []
    merge_count = 0
    current: RawBlock | None = None

    for nxt in blocks:
        if current is None:
            current = nxt
            continue

        if _can_merge_pair(current, nxt, page_height):
            current = _merge_blocks(current, nxt)
            merge_count += 1
        else:
            result.append(current)
            current = nxt

    if current is not None:
        result.append(current)

    blocks_after = len(result)
    stats = {
        "blocks_before": blocks_before,
        "blocks_after": blocks_after,
        "merge_count": merge_count,
    }
    log_coalescing_diagnostics(page_number, stats)
    return result, stats
