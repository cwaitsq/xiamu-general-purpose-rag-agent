from __future__ import annotations

import json
import urllib.request
import sys
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def call(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


if __name__ == "__main__":
    session_id = f"backend-selftest-{uuid4().hex[:8]}"
    result = call(
        "http://127.0.0.1:8877/api/chat/send",
        {
            "tenant_id": "foreign_trade_demo",
            "session_id": session_id,
            "question": "最小起订量是多少？",
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
