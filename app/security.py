"""Security utilities for API key authentication."""

from fastapi import Request, HTTPException
from app.config import settings


def require_api_key(request: Request) -> None:
    """
    Validate API key from X-Redaction-Key header.
    
    Raises HTTPException(401) if key is missing or invalid.
    """
    api_key = request.headers.get("X-Redaction-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Redaction-Key header"
        )
    
    if api_key != settings.REDACTION_SERVICE_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
