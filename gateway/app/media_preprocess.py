from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .config import Settings

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
OCR_TEXT_PROMPT = (
    "请提取资料中的全部正文文字，只输出整理后的文字内容。"
    "不要解释，不要总结，不要补充原文没有的信息。"
    "如果是表格或聊天截图，请尽量保留原顺序。"
)
AUDIO_TEXT_PROMPT = (
    "请把音频完整转成简体中文文字稿。"
    "只输出正文，不要解释，不要补充。"
    "如果有英文专业词，可以保留原词。"
)
VIDEO_TEXT_PROMPT = (
    "请把视频里的语音内容、字幕内容、画面中能看清的文字整理成一份简体中文文字稿。"
    "先保留语音主内容，再补充画面文字。"
    "只输出正文，不要解释，不要补充原视频没有的信息。"
)


class MediaPreprocessError(RuntimeError):
    pass


@dataclass
class MediaPreprocessResult:
    source_file: str
    media_type: str
    text: str
    output_file: str
    warnings: list[str] = field(default_factory=list)


def preprocess_media_file(path: Path, settings: Settings) -> MediaPreprocessResult:
    if not settings.multimodal_enabled:
        raise MediaPreprocessError("未配置多模态服务，请先设置 DASHSCOPE_API_KEY 或 MULTIMODAL_API_KEY")
    if not path.exists():
        raise MediaPreprocessError(f"文件不存在：{path}")
    max_bytes = max(1, settings.media_max_file_bytes)
    if path.stat().st_size > max_bytes:
        raise MediaPreprocessError(f"{path.name} 超过大小限制，当前上限是 {max_bytes // (1024 * 1024)}MB")

    suffix = path.suffix.lower()
    warnings: list[str] = []
    if suffix in IMAGE_SUFFIXES:
        text = ocr_image_file(path, settings)
        media_type = "image"
    elif suffix in AUDIO_SUFFIXES:
        text = transcribe_audio_file(path, settings)
        media_type = "audio"
    elif suffix in VIDEO_SUFFIXES:
        text = transcribe_video_file(path, settings)
        media_type = "video"
        warnings.append("视频转写当前走多模态理解，长视频建议后续再接对象存储和异步任务")
    elif suffix == ".pdf":
        text = ocr_scanned_pdf(path, settings)
        media_type = "pdf_scan"
    else:
        raise MediaPreprocessError(f"当前不支持预处理该文件类型：{path.suffix}")

    cleaned = normalize_text(text)
    if not cleaned:
        raise MediaPreprocessError(f"{path.name} 预处理后没有拿到有效正文")
    output_file = write_preprocess_output(path, media_type, cleaned, settings)
    return MediaPreprocessResult(
        source_file=path.name,
        media_type=media_type,
        text=cleaned,
        output_file=output_file,
        warnings=warnings,
    )


def ocr_image_file(path: Path, settings: Settings) -> str:
    content = _completion_text(
        settings,
        model=settings.image_ocr_model,
        system_prompt="你是企业资料 OCR 助手，只能忠实提取图片文字。",
        user_content=[
            {"type": "text", "text": OCR_TEXT_PROMPT},
            {"type": "image_url", "image_url": {"url": file_to_data_url(path)}},
        ],
        stream=False,
    )
    return content


def transcribe_audio_file(path: Path, settings: Settings) -> str:
    suffix = path.suffix.lower().removeprefix(".") or "wav"
    content = _completion_text(
        settings,
        model=settings.audio_asr_model,
        system_prompt="你是企业资料语音转写助手，只能忠实输出音频文字稿。",
        user_content=[
            {"type": "text", "text": AUDIO_TEXT_PROMPT},
            {
                "type": "input_audio",
                "input_audio": {
                    "data": file_to_data_url(path),
                    "format": suffix,
                },
            },
        ],
        stream=False,
    )
    return content


