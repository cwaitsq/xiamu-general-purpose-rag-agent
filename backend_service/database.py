from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import BackendSettings

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    dict_row = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  owner_user_id TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_attachments (
  id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  owner_user_id TEXT,
  session_id TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  mime_type TEXT,
  file_size INTEGER NOT NULL DEFAULT 0,
  preview_text TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_docs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  version TEXT,
  visibility TEXT NOT NULL,
  source_path TEXT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  file_name TEXT,
  file_path TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  result_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_logs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  owner_user_id TEXT,
  session_id TEXT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  status TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  handoff_required INTEGER NOT NULL DEFAULT 0,
  confidence TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handoff_logs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  owner_user_id TEXT,
  session_id TEXT NOT NULL,
  question TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions (tenant_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_message_attachments_session ON message_attachments (tenant_id, owner_user_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_message_attachments_message ON message_attachments (message_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_tenant ON knowledge_docs (tenant_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_tenant ON ingestion_jobs (tenant_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_qa_logs_tenant ON qa_logs (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_handoff_logs_tenant ON handoff_logs (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id, role, status, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_email ON users (tenant_id, email);
"""


class CursorWrapper:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def fetchone(self) -> dict[str, Any] | None:
        row = self.cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.cursor.fetchall()]


class DBConnection:
    def __init__(self, raw_conn: Any, *, driver: str) -> None:
        self.raw_conn = raw_conn
        self.driver = driver

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> CursorWrapper:
        cursor = self.raw_conn.cursor()
        cursor.execute(_adapt_query(sql, self.driver), tuple(params))
        return CursorWrapper(cursor)

    def commit(self) -> None:
        self.raw_conn.commit()

    def close(self) -> None:
        self.raw_conn.close()


def _adapt_query(sql: str, driver: str) -> str:
    if driver == "postgres":
        return sql.replace("?", "%s")
    return sql


def init_db(settings: BackendSettings) -> None:
    conn = connect(settings)
    for statement in [item.strip() for item in SCHEMA_SQL.split(";") if item.strip()]:
        conn.execute(statement)
    migrate_db(conn)
    conn.commit()
    conn.close()


def migrate_db(conn: DBConnection) -> None:
    _ensure_column(conn, "sessions", "owner_user_id", "TEXT")
    _ensure_column(conn, "qa_logs", "owner_user_id", "TEXT")
    _ensure_column(conn, "handoff_logs", "owner_user_id", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions (tenant_id, owner_user_id, updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_logs_owner ON qa_logs (tenant_id, owner_user_id, created_at)")


def _ensure_column(conn: DBConnection, table: str, column: str, definition: str) -> None:
    if _column_exists(conn, table, column):
        return
    if conn.driver == "postgres":
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _column_exists(conn: DBConnection, table: str, column: str) -> bool:
    if conn.driver == "postgres":
        row = conn.execute(
            """
            SELECT 1 AS present
            FROM information_schema.columns
            WHERE table_name=? AND column_name=?
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        return row is not None

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row.get("name") or "") == column for row in rows)


def connect(settings: BackendSettings) -> DBConnection:
    if settings.db_driver == "postgres":
        if psycopg is None:
            raise RuntimeError("当前环境未安装 psycopg，无法连接 PostgreSQL")
        if not settings.database_url:
            raise RuntimeError("未配置 BACKEND_DATABASE_URL，无法连接 PostgreSQL")
        raw_conn = psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=False)
        return DBConnection(raw_conn, driver="postgres")

    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    raw_conn = sqlite3.connect(db_path, check_same_thread=False)
    raw_conn.row_factory = sqlite3.Row
    return DBConnection(raw_conn, driver="sqlite")


def decode_result_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
