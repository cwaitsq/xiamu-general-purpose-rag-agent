from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BackendSettings:
    app_host: str
    app_port: int
    gateway_base_url: str
    gateway_api_key: str
    auth_secret: str
    auth_token_ttl_hours: int
    bootstrap_admin_email: str
    bootstrap_admin_password: str
    bootstrap_admin_name: str
    upload_dir: str
    db_driver: str
    db_path: str
    database_url: str
    default_tenant_id: str
    default_publish_status: str
    default_refresh_index: bool
    app_log_dir: str
    request_body_max_bytes: int
    upload_max_bytes: int
    rate_limit_per_minute: int


def load_settings() -> BackendSettings:
    _load_env_file()
    db_driver = os.getenv("BACKEND_DB_DRIVER", "sqlite").strip().lower() or "sqlite"
    return BackendSettings(
        app_host=os.getenv("BACKEND_HOST", "0.0.0.0").strip() or "0.0.0.0",
        app_port=int(os.getenv("BACKEND_PORT", "8877")),
        gateway_base_url=(
            os.getenv("BACKEND_GATEWAY_BASE_URL", "http://127.0.0.1:8765/gateways/rag_kefu_gateway").rstrip("/")
        ),
        gateway_api_key=(
            os.getenv("RAG_KEFU_GATEWAY_API_KEY", "").strip()
            or os.getenv("GATEWAY_API_KEY", "").strip()
        ),
        auth_secret=os.getenv("BACKEND_AUTH_SECRET", "dev-only-change-me").strip() or "dev-only-change-me",
        auth_token_ttl_hours=int(os.getenv("BACKEND_AUTH_TOKEN_TTL_HOURS", "72")),
        bootstrap_admin_email=(
            os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@foreigntrade.local").strip()
            or "admin@foreigntrade.local"
        ),
        bootstrap_admin_password=(
            os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "Admin@123456").strip()
            or "Admin@123456"
        ),
        bootstrap_admin_name=(
            os.getenv("BOOTSTRAP_ADMIN_NAME", "系统管理员").strip()
            or "系统管理员"
        ),
        upload_dir=(
            os.getenv("BACKEND_UPLOAD_DIR", str(ROOT / "tenant_kb")).strip()
            or str(ROOT / "tenant_kb")
        ),
        db_driver=db_driver,
        db_path=(
            os.getenv("BACKEND_DB_PATH", str(ROOT / "backend_service" / "data" / "app.db")).strip()
            or str(ROOT / "backend_service" / "data" / "app.db")
        ),
        database_url=os.getenv("BACKEND_DATABASE_URL", "").strip(),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "foreign_trade_demo").strip() or "foreign_trade_demo",
        default_publish_status=os.getenv("DEFAULT_PUBLISH_STATUS", "active").strip() or "active",
        default_refresh_index=_env_bool("DEFAULT_REFRESH_INDEX", True),
        app_log_dir=(
            os.getenv("BACKEND_LOG_DIR", str(ROOT / "backend_service" / "logs")).strip()
            or str(ROOT / "backend_service" / "logs")
        ),
        request_body_max_bytes=int(os.getenv("BACKEND_REQUEST_BODY_MAX_BYTES", "65536")),
        upload_max_bytes=int(os.getenv("BACKEND_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024))),
        rate_limit_per_minute=int(os.getenv("BACKEND_RATE_LIMIT_PER_MINUTE", "120")),
    )
