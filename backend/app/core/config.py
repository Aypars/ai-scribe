"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI-SCRIBE"
    debug: bool = True
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai-scribe"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    hf_token: str = ""
    upload_dir: str = "uploads"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    secret_key: str = "change-me"
    max_upload_bytes: int = 500 * 1024 * 1024  # 500 MB
    whisper_model: str = "turbo"
    whisper_language: str = "tr"
    whisper_bin: str = ""
    whisperx_bin: str = ""
    whisperx_model: str = "large-v2"
    whisperx_batch_size: int = 4
    ffmpeg_bin: str = ""


settings = Settings()
