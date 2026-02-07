"""PDF redaction engine using PyMuPDF."""

import logging
import fitz  # PyMuPDF
from app.schemas import RedactionRectangle
from app.config import settings

logger = logging.getLogger(__name__)

TEXT_LOG_MAX_LEN = 80

# Sentinel strings used to verify redaction truly removes text (resume template placeholders)
SENTINEL_WRITE_MAIN = "Write your main highlighted accomplishments"
SENTINEL_THINK_ABOUT = "Think about how your task/project helped"
VERIFY_EXCERPT_LEN = 80


def _check_sentinels(text: str) -> tuple[bool, bool]:
    """Return (contains_write_main, contains_think_about) for full-page text."""
    return (
        SENTINEL_WRITE_MAIN in text,
        SENTINEL_THINK_ABOUT in text,
    )


def _excerpt_around(text: str, substring: str, max_len: int = VERIFY_EXCERPT_LEN) -> str:
    """Return a short excerpt around the first occurrence of substring."""
    idx = text.find(substring)
    if idx == -1:
        return ""
    start = max(0, idx - (max_len // 2))
    end = min(len(text), start + max_len)
    excerpt = text[start:end].replace("\n", " ").strip()
    if len(excerpt) > max_len:
        excerpt = excerpt[:max_len] + "..."
    return excerpt


def _text_in_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    """Extract text inside rect; return truncated string for logging."""
    try:
        s = page.get_text(clip=rect).strip().replace("\n", " ")
    except Exception:
        return ""
    if len(s) > TEXT_LOG_MAX_LEN:
        s = s[:TEXT_LOG_MAX_LEN] + "..."
    return s


def clamp_rect_to_page(
    page_rect: fitz.Rect, bbox: tuple[float, float, float, float]
) -> fitz.Rect | None:
    """
    Clamp a bbox to page bounds and return a valid rect, or None if area is invalid.

    Uses page_rect.x0, .y0, .x1, .y1 so CropBox offsets are respected.
    After clamping, if the resulting area is degenerate, returns None.
    """
    x0, y0, x1, y1 = bbox
    clamped_x0 = max(page_rect.x0, min(x0, page_rect.x1))
    clamped_y0 = max(page_rect.y0, min(y0, page_rect.y1))
    clamped_x1 = max(page_rect.x0, min(x1, page_rect.x1))
    clamped_y1 = max(page_rect.y0, min(y1, page_rect.y1))

    if clamped_x1 <= clamped_x0 or clamped_y1 <= clamped_y0:
        return None
    return fitz.Rect(clamped_x0, clamped_y0, clamped_x1, clamped_y1)


def _bbox_intersects_page(page_rect: fitz.Rect, bbox: tuple[float, float, float, float]) -> bool:
    """Return True if bbox has any overlap with page_rect."""
    x0, y0, x1, y1 = bbox
    if x1 <= page_rect.x0 or x0 >= page_rect.x1:
        return False
    if y1 <= page_rect.y0 or y0 >= page_rect.y1:
        return False
    return True


def redact_pdf_bytes(
    pdf_bytes: bytes,
    rectangles: list[RedactionRectangle],
    max_pages: int
) -> tuple[bytes, dict]:
    """
    Apply redactions to a PDF.

    Input bbox (x0, y0, x1, y1) is in PDF points with bottom-left origin,
    same coordinate system as PyMuPDF; no Y-axis conversion is applied.

    Args:
        pdf_bytes: Raw PDF bytes
        rectangles: List of redaction rectangles
        max_pages: Maximum allowed pages

    Returns:
        Tuple of (redacted_pdf_bytes, stats_dict)

    Raises:
        ValueError: If PDF is invalid or exceeds limits
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise ValueError(f"Invalid PDF: {str(e)}")

    try:
        page_count = len(doc)

        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages, exceeds maximum of {max_pages}")

        rectangles_by_page: dict[int, list[RedactionRectangle]] = {}
        for rect in rectangles:
            page_idx = rect.page_index
            if page_idx not in rectangles_by_page:
                rectangles_by_page[page_idx] = []
            rectangles_by_page[page_idx].append(rect)

        rectangles_requested = len(rectangles)
        rectangles_applied = 0
        rectangles_skipped_out_of_bounds = 0
        rectangles_skipped_invalid_area = 0

        for page_index in range(page_count):
            if page_index not in rectangles_by_page:
                continue

            page = doc[page_index]
            page_rect = page.rect
            H = page_rect.height

            logger.info(
                "[redactor] page_meta page=%s rect=%s (width=%s height=%s) rotation=%s mediabox=%s cropbox=%s",
                page_index,
                page_rect,
                page_rect.width,
                page_rect.height,
                getattr(page, "rotation", None),
                getattr(page, "mediabox", None),
                getattr(page, "cropbox", None),
            )

            # [verify] before redaction: check if sentinel strings are present
            try:
                page_text_before = page.get_text("text")
            except Exception:
                page_text_before = ""
            contains_write_main_before, contains_think_about_before = _check_sentinels(page_text_before)
            logger.info(
                "[verify] page=%s before_redaction contains_write_main=%s contains_think_about=%s",
                page_index,
                contains_write_main_before,
                contains_think_about_before,
            )

            for rect_spec in rectangles_by_page[page_index]:
                bbox = tuple(rect_spec.bbox)
                x0, y0, x1, y1 = bbox

                # Log orig rect and text in orig rect
                rect_orig = fitz.Rect(x0, y0, x1, y1)
                text_orig = _text_in_rect(page, rect_orig)
                logger.info(
                    '[redactor] rect_test page=%s orig=[%s,%s,%s,%s] text_orig="%s"',
                    page_index,
                    x0,
                    y0,
                    x1,
                    y1,
                    text_orig,
                )

                # Compute flipped rect (bottom-left -> top-left style) and log text
                rect_flip = fitz.Rect(x0, H - y1, x1, H - y0)
                text_flip = _text_in_rect(page, rect_flip)
                logger.info(
                    '[redactor] rect_test page=%s flip=[%s,%s,%s,%s] text_flip="%s"',
                    page_index,
                    x0,
                    H - y1,
                    x1,
                    H - y0,
                    text_flip,
                )

                if not _bbox_intersects_page(page_rect, bbox):
                    rectangles_skipped_out_of_bounds += 1
                    logger.warning(
                        f"Page {page_index}: Rectangle [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] "
                        "is out of bounds"
                    )
                    continue

                clamped_rect = clamp_rect_to_page(page_rect, bbox)
                if clamped_rect is None:
                    rectangles_skipped_invalid_area += 1
                    logger.warning(
                        f"Page {page_index}: Rectangle [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] "
                        "has invalid area after clamping"
                    )
                    continue

                try:
                    page.add_redact_annot(clamped_rect, fill=(1, 1, 1))
                    rectangles_applied += 1
                except Exception as e:
                    logger.warning(
                        f"Page {page_index}: Failed to add redaction annotation "
                        f"for [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]: {e}"
                    )
                    rectangles_skipped_out_of_bounds += 1

            try:
                page.apply_redactions()
            except Exception as e:
                logger.warning(f"Page {page_index}: Failed to apply redactions: {e}")

            # [verify] after apply_redactions (before save): check if sentinels are gone
            try:
                page_text_after = page.get_text("text")
            except Exception:
                page_text_after = ""
            contains_write_main_after, contains_think_about_after = _check_sentinels(page_text_after)
            logger.info(
                "[verify] page=%s after_apply_redactions contains_write_main=%s contains_think_about=%s",
                page_index,
                contains_write_main_after,
                contains_think_about_after,
            )
            if contains_write_main_after:
                excerpt = _excerpt_around(page_text_after, SENTINEL_WRITE_MAIN)
                logger.warning(
                    '[verify] WARNING page=%s still_contains="%s"',
                    page_index,
                    SENTINEL_WRITE_MAIN,
                )
                logger.warning('[verify] excerpt="%s"', excerpt)
            if contains_think_about_after:
                excerpt = _excerpt_around(page_text_after, SENTINEL_THINK_ABOUT)
                logger.warning(
                    '[verify] WARNING page=%s still_contains="%s"',
                    page_index,
                    SENTINEL_THINK_ABOUT,
                )
                logger.warning('[verify] excerpt="%s"', excerpt)

        output_bytes = doc.tobytes(garbage=4, deflate=True)

        # [verify] after save and reopen: ensure text not reintroduced by save structure
        try:
            doc2 = fitz.open(stream=output_bytes, filetype="pdf")
            try:
                for page_index in range(len(doc2)):
                    p = doc2[page_index]
                    try:
                        reopen_text = p.get_text("text")
                    except Exception:
                        reopen_text = ""
                    contains_write_main_reopen, contains_think_about_reopen = _check_sentinels(reopen_text)
                    logger.info(
                        "[verify] reopen page=%s contains_write_main=%s contains_think_about=%s",
                        page_index,
                        contains_write_main_reopen,
                        contains_think_about_reopen,
                    )
                    if contains_write_main_reopen:
                        excerpt = _excerpt_around(reopen_text, SENTINEL_WRITE_MAIN)
                        logger.warning(
                            '[verify] WARNING page=%s still_contains="%s"',
                            page_index,
                            SENTINEL_WRITE_MAIN,
                        )
                        logger.warning('[verify] excerpt="%s"', excerpt)
                    if contains_think_about_reopen:
                        excerpt = _excerpt_around(reopen_text, SENTINEL_THINK_ABOUT)
                        logger.warning(
                            '[verify] WARNING page=%s still_contains="%s"',
                            page_index,
                            SENTINEL_THINK_ABOUT,
                        )
                        logger.warning('[verify] excerpt="%s"', excerpt)
            finally:
                doc2.close()
        except Exception as e:
            logger.warning("[verify] Failed to reopen output PDF for verification: %s", e)

        stats = {
            "pages": page_count,
            "rectangles_requested": rectangles_requested,
            "rectangles_applied": rectangles_applied,
            "rectangles_skipped_out_of_bounds": rectangles_skipped_out_of_bounds,
            "rectangles_skipped_invalid_area": rectangles_skipped_invalid_area,
        }

        logger.info(
            f"Redaction complete: {rectangles_applied}/{rectangles_requested} "
            f"rectangles applied on {page_count} pages"
        )

        return output_bytes, stats

    finally:
        doc.close()
