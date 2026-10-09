from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str

    # ── JWT ───────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── Redis (optional — used by Celery if enabled) ──────────
    REDIS_URL: Optional[str] = None

    # ── Email / SMTP ──────────────────────────────────────────
    # Set EMAIL_ENABLED=true to actually send emails.
    # Leave false (default) in development — calls are logged instead.
    EMAIL_ENABLED: bool = False
    SMTP_HOST:     str  = "smtp.gmail.com"
    SMTP_PORT:     int  = 587
    SMTP_TLS:      bool = True
    SMTP_USER:     str  = ""
    SMTP_PASSWORD: str  = ""
    SMTP_FROM:     str  = "noreply@ahadubank.com"

    # ── Frontend URL (used in email links) ────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
