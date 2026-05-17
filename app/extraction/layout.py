"""Parse PyMuPDF dict-mode text into raw blocks."""

from __future__ import annotations

import re
from statistics import median

from app.extraction.normalization import normalize_block_text
from app.extraction.reading_order import RawBlock

_LIST_ITEM_RE = re.compile(
    r"^[\s]*(?:[•\-\*\u2022]|\d+[\.\)]|[a-zA-Z][\.\)])\s+\S",
    re.UNICODE,
)


def _span_font_size(span: dict) -> float:
    size = span.get("size") or 0.0
    try:
        return float(size)
    except (TypeError, ValueError):
        return 0.0


def _lines_to_text(lines: list[dict]) -> tuple[str, float]:
    """Concatenate line spans; return text and median font size."""
    sizes: list[float] = []
    parts: list[str] = []

    for line in lines:
        line_parts: list[str] = []
        for span in line.get("spans", []):
            text = span.get("text", "")
            if text:
                line_parts.append(text)
                sz = _span_font_size(span)
                if sz > 0:
                    sizes.append(sz)
        if line_parts:
            parts.append("".join(line_parts))

    text = "\n".join(parts)
    font_size = median(sizes) if sizes else 0.0
    return text, float(font_size)


def _line_bbox(line: dict) -> tuple[float, float, float, float] | None:
    bbox = line.get("bbox")
    if bbox and len(bbox) == 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    spans = line.get("spans") or []
    if not spans:
        return None
    xs0, ys0, xs1, ys1 = [], [], [], []
    for span in spans:
        sb = span.get("bbox")
        if sb and len(sb) == 4:
            xs0.append(float(sb[0]))
            ys0.append(float(sb[1]))
            xs1.append(float(sb[2]))
            ys1.append(float(sb[3]))
    if not xs0:
        return None
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _line_to_raw_block(line: dict, block_index: int, line_index: int) -> RawBlock | None:
    text, font_size = _lines_to_text([line])
    text = normalize_block_text(text)
    if not text.strip():
        return None
    bbox = _line_bbox(line)
    if bbox is None:
        return None
    return RawBlock(
        index=block_index * 1000 + line_index,
        text=text,
        bbox=bbox,
        font_size=font_size,
        metadata={"source_block_index": block_index, "source_line_index": line_index},
    )


def parse_dict_blocks(page_dict: dict, page_index: int) -> list[RawBlock]:
    """
    Convert page.get_text('dict') into RawBlock instances at line granularity.
    Skips image blocks (type != 0).
    """
    blocks: list[RawBlock] = []
    raw_blocks = page_dict.get("blocks") or []

    for block_index, block in enumerate(raw_blocks):
        if block.get("type") != 0:
            continue

        lines = block.get("lines") or []
        if not lines:
            continue

        for line_index, line in enumerate(lines):
            raw = _line_to_raw_block(line, block_index, line_index)
            if raw is not None:
                blocks.append(raw)

    return blocks


def classify_block_types(
    blocks: list[RawBlock],
    page_height: float,
    page_median_font: float,
) -> None:
    """Apply deterministic block-type heuristics in place (not header/footer — those use cross-page detection)."""
    if page_median_font <= 0:
        sizes = [b.font_size for b in blocks if b.font_size > 0]
        page_median_font = median(sizes) if sizes else 12.0

    for block in blocks:
        if block.block_type == "table_row":
            continue

        if _LIST_ITEM_RE.match(block.text):
            block.block_type = "list_item"
            continue

        line_count = block.text.count("\n") + 1
        is_short = len(block.text) < 120 and line_count <= 2
        if (
            block.font_size > 0
            and page_median_font > 0
            and block.font_size >= page_median_font * 1.15
            and is_short
        ):
            block.block_type = "heading"
            continue

        if block.block_type == "unknown":
            block.block_type = "paragraph"
