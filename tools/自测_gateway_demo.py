from __future__ import annotations

import json
import runpy
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
BUILD_SCRIPT = ROOT / "tools" / "构建知识切片.py"

sys.path.insert(0, str(GATEWAY_DIR))

from app.main import GatewayHandler  # noqa: E402


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    api_key = _load_api_key()
    if api_key:
        headers["x-api-key"] = api_key
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_api_key() -> str:
    env_file = ROOT / "gateway" / ".env"
    env_key = os.getenv("RAG_KEFU_GATEWAY_API_KEY", "").strip() or os.getenv("GATEWAY_API_KEY", "").strip()
    if env_key:
        return env_key
    if not env_file.exists():
        return ""
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in {"RAG_KEFU_GATEWAY_API_KEY", "GATEWAY_API_KEY"}:
            return value.strip()
    return ""


def main() -> None:
    runpy.run_path(str(BUILD_SCRIPT), run_name="__main__")

    server = ThreadingHTTPServer(("127.0.0.1", 9000), GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(1)

    try:
        health = get_json("http://127.0.0.1:9000/health")
        answer = post_json(
            "http://127.0.0.1:9000/gateway/query",
            {
                "session_id": "demo-001",
                "question": "最小起订量是多少？",
                "history": [],
                "top_k": 3,
            },
        )
        risk = post_json(
            "http://127.0.0.1:9000/gateway/query",
            {
                "session_id": "demo-002",
                "question": "赔付金额怎么算？",
                "history": [],
                "top_k": 3,
            },
        )

        print("健康检查：")
        print(json.dumps(health, ensure_ascii=False, indent=2))
        print()
        print("普通问答：")
        print(json.dumps(answer, ensure_ascii=False, indent=2))
        print()
        print("高风险转人工：")
        print(json.dumps(risk, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
