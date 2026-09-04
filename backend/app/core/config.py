"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI-SCRIBE"
    debug: bool = True
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai-scribe"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    hf_token: str = ""
    upload_dir: str = "uploads"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    secret_key: str = "change-me"
    max_upload_bytes: int = 500 * 1024 * 1024  # 500 MB
    whisper_model: str = "turbo"
    whisper_language: str = "tr"
    whisper_bin: str = ""
    whisperx_bin: str = ""
    whisperx_model: str = "large-v3"
    whisperx_batch_size: int = 4
    ffmpeg_bin: str = ""
    frontend_url: str = "http://localhost:3000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True


settings = Settings()
