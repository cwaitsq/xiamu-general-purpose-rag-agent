from __future__ import annotations

import os
import runpy
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
BUILD_SCRIPT = ROOT / "tools" / "构建知识切片.py"

sys.path.insert(0, str(GATEWAY_DIR))

from app.main import GatewayHandler  # noqa: E402


def main() -> None:
    runpy.run_path(str(BUILD_SCRIPT), run_name="__main__")

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "9000"))

    server = ThreadingHTTPServer((host, port), GatewayHandler)
    print(f"Gateway Demo 已启动：http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
