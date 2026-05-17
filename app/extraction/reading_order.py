"""Deterministic reading-order stabilization heuristics."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.extraction.logging import log_column_layout_diagnostics, log_reading_order_diagnostics


@dataclass
class RawBlock:
    """Internal block before final serialization."""

    index: int
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    block_type: str = "unknown"
    metadata: dict | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ColumnLayout:
    """Column detection result for a page."""

    likely_multi_column: bool = False
    column_count: int = 1
    split_x: float | None = None
    columns: list[dict] = field(default_factory=list)
    fallback_used: bool = False


def _block_sort_key(block: RawBlock) -> tuple[float, float]:
    x0, y0, x1, y1 = block.bbox
    return (y0, x0)


def _cluster_x0_values(x0_values: list[float], tolerance: float) -> list[list[float]]:
    """Group x0 values into clusters within tolerance."""
    if not x0_values:
        return []
    sorted_vals = sorted(x0_values)
    clusters: list[list[float]] = [[sorted_vals[0]]]
    for v in sorted_vals[1:]:
        if v - clusters[-1][-1] <= tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def _cluster_centers(clusters: list[list[float]]) -> list[float]:
    return [sum(c) / len(c) for c in clusters]


def detect_column_layout(
    blocks: list[RawBlock],
    page_width: float,
) -> ColumnLayout:
    """
    Detect column bands using left-edge (x0) clustering and gap analysis.
    Falls back to single-column when ambiguous.
    """
    layout = ColumnLayout()
    if len(blocks) < 4 or page_width <= 0:
        layout.fallback_used = True
        return layout

    x0s = [b.bbox[0] for b in blocks]
    tolerance = max(15.0, page_width * 0.04)
    clusters = _cluster_x0_values(x0s, tolerance)
    centers = _cluster_centers(clusters)

    if len(centers) < 2:
        layout.fallback_used = True
        return layout

    # Largest gap between cluster centers
    max_gap = 0.0
    split_idx = 0
    for i in range(len(centers) - 1):
        gap = centers[i + 1] - centers[i]
        if gap > max_gap:
            max_gap = gap
            split_idx = i

    min_gap = page_width * 0.10
    if max_gap < min_gap:
        layout.fallback_used = True
        return layout

    split_x = (centers[split_idx] + centers[split_idx + 1]) / 2.0

    left_blocks = [b for b in blocks if b.bbox[0] < split_x]
    right_blocks = [b for b in blocks if b.bbox[0] >= split_x]

    if len(left_blocks) < 2 or len(right_blocks) < 2:
        layout.fallback_used = True
        return layout

    # Confirm left column is actually left of right column
    left_median = sorted(b.bbox[0] for b in left_blocks)[len(left_blocks) // 2]
    right_median = sorted(b.bbox[0] for b in right_blocks)[len(right_blocks) // 2]
    if left_median >= right_median:
        layout.fallback_used = True
        return layout

    layout.likely_multi_column = True
    layout.column_count = 2
    layout.split_x = split_x
    layout.columns = [
        {
            "index": 0,
            "block_count": len(left_blocks),
            "x_min": min(b.bbox[0] for b in left_blocks),
            "x_max": max(b.bbox[2] for b in left_blocks),
        },
        {
            "index": 1,
            "block_count": len(right_blocks),
            "x_min": min(b.bbox[0] for b in right_blocks),
            "x_max": max(b.bbox[2] for b in right_blocks),
        },
    ]
    return layout


def _assign_block_column(block: RawBlock, layout: ColumnLayout) -> int:
    """Assign block to column index using left edge vs split."""
    if layout.split_x is None:
        return 0
    return 0 if block.bbox[0] < layout.split_x else 1


def _order_multi_column(
    blocks: list[RawBlock],
    layout: ColumnLayout,
) -> list[RawBlock]:
    """Read columns left-to-right; within each column top-to-bottom."""
    if layout.split_x is None:
        return sorted(blocks, key=_block_sort_key)

    columns: dict[int, list[RawBlock]] = {0: [], 1: []}
    for block in blocks:
        col = _assign_block_column(block, layout)
        columns[col].append(block)

    ordered: list[RawBlock] = []
    for col_idx in sorted(columns.keys()):
        col_blocks = sorted(columns[col_idx], key=_block_sort_key)
        ordered.extend(col_blocks)
    return ordered


def assign_reading_order(
    blocks: list[RawBlock],
    page_width: float,
    page_number: int,
) -> tuple[list[RawBlock], bool, ColumnLayout]:
    """
    Sort blocks in human reading order (column-aware when detected).
    Returns (ordered_blocks, likely_multi_column, column_layout).
    """
    if not blocks:
        empty_layout = ColumnLayout(fallback_used=True)
        return [], False, empty_layout

    layout = detect_column_layout(blocks, page_width)

    if layout.likely_multi_column and not layout.fallback_used:
        ordered = _order_multi_column(blocks, layout)
        likely_multi_column = True
    else:
        ordered = sorted(blocks, key=_block_sort_key)
        likely_multi_column = False
        layout = ColumnLayout(fallback_used=True)

    log_column_layout_diagnostics(page_number, layout)
    diagnostics = [(f"idx{b.index}", i) for i, b in enumerate(ordered)]
    log_reading_order_diagnostics(page_number, diagnostics)

    return ordered, likely_multi_column, layout


def make_block_id(page_number: int, order_index: int) -> str:
    """Deterministic block identifier."""
    return f"page_{page_number}_block_{order_index}"
