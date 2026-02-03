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

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
