from pathlib import Path
from uuid import uuid4

from app.core.config import settings

ALLOWED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a"}
AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


class StorageError(ValueError):
    pass


def _upload_root() -> Path:
    root = Path(settings.upload_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_audio(user_id: int, filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise StorageError("Sadece MP3, WAV veya M4A yükleyebilirsiniz")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise StorageError(f"Dosya {limit_mb} MB sınırını aşıyor")

    dest_dir = _upload_root() / str(user_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = dest_dir / f"{uuid4().hex}{suffix}"
    stored.write_bytes(data)
    return f"{user_id}/{stored.name}"


def absolute_audio_path(audio_path: str) -> Path:
    path = Path(audio_path)
    if not path.is_absolute():
        path = _upload_root() / audio_path
    return path


def delete_audio(audio_path: str | None) -> None:
    if not audio_path:
        return
    path = absolute_audio_path(audio_path)
    if path.is_file():
        path.unlink()
