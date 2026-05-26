from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import load_settings
from .rag_clients import QmdClient
from .schemas import QueryRequest
from .service import handle_query, load_chunks
from .tenant_paths import DEFAULT_TENANT_ID


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "RAGGatewayDemo/0.1.0"

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        settings = load_settings()
        qmd_client = QmdClient(settings)
        self.send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "chunks_loaded": len(load_chunks(DEFAULT_TENANT_ID, settings=settings)),
                "gateway_mode": settings.gateway_mode,
                "retrieval_backend": "qmd" if settings.gateway_mode == "qmd" else "demo",
                "rag_enabled": settings.rag_enabled,
                "llm_enabled": settings.llm_enabled,
                "llm_ready": bool(settings.llm_enabled and settings.llm_api_key and settings.llm_model),
                "llm_model": settings.llm_model if settings.llm_enabled else None,
                "qmd_collection": settings.qmd_collection,
                "qmd_ready": qmd_client.collection_exists() if settings.gateway_mode == "qmd" else False,
                "media_preprocess_enabled": settings.media_preprocess_enabled,
                "multimodal_ready": settings.multimodal_enabled,
                "image_ocr_model": settings.image_ocr_model if settings.media_preprocess_enabled else None,
                "audio_asr_model": settings.audio_asr_model if settings.media_preprocess_enabled else None,
                "video_understand_model": settings.video_understand_model if settings.media_preprocess_enabled else None,
            },
        )

    def do_POST(self) -> None:
        if self.path != "/gateway/query":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        settings = load_settings()
        if settings.gateway_api_key:
            request_api_key = self.headers.get("x-api-key", "")
            if request_api_key != settings.gateway_api_key:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
            request = QueryRequest.from_dict(payload)
            response = handle_query(request)
            self.send_json(HTTPStatus.OK, response.to_dict())
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - demo fallback
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error", "detail": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "9000"))
    server = ThreadingHTTPServer((host, port), GatewayHandler)
    print(f"Gateway listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
