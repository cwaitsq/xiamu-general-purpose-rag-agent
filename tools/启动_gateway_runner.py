from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = ROOT.parent / "factory_n8n"
RUNNER_SCRIPT = FACTORY_ROOT / "tools" / "gateway-runner.py"
ROOT_ENV_FILE = ROOT / ".env"
GATEWAY_ENV_FILE = ROOT / "gateway" / ".env"


def _load_gateway_env() -> None:
    for env_file in (ROOT_ENV_FILE, GATEWAY_ENV_FILE):
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                os.environ.setdefault(key, value.strip())


def main() -> int:
    if not RUNNER_SCRIPT.exists():
        print(f"未找到 gateway-runner：{RUNNER_SCRIPT}")
        return 1

    _load_gateway_env()
    host = os.getenv("GATEWAY_RUNNER_HOST", "0.0.0.0")
    port = os.getenv("GATEWAY_RUNNER_PORT", "8765")
    command = [
        sys.executable,
        str(RUNNER_SCRIPT),
        "--repo-root",
        str(ROOT),
        "serve",
        "--host",
        host,
        "--port",
        port,
    ]
    print(f"Gateway Runner 启动中：http://{host}:{port}")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
