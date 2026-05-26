from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


ROOT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
GATEWAY_ENV_FILE = Path(__file__).resolve().parents[1] / "gateway" / ".env"


def _load_api_key() -> str:
    env_key = os.getenv("RAG_KEFU_GATEWAY_API_KEY", "").strip() or os.getenv("GATEWAY_API_KEY", "").strip()
    if env_key:
        return env_key
    for env_file in (ROOT_ENV_FILE, GATEWAY_ENV_FILE):
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"RAG_KEFU_GATEWAY_API_KEY", "GATEWAY_API_KEY"}:
                return value.strip()
    return ""


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    api_key = _load_api_key()
    if api_key:
        headers["x-api-key"] = api_key
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    base_url = os.getenv("GATEWAY_RUNNER_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
    health = get_json(f"{base_url}/gateways/rag_kefu_gateway/health")
    answer = post_json(
        f"{base_url}/gateways/rag_kefu_gateway/query",
        {
            "tenant_id": "foreign_trade_demo",
            "session_id": "demo-001",
            "question": "最小起订量是多少？",
            "history": [],
            "top_k": 3,
        },
    )

    print("健康检查：")
    print(json.dumps(health, ensure_ascii=False, indent=2))
    print()
    print("问答结果：")
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
