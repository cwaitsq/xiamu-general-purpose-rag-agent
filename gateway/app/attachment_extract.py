from __future__ import annotations

import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Settings, load_settings
from .knowledge_prepare import (
    AUDIO_SUFFIXES,
    IMAGE_SUFFIXES,
    SUPPORTED_SUFFIXES,
    VIDEO_SUFFIXES,
    normalize_text,
    read_raw_text,
    read_text_with_fallback,
    try_preprocess_unsupported_path,
    try_read_with_media_preprocess,
)


TEXT_MIME_TYPES = {
    "application/csv",
    "application/json",
    "application/ld+json",
    "application/xml",
}


@dataclass
class AttachmentExtractResult:
    source_file: str
    media_type: str
    text: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def extract_attachment_text(
    file_path: str,
    *,
    mime_type: str | None = None,
    settings: Settings | None = None,
) -> AttachmentExtractResult:
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"attachment file does not exist: {file_path}")

    active_settings = settings or load_settings()
    normalized_mime_type = (mime_type or "").strip().lower()
    warnings: list[str] = []
    errors: list[str] = []
    suffix = path.suffix.lower()

    try:
        if suffix in SUPPORTED_SUFFIXES:
            text = read_raw_text(path)
            media_type = classify_media_type(suffix=suffix, mime_type=normalized_mime_type)
        elif is_text_mime_type(normalized_mime_type):
            text = read_text_with_fallback(path)
            media_type = "text"
        else:
            text = try_preprocess_unsupported_path(path, settings=active_settings, warnings=warnings, errors=errors)
            media_type = classify_media_type(suffix=suffix, mime_type=normalized_mime_type)
    except (KeyError, OSError, UnicodeDecodeError, ValueError, zipfile.BadZipFile) as exc:
        if suffix == ".pdf":
            text = try_read_with_media_preprocess(path, settings=active_settings, warnings=warnings, errors=errors)
            media_type = "pdf_scan" if text else "pdf"
        else:
            raise ValueError(f"failed to extract attachment text from {path.name}: {exc}") from exc

    cleaned = normalize_text(text)
    if not cleaned:
        if errors:
            raise ValueError("; ".join(errors))
        raise ValueError(f"no readable text extracted from {path.name}")

    return AttachmentExtractResult(
        source_file=path.name,
        media_type=media_type,
        text=cleaned,
        warnings=warnings,
    )


def classify_media_type(*, suffix: str, mime_type: str) -> str:
    if suffix in IMAGE_SUFFIXES or mime_type.startswith("image/"):
        return "image"
    if suffix in AUDIO_SUFFIXES or mime_type.startswith("audio/"):
        return "audio"
    if suffix in VIDEO_SUFFIXES or mime_type.startswith("video/"):
        return "video"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".txt", ".md"} or is_text_mime_type(mime_type):
        return "text"
    return "document"


def is_text_mime_type(mime_type: str) -> bool:
    return mime_type.startswith("text/") or mime_type in TEXT_MIME_TYPES
