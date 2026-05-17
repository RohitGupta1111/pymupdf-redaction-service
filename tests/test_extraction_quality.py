"""Focused tests for paragraph coalescing and column-aware reading order."""

from __future__ import annotations

import pytest

from app.extraction.coalescing import coalesce_paragraphs
from app.extraction.pipeline import run_extraction_pipeline
from app.extraction.reading_order import RawBlock, assign_reading_order, detect_column_layout
from app.extraction.schemas import BlockType, ExtractPdfOptions
from tests.extraction_fixtures import (
    bullet_continuation_pdf,
    heading_and_body_pdf,
    multi_column_pdf,
    paragraph_lines_pdf,
    resume_two_column_pdf,
    simple_pdf,
)


def _run(pdf_bytes: bytes, **kwargs):
    return run_extraction_pipeline(
        pdf_bytes,
        ExtractPdfOptions(**kwargs),
        max_pages=500,
    )


def test_paragraph_line_merging():
    doc = _run(paragraph_lines_pdf())
    blocks = doc.pages[0].blocks
    paragraphs = [b for b in blocks if b.type == BlockType.PARAGRAPH]
    assert len(paragraphs) <= 2, f"Expected coalesced paragraph(s), got {len(paragraphs)} blocks"
    merged = " ".join(b.text for b in paragraphs)
    assert "Senior Frontend Engineer" in merged
    assert "mentoring" in merged
    meta = doc.pages[0].layout_metadata.get("coalescing", {})
    assert meta.get("merge_count", 0) >= 2


def test_heading_not_merged_with_body():
    doc = _run(heading_and_body_pdf())
    types = [b.type for b in doc.pages[0].blocks]
    assert BlockType.HEADING in types
    headings = [b for b in doc.pages[0].blocks if b.type == BlockType.HEADING]
    assert headings[0].text.strip() == "EXPERIENCE"
    assert "First line" not in headings[0].text


def test_bullet_continuation_preserved():
    doc = _run(bullet_continuation_pdf())
    list_items = [b for b in doc.pages[0].blocks if b.type == BlockType.LIST_ITEM]
    assert len(list_items) >= 2
    first = list_items[0].text
    assert "Led migration" in first
    assert "product teams" in first


def test_resume_two_column_reading_order():
    doc = _run(resume_two_column_pdf())
    texts = [b.text for b in doc.pages[0].blocks]
    joined = " | ".join(texts)
    summary_idx = joined.find("SUMMARY")
    experience_idx = joined.find("EXPERIENCE")
    education_idx = joined.find("EDUCATION")
    skills_idx = joined.find("SKILLS")
    assert summary_idx != -1
    assert experience_idx != -1
    assert education_idx != -1
    assert skills_idx != -1
    # Left column fully before right column
    assert summary_idx < education_idx
    assert experience_idx < education_idx
    assert experience_idx < skills_idx
    layout = doc.pages[0].layout_metadata.get("column_layout", {})
    assert layout.get("likely_multi_column") is True
    assert layout.get("column_count") == 2


def test_single_column_regression():
    doc = _run(simple_pdf("Single column only text here."))
    assert len(doc.pages[0].blocks) >= 1
    layout = doc.pages[0].layout_metadata.get("column_layout", {})
    assert layout.get("likely_multi_column") is not True or layout.get("fallback_used") is True


def test_multi_column_fixture_still_ordered():
    doc = _run(multi_column_pdf())
    texts = [b.text for b in doc.pages[0].blocks]
    joined = " ".join(texts)
    assert joined.find("Left") < joined.find("Right")


def test_ambiguous_layout_fallback():
    """Sparse blocks with no clear column gap should not force multi-column."""
    blocks = [
        RawBlock(0, "A", (50, 50, 200, 70), 11, "paragraph"),
        RawBlock(1, "B", (55, 200, 210, 220), 11, "paragraph"),
        RawBlock(2, "C", (60, 400, 220, 420), 11, "paragraph"),
    ]
    layout = detect_column_layout(blocks, 612.0)
    assert layout.likely_multi_column is False
    ordered, likely_mc, layout2 = assign_reading_order(blocks, 612.0, 1)
    assert likely_mc is False
    assert [b.text for b in ordered] == ["A", "B", "C"]


def test_coalesce_unit_merge():
    blocks = [
        RawBlock(0, "Line one of paragraph.", (72, 72, 400, 88), 11, "paragraph"),
        RawBlock(1, "Line two continues.", (72, 90, 400, 106), 11, "paragraph"),
    ]
    merged, stats = coalesce_paragraphs(blocks, 792.0, 1)
    assert stats["merge_count"] == 1
    assert len(merged) == 1
    assert "Line one" in merged[0].text and "Line two" in merged[0].text


def test_coalesce_unit_no_merge_after_heading():
    blocks = [
        RawBlock(0, "SECTION", (72, 72, 200, 90), 14, "heading"),
        RawBlock(1, "Body text here.", (72, 100, 400, 116), 11, "paragraph"),
    ]
    merged, stats = coalesce_paragraphs(blocks, 792.0, 1)
    assert stats["merge_count"] == 0
    assert len(merged) == 2
