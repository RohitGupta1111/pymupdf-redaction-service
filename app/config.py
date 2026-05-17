"""Configuration settings using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    REDACTION_SERVICE_API_KEY: str
    MAX_PDF_MB: int = 10
    MAX_PAGES: int = 30
    REQUEST_TIMEOUT_SECONDS: int = 30
    LOG_LEVEL: str = "INFO"
    PORT: int = 8080
    ENABLE_DEBUG_REDACTION_LOGS: bool = False

    # Extraction subsystem (isolated from redaction limits)
    MAX_EXTRACT_PDF_MB: int = 50
    MAX_EXTRACT_PAGES: int = 500
    EXTRACT_FETCH_TIMEOUT_SECONDS: int = 60
    EXTRACT_PROCESS_TIMEOUT_SECONDS: int = 120
    ENABLE_DEBUG_EXTRACTION_LOGS: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