def transcribe_video_file(path: Path, settings: Settings) -> str:
    return _completion_text(
        settings,
        model=settings.video_understand_model,
        system_prompt="你是企业资料视频转写助手，只能忠实整理视频中的语音和画面文字。",
        user_content=[
            {"type": "text", "text": VIDEO_TEXT_PROMPT},
            {"type": "video_url", "video_url": {"url": file_to_data_url(path)}},
        ],
        stream=True,
    )


def ocr_scanned_pdf(path: Path, settings: Settings) -> str:
    if PdfReader is None:
        raise MediaPreprocessError("当前环境没有安装 pypdf，不能处理扫描版 PDF")

    reader = PdfReader(str(path))
    page_texts: list[str] = []
    image_count = 0
    for page_index, page in enumerate(reader.pages, start=1):
        images = getattr(page, "images", None)
        if not images:
            continue
        page_parts: list[str] = []
        for image in images:
            image_bytes = getattr(image, "data", b"") or b""
            if not image_bytes:
                continue
            image_name = getattr(image, "name", f"page_{page_index}.png")
            mime_type = mimetype_from_name(image_name)
            text = _completion_text(
                settings,
                model=settings.image_ocr_model,
                system_prompt="你是企业资料 OCR 助手，只能忠实提取扫描件中的文字。",
                user_content=[
                    {"type": "text", "text": OCR_TEXT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": bytes_to_data_url(image_bytes, mime_type)},
                    },
                ],
                stream=False,
            )
            cleaned = normalize_text(text)
            if cleaned:
                page_parts.append(cleaned)
                image_count += 1
        if page_parts:
            page_texts.append(f"第 {page_index} 页\n" + "\n".join(page_parts))

    if not page_texts:
        raise MediaPreprocessError("扫描版 PDF 没提取到图片层，当前无法自动 OCR")
    if image_count > 8:
        page_texts.append("\n说明：扫描件页数较多，建议人工抽查关键页。")
    return "\n\n".join(page_texts)


def write_preprocess_output(path: Path, media_type: str, text: str, settings: Settings) -> str:
    output_dir = Path(settings.media_output_dir) / "自动转写"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_name(path.stem)
    output_path = output_dir / f"{safe_name}.{media_type}.txt"
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    return str(output_path)


def file_to_data_url(path: Path) -> str:
    mime_type = mimetype_from_name(path.name)
    return bytes_to_data_url(path.read_bytes(), mime_type)


def bytes_to_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def mimetype_from_name(name: str) -> str:
    mime_type, _encoding = mimetypes.guess_type(name)
    return mime_type or "application/octet-stream"


def _completion_text(
    settings: Settings,
    *,
    model: str,
    system_prompt: str,
    user_content: list[dict[str, Any]],
    stream: bool,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": stream,
    }
    if stream:
        return _stream_chat_completion(settings, payload)
    return _chat_completion(settings, payload)


def _chat_completion(settings: Settings, payload: dict[str, Any]) -> str:
    response = requests.post(
        f"{settings.multimodal_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.multimodal_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=settings.multimodal_timeout_seconds,
    )
    if response.status_code >= 400:
        raise MediaPreprocessError(f"多模态接口调用失败：HTTP {response.status_code} {response.text}")
    data = response.json()
    return extract_completion_text(data)


def _stream_chat_completion(settings: Settings, payload: dict[str, Any]) -> str:
    response = requests.post(
        f"{settings.multimodal_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.multimodal_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json=payload,
        timeout=settings.multimodal_timeout_seconds,
        stream=True,
    )
    if response.status_code >= 400:
        raise MediaPreprocessError(f"多模态流式接口调用失败：HTTP {response.status_code} {response.text}")

    texts: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if not data_str or data_str == "[DONE]":
            continue
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content", "")
            if isinstance(content, str) and content:
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = str(item.get("text", "")).strip()
                        if text:
                            texts.append(text)
    combined = "".join(texts).strip()
    if not combined:
        raise MediaPreprocessError("多模态流式接口没有返回有效正文")
    return combined


def extract_completion_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()
    return ""


def sanitize_name(name: str) -> str:
    sanitized = re.sub(r"[<>:\"/\\\\|?*]+", "_", name).strip(" .")
    return sanitized or "未命名资料"


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
