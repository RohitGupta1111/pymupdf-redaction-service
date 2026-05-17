"""Lightweight table-aware linearization heuristics."""

from __future__ import annotations

import re
from app.extraction.reading_order import RawBlock

# Multiple spaces or tab gaps suggesting columns
_COLUMN_GAP_RE = re.compile(r"\s{2,}|\t")
_PIPE_ROW_RE = re.compile(r"\|.+\|")


def _has_column_gaps(text: str) -> bool:
    return bool(_COLUMN_GAP_RE.search(text))


def _split_columns(text: str) -> list[str]:
    parts = _COLUMN_GAP_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def detect_table_row_blocks(blocks: list[RawBlock]) -> list[RawBlock]:
    """
    Identify table-like rows via alignment and column spacing.
    May merge/split blocks into table_row typed entries.
    """
    if not blocks:
        return blocks

    # Group blocks with similar y0 (same row band)
    row_bands: dict[int, list[RawBlock]] = {}
    y_tolerance = 4.0

    for block in blocks:
        y0 = block.bbox[1]
        band_key = int(y0 / y_tolerance)
        row_bands.setdefault(band_key, []).append(block)

    table_row_indices: set[int] = set()
    result: list[RawBlock] = []

    for band_blocks in row_bands.values():
        if len(band_blocks) < 2:
            result.extend(band_blocks)
            continue

        # Check if multiple blocks in band have column-like gaps or pipes
        column_like = sum(
            1
            for b in band_blocks
            if _has_column_gaps(b.text) or _PIPE_ROW_RE.search(b.text)
        )

        if column_like >= 2 or (
            len(band_blocks) >= 2
            and all(_has_column_gaps(b.text) for b in band_blocks)
        ):
            # Linearize band into one table row per block, typed table_row
            for b in band_blocks:
                b.block_type = "table_row"
                if _has_column_gaps(b.text):
                    cols = _split_columns(b.text)
                    b.text = " | ".join(cols)
                    b.metadata["table_linearized"] = True
                table_row_indices.add(b.index)
            result.extend(sorted(band_blocks, key=lambda b: b.bbox[0]))
        else:
            result.extend(band_blocks)

    # Align consecutive single blocks with column gaps as table rows
    for block in result:
        if block.index in table_row_indices:
            continue
        if _has_column_gaps(block.text) and len(_split_columns(block.text)) >= 2:
            cols = _split_columns(block.text)
            block.text = " | ".join(cols)
            block.block_type = "table_row"
            block.metadata["table_linearized"] = True

    return result


def try_find_tables(page, blocks: list[RawBlock]) -> list[RawBlock]:
    """
    Optional PyMuPDF find_tables pass — converts table cells to table_row blocks.
  Falls back silently if unavailable.
    """
    if not hasattr(page, "find_tables"):
        return blocks

    try:
        tables = page.find_tables()
    except Exception:
        return blocks

    if not tables or not getattr(tables, "tables", None):
        return blocks

    table_blocks: list[RawBlock] = []
    consumed_bbox: list[tuple[float, float, float, float]] = []

    for table in tables.tables:
        try:
            data = table.extract()
        except Exception:
            continue
        if not data:
            continue

        bbox = getattr(table, "bbox", None)
        if bbox:
            consumed_bbox.append(tuple(bbox))

        for row in data:
            if not row:
                continue
            cells = [str(c).strip() if c is not None else "" for c in row]
            if not any(cells):
                continue
            text = " | ".join(cells)
            tbbox = tuple(bbox) if bbox else (0.0, 0.0, 0.0, 0.0)
            table_blocks.append(
                RawBlock(
                    index=-1,
                    text=text,
                    bbox=tbbox,
                    font_size=0.0,
                    block_type="table_row",
                    metadata={"table_source": "find_tables"},
                )
            )

    if not table_blocks:
        return blocks

    # Remove dict blocks heavily overlapping table regions
    def overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)

    filtered = [
        b
        for b in blocks
        if not any(overlaps(b.bbox, tb) for tb in consumed_bbox)
    ]
    return filtered + table_blocks
