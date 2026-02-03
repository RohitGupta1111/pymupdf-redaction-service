"""PDF redaction engine using PyMuPDF."""

import logging
import fitz  # PyMuPDF
from app.schemas import RedactionRectangle
from app.config import settings

logger = logging.getLogger(__name__)


def redact_pdf_bytes(
    pdf_bytes: bytes,
    rectangles: list[RedactionRectangle],
    max_pages: int
) -> tuple[bytes, dict]:
    """
    Apply redactions to a PDF.
    
    Args:
        pdf_bytes: Raw PDF bytes
        rectangles: List of redaction rectangles
        max_pages: Maximum allowed pages
        
    Returns:
        Tuple of (redacted_pdf_bytes, stats_dict)
        
    Raises:
        ValueError: If PDF is invalid or exceeds limits
    """
    # Open PDF from bytes
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise ValueError(f"Invalid PDF: {str(e)}")
    
    try:
        page_count = len(doc)
        
        # Check page count limit
        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages, exceeds maximum of {max_pages}")
        
        # Group rectangles by page index
        rectangles_by_page: dict[int, list[RedactionRectangle]] = {}
        for rect in rectangles:
            page_idx = rect.page_index
            if page_idx not in rectangles_by_page:
                rectangles_by_page[page_idx] = []
            rectangles_by_page[page_idx].append(rect)
        
        rectangles_requested = len(rectangles)
        rectangles_applied = 0
        rectangles_skipped_out_of_bounds = 0
        
        # Process each page
        for page_index in range(page_count):
            if page_index not in rectangles_by_page:
                continue
            
            page = doc[page_index]
            page_rect = page.rect  # Page boundaries
            
            # Process each rectangle for this page
            for rect_spec in rectangles_by_page[page_index]:
                x0, y0, x1, y1 = rect_spec.bbox
                
                # Note: PyMuPDF uses top-left origin, but input is bottom-left
                # Convert from bottom-left to top-left origin
                page_height = page_rect.height
                y0_top = page_height - y1  # Convert bottom y1 to top y0
                y1_top = page_height - y0  # Convert bottom y0 to top y1
                
                # Clamp to page bounds
                clamped_x0 = max(0, min(x0, page_rect.width))
                clamped_y0 = max(0, min(y0_top, page_height))
                clamped_x1 = max(0, min(x1, page_rect.width))
                clamped_y1 = max(0, min(y1_top, page_height))
                
                # Check if rectangle is valid after clamping
                if clamped_x0 >= clamped_x1 or clamped_y0 >= clamped_y1:
                    rectangles_skipped_out_of_bounds += 1
                    logger.warning(
                        f"Page {page_index}: Rectangle [{x0}, {y0}, {x1}, {y1}] "
                        f"is out of bounds or invalid after clamping"
                    )
                    continue
                
                # Create redaction annotation
                # fill=(1,1,1) is white RGB
                try:
                    redact_rect = fitz.Rect(clamped_x0, clamped_y0, clamped_x1, clamped_y1)
                    page.add_redact_annot(redact_rect, fill=(1, 1, 1))
                    rectangles_applied += 1
                except Exception as e:
                    logger.warning(
                        f"Page {page_index}: Failed to add redaction annotation "
                        f"for [{x0}, {y0}, {x1}, {y1}]: {e}"
                    )
                    rectangles_skipped_out_of_bounds += 1
            
            # Apply all redactions for this page
            try:
                page.apply_redactions()
            except Exception as e:
                logger.warning(f"Page {page_index}: Failed to apply redactions: {e}")
        
        # Save to bytes
        output_bytes = doc.tobytes(garbage=4, deflate=True)
        
        stats = {
            "pages": page_count,
            "rectangles_requested": rectangles_requested,
            "rectangles_applied": rectangles_applied,
            "rectangles_skipped_out_of_bounds": rectangles_skipped_out_of_bounds
        }
        
        logger.info(
            f"Redaction complete: {rectangles_applied}/{rectangles_requested} "
            f"rectangles applied on {page_count} pages"
        )
        
        return output_bytes, stats
        
    finally:
        doc.close()
