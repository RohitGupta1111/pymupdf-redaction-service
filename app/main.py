"""FastAPI application for PDF redaction service."""

import base64
import logging
import time
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import RedactPdfRequest, RedactPdfResponse
from app.security import require_api_key
from app.redactor import redact_pdf_bytes
from app.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PyMuPDF PDF Redaction Service",
    description="Microservice for applying true redactions to PDFs using PyMuPDF",
    version="1.0.0"
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/redact", response_model=RedactPdfResponse)
async def redact_pdf(
    request: RedactPdfRequest,
    _: None = Depends(require_api_key)
):
    """
    Redact PDF with specified rectangles.
    
    Requires X-Redaction-Key header for authentication.
    """
    start_time = time.time()
    
    try:
        # Decode base64 PDF
        try:
            pdf_bytes = base64.b64decode(request.pdf_data)
        except Exception as e:
            logger.error(f"Failed to decode base64 PDF: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 PDF data: {str(e)}"
            )
        
        # Validate PDF size
        pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
        if pdf_size_mb > settings.MAX_PDF_MB:
            raise HTTPException(
                status_code=400,
                detail=f"PDF size ({pdf_size_mb:.2f} MB) exceeds maximum ({settings.MAX_PDF_MB} MB)"
            )
        
        logger.info(
            f"Processing redaction request: {len(request.redaction_rectangles)} "
            f"rectangles, PDF size: {pdf_size_mb:.2f} MB"
        )
        
        # Apply redactions
        try:
            redacted_bytes, stats = redact_pdf_bytes(
                pdf_bytes,
                request.redaction_rectangles,
                settings.MAX_PAGES
            )
        except ValueError as e:
            logger.error(f"Redaction failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error during redaction: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Internal error during redaction: {str(e)}"
            )
        
        # Encode result
        redacted_base64 = base64.b64encode(redacted_bytes).decode("utf-8")
        
        elapsed_time = time.time() - start_time
        logger.info(f"Redaction completed in {elapsed_time:.2f}s")
        
        return RedactPdfResponse(
            redacted_pdf=redacted_base64,
            stats=stats
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
