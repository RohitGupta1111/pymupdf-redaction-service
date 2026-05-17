"""PDF fixtures for extraction tests."""

from __future__ import annotations

import fitz


def simple_pdf(text: str = "Hello extraction world.") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def multi_page_pdf(pages_text: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def multi_column_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Left column
    for i in range(5):
        page.insert_text((72, 72 + i * 24), f"Left column line {i + 1}", fontsize=11)
    # Right column (large x gap)
    for i in range(5):
        page.insert_text((340, 72 + i * 24), f"Right column line {i + 1}", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def table_like_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Course          Fee          Duration", fontsize=11)
    page.insert_text((72, 96), "Python 101      $500         6 weeks", fontsize=11)
    page.insert_text((72, 120), "Data Science    $800         10 weeks", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def repeated_footer_pdf(page_count: int = 5) -> bytes:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Main content for page {i + 1}", fontsize=12)
        page.insert_text((72, 750), "ACME Corp Confidential", fontsize=9)
        page.insert_text((500, 750), str(i + 1), fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def empty_page_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 72), "Only page two has text.", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def paragraph_lines_pdf() -> bytes:
    """Multiple lines that should coalesce into one paragraph."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    lines = [
        "Senior Frontend Engineer with 7+ years",
        "high-performance web apps and tools.",
        "design, feature delivery, and mentoring.",
    ]
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 16
    data = doc.tobytes()
    doc.close()
    return data


def heading_and_body_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "EXPERIENCE", fontsize=14)
    page.insert_text((72, 100), "First line of job description.", fontsize=11)
    page.insert_text((72, 116), "Second line continues here.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def bullet_continuation_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "- Led migration to React", fontsize=11)
    page.insert_text((72, 88), "across three product teams.", fontsize=11)
    page.insert_text((72, 112), "- Improved CI pipeline", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def resume_two_column_pdf() -> bytes:
    """Resume-style: left main column, right sidebar — left must read fully first."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Left column (main) — lower sections have higher y
    page.insert_text((72, 72), "SUMMARY", fontsize=14)
    page.insert_text((72, 96), "Senior engineer summary line.", fontsize=11)
    page.insert_text((72, 200), "EXPERIENCE", fontsize=14)
    page.insert_text((72, 224), "Company A - Developer role.", fontsize=11)
    # Right column (sidebar) — starts at same y as SUMMARY
    page.insert_text((340, 72), "EDUCATION", fontsize=14)
    page.insert_text((340, 96), "BS Computer Science", fontsize=11)
    page.insert_text((340, 120), "SKILLS", fontsize=14)
    page.insert_text((340, 144), "Python, JavaScript", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def encrypted_pdf(user_pass: str = "secret") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret content", fontsize=12)
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=user_pass,
        owner_pw=user_pass,
    )
    doc.close()
    return data
