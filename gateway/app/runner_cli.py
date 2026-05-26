from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


GATEWAY_DIR = Path(__file__).resolve().parents[1]
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from app.attachment_extract import extract_attachment_text  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.knowledge_ingest import run_knowledge_ingest  # noqa: E402
from app.knowledge_prepare import run_knowledge_prepare  # noqa: E402
from app.rag_clients import QmdClient  # noqa: E402
from app.schemas import QueryRequest  # noqa: E402
from app.service import handle_query  # noqa: E402
from app.tenant_paths import DEFAULT_TENANT_ID, count_workspace_chunks  # noqa: E402


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return data


def run_query() -> int:
    try:
        payload = read_stdin_json()
        request = QueryRequest.from_dict(payload)
        response = handle_query(request)
        print(json.dumps(response.to_dict(), ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "answer": f"请求参数不对：{exc}",
                    "sources": [],
                    "confidence": "low",
                    "handoff_required": False,
                    "reason": "invalid_request",
                    "answer_mode": "rule",
                    "llm_model": None,
                    "retrieval_backend": None,
                    "used_llm": False,
                    "next_action": "rephrase",
                    "timings": {"retrieval_ms": 0, "answer_ms": 0, "total_ms": 0},
                },
                ensure_ascii=False,
            )
        )
        return 0


def run_health() -> int:
    settings = load_settings()
    qmd_client = QmdClient(settings)
    payload = {
        "status": "ok",
        "gateway_mode": settings.gateway_mode,
        "retrieval_backend": "qmd" if settings.gateway_mode == "qmd" else "demo",
        "rag_enabled": settings.rag_enabled,
        "llm_enabled": settings.llm_enabled,
        "llm_ready": bool(settings.llm_enabled and settings.llm_api_key and settings.llm_model),
        "llm_model": settings.llm_model if settings.llm_enabled else None,
        "qmd_collection": settings.qmd_collection,
        "qmd_ready": qmd_client.collection_exists() if settings.gateway_mode == "qmd" else False,
        "chunks_loaded": count_workspace_chunks(settings.qmd_collection),
        "media_preprocess_enabled": settings.media_preprocess_enabled,
        "multimodal_ready": settings.multimodal_enabled,
        "image_ocr_model": settings.image_ocr_model if settings.media_preprocess_enabled else None,
        "audio_asr_model": settings.audio_asr_model if settings.media_preprocess_enabled else None,
        "video_understand_model": settings.video_understand_model if settings.media_preprocess_enabled else None,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def run_ingest_rebuild() -> int:
    payload = read_stdin_json()
    result = run_knowledge_ingest(
        validate_only=bool(payload.get("validate_only", False)),
        refresh_index=bool(payload.get("refresh_index", True)),
        prepare_raw=bool(payload.get("prepare_raw", False)),
        publish_status=str(payload.get("publish_status", "draft")).strip() or "draft",
        prepare_use_llm=bool(payload.get("prepare_use_llm", False)),
        settings=load_settings(),
        tenant_id=str(payload.get("tenant_id", DEFAULT_TENANT_ID)).strip() or DEFAULT_TENANT_ID,
        target_file_path=(str(payload.get("target_file_path")).strip() if payload.get("target_file_path") else None),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0


def run_prepare_raw() -> int:
    payload = read_stdin_json()
    result = run_knowledge_prepare(
        validate_only=bool(payload.get("validate_only", False)),
        publish_status=str(payload.get("publish_status", "draft")).strip() or "draft",
        use_llm=bool(payload.get("use_llm", False)),
        settings=load_settings(),
        tenant_id=str(payload.get("tenant_id", DEFAULT_TENANT_ID)).strip() or DEFAULT_TENANT_ID,
        target_file_path=(str(payload.get("target_file_path")).strip() if payload.get("target_file_path") else None),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0


def run_extract_attachment() -> int:
    payload = read_stdin_json()
    file_path = str(payload.get("file_path") or "").strip()
    if not file_path:
        raise ValueError("file_path is required")
    result = extract_attachment_text(
        file_path,
        mime_type=(str(payload.get("mime_type")).strip() if payload.get("mime_type") else None),
        settings=load_settings(),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "query"
    if action == "query":
        return run_query()
    if action == "health":
        return run_health()
    if action == "prepare_raw":
        return run_prepare_raw()
    if action == "ingest_rebuild":
        return run_ingest_rebuild()
    if action == "extract_attachment":
        return run_extract_attachment()
    print(f"不支持的动作：{action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
