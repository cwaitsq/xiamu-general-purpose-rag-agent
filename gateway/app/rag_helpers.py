from __future__ import annotations

import hashlib
from typing import Any


def point_id_for_chunk_id(chunk_id: str) -> int:
    digest = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def chunk_text_for_embedding(title: str, section_title: str, text: str) -> str:
    return f"标题：{title}\n小节：{section_title}\n内容：{text}".strip()


def chunk_payload_to_text(payload: dict[str, Any]) -> str:
    return chunk_text_for_embedding(
        str(payload.get("title", "")),
        str(payload.get("section_title", "")),
        str(payload.get("text", "")),
    )
