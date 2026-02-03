"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field, field_validator
import math


class RedactionRectangle(BaseModel):
    """A rectangle to redact on a specific page."""

    page_index: int = Field(ge=0, description="0-indexed page number")
    bbox: list[float] = Field(
        min_length=4, max_length=4, description="Bounding box [x0, y0, x1, y1] in PDF points (bottom-left origin)"
    )

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float]) -> list[float]:
        """Validate bbox coordinates."""
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 elements")
        
        x0, y0, x1, y1 = v
        
        # Check for non-finite values
        if not all(math.isfinite(coord) for coord in v):
            raise ValueError("bbox coordinates must be finite numbers")
        
        # Check for extremely large values (likely errors)
        MAX_COORD = 1e6  # 1 million points is extremely large for a PDF
        if any(abs(coord) > MAX_COORD for coord in v):
            raise ValueError(f"bbox coordinates exceed maximum allowed value ({MAX_COORD})")
        
        # Validate rectangle bounds
        if x0 >= x1:
            raise ValueError("x0 must be less than x1")
        if y0 >= y1:
            raise ValueError("y0 must be less than y1")
        
        return v


class RedactPdfRequest(BaseModel):
    """Request to redact a PDF."""

    pdf_data: str = Field(description="Base64-encoded PDF bytes")
    redaction_rectangles: list[RedactionRectangle] = Field(
        description="List of rectangles to redact", min_length=0
    )


class RedactPdfResponse(BaseModel):
    """Response containing redacted PDF."""

    redacted_pdf: str = Field(description="Base64-encoded redacted PDF bytes")
    stats: dict = Field(description="Redaction statistics")
