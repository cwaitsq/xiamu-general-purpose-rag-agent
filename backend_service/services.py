from __future__ import annotations

import cgi
import json
import mimetypes
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from .config import ROOT, BackendSettings
from .database import DBConnection, decode_result_json


SECRET_PATTERNS = [re.compile(r"sk-[A-Za-z0-9]{12,}")]
TEXT_ATTACHMENT_SUFFIXES = {
    ".csv",
    ".json",
    ".log",
    ".md",
    ".markdown",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
ATTACHMENT_PREVIEW_LIMIT = 1600
ATTACHMENT_EXTRACTION_LIMIT = 6000


def redact_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_KEY]", redacted)
    return redacted


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def sanitize_tenant_id(tenant_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", tenant_id.strip())
    return cleaned[:64].strip("_") or "default"


def sanitize_file_name(name: str) -> str:
    return "".join(char if char not in '<>:"/\\|?*' else "_" for char in name).strip() or "unnamed.bin"


def build_attachment_preview(file_name: str, content: bytes, mime_type: str | None = None) -> str | None:
    suffix = Path(file_name).suffix.lower()
    detected_type = (mime_type or mimetypes.guess_type(file_name)[0] or "").lower()
    is_text_like = detected_type.startswith("text/") or detected_type in {
        "application/json",
        "application/xml",
    } or suffix in TEXT_ATTACHMENT_SUFFIXES
    if not is_text_like:
        return None

    text = content.decode("utf-8", errors="ignore").replace("\r\n", "\n").strip()
    if not text:
        return None
    return normalize_attachment_text(text, limit=ATTACHMENT_PREVIEW_LIMIT)


def normalize_attachment_text(text: str | None, *, limit: int) -> str | None:
    if text is None:
        return None
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return None
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized[:limit]


def summarize_runner_error(detail: str | None) -> str | None:
    if detail is None:
        return None
    lines = [line.strip() for line in detail.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return None
    summary = re.sub(r"^[A-Za-z_][A-Za-z0-9_.]*:\s*", "", lines[-1]).strip()
    return summary[:600] if summary else None


def extract_attachment_preview(
    settings: BackendSettings,
    *,
    tenant_id: str,
    file_path: str,
    file_name: str,
    content: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    fallback_preview = build_attachment_preview(file_name, content, mime_type)
    payload = {
        "tenant_id": tenant_id,
        "file_path": file_path,
        "file_name": file_name,
        "mime_type": mime_type,
    }

    try:
        result = invoke_gateway_runner("extract_attachment", payload)
    except RuntimeError as exc:
        warning = summarize_runner_error(str(exc))
        warnings = [warning] if warning else []
        return {
            "preview_text": fallback_preview,
            "media_type": None,
            "warnings": warnings,
            "used_gateway": False,
        }

    extracted_text = normalize_attachment_text(str(result.get("text") or ""), limit=ATTACHMENT_EXTRACTION_LIMIT)
    preview_text = extracted_text or fallback_preview
    warnings = [str(item).strip() for item in list(result.get("warnings") or []) if str(item).strip()]
    return {
        "preview_text": preview_text,
        "media_type": str(result.get("media_type") or "").strip() or None,
        "warnings": warnings,
        "used_gateway": bool(extracted_text),
    }


def normalize_email(email: str) -> str:
    return email.strip().lower()


def build_scoped_id(tenant_id: str, public_id: str) -> str:
    return f"{tenant_id}::{public_id}"


def extract_public_id(scoped_id: str, tenant_id: str | None = None) -> str:
    if "::" not in scoped_id:
        return scoped_id
    prefix, value = scoped_id.split("::", 1)
    if tenant_id and prefix != tenant_id:
        return scoped_id
    return value


def session_db_id(tenant_id: str, session_id: str) -> str:
    return build_scoped_id(tenant_id, session_id)


def knowledge_doc_db_id(tenant_id: str, kb_id: str) -> str:
    return build_scoped_id(tenant_id, kb_id)


def get_session(conn: DBConnection, *, tenant_id: str, session_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, tenant_id, owner_user_id, status, created_at, updated_at
        FROM sessions
        WHERE id=? AND tenant_id=?
        """,
        (session_db_id(tenant_id, session_id), tenant_id),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def serialize_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row.get("last_login_at"),
    }


def get_user_by_id(conn: DBConnection, user_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, tenant_id, email, display_name, password_hash, role, status, created_at, updated_at, last_login_at
        FROM users
        WHERE id=?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_user_by_email(conn: DBConnection, *, tenant_id: str, email: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, tenant_id, email, display_name, password_hash, role, status, created_at, updated_at, last_login_at
        FROM users
        WHERE tenant_id=? AND email=?
        """,
        (tenant_id, normalize_email(email)),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def create_user(
    conn: DBConnection,
    *,
    tenant_id: str,
    email: str,
    password: str,
    display_name: str,
    role: str = "user",
    status: str = "active",
) -> dict[str, Any]:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("邮箱不能为空")
    if len(password.strip()) < 8:
        raise ValueError("密码至少需要 8 位")
    if not display_name.strip():
        raise ValueError("名称不能为空")
    if role not in {"admin", "user"}:
        raise ValueError("角色不合法")
    if status not in {"active", "disabled"}:
        raise ValueError("状态不合法")
    if get_user_by_email(conn, tenant_id=normalized_tenant_id, email=normalized_email):
        raise ValueError("该邮箱已注册")

    now = now_iso()
    user_id = new_id("user")
    conn.execute(
        """
        INSERT INTO users (id, tenant_id, email, display_name, password_hash, role, status, created_at, updated_at, last_login_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            user_id,
            normalized_tenant_id,
            normalized_email,
            display_name.strip(),
            generate_password_hash(password),
            role,
            status,
            now,
            now,
        ),
    )
    conn.commit()
    return serialize_user(get_user_by_id(conn, user_id)) or {}


def ensure_bootstrap_admin(conn: DBConnection, settings: BackendSettings) -> None:
    admin = get_user_by_email(conn, tenant_id=settings.default_tenant_id, email=settings.bootstrap_admin_email)
    if admin is not None:
        return
    create_user(
        conn,
        tenant_id=settings.default_tenant_id,
        email=settings.bootstrap_admin_email,
        password=settings.bootstrap_admin_password,
        display_name=settings.bootstrap_admin_name,
        role="admin",
        status="active",
    )


def authenticate_user(conn: DBConnection, *, tenant_id: str, email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(conn, tenant_id=sanitize_tenant_id(tenant_id), email=email)
    if user is None:
        return None
    if user["status"] != "active":
        raise ValueError("账号已被停用")
    if not check_password_hash(user["password_hash"], password):
        return None
    return serialize_user(user)


def touch_user_login(conn: DBConnection, *, user_id: str) -> None:
    conn.execute(
        """
        UPDATE users
        SET last_login_at=?, updated_at=?
        WHERE id=?
        """,
        (now_iso(), now_iso(), user_id),
    )
    conn.commit()


def list_users(conn: DBConnection, *, tenant_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if tenant_id:
        rows = conn.execute(
            """
            SELECT id, tenant_id, email, display_name, password_hash, role, status, created_at, updated_at, last_login_at
            FROM users
            WHERE tenant_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (sanitize_tenant_id(tenant_id), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tenant_id, email, display_name, password_hash, role, status, created_at, updated_at, last_login_at
            FROM users
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [serialize_user(dict(row)) or {} for row in rows]


def update_user(
    conn: DBConnection,
    *,
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    user = get_user_by_id(conn, user_id)
    if user is None:
        return None
    next_display_name = display_name.strip() if display_name is not None else user["display_name"]
    next_role = role or user["role"]
    next_status = status or user["status"]
    if not next_display_name:
        raise ValueError("名称不能为空")
    if next_role not in {"admin", "user"}:
        raise ValueError("角色不合法")
    if next_status not in {"active", "disabled"}:
        raise ValueError("状态不合法")
    conn.execute(
        """
        UPDATE users
        SET display_name=?, role=?, status=?, updated_at=?
        WHERE id=?
        """,
        (next_display_name, next_role, next_status, now_iso(), user_id),
    )
    conn.commit()
    return serialize_user(get_user_by_id(conn, user_id))


def update_current_user(
    conn: DBConnection,
    *,
    user_id: str,
    display_name: str | None = None,
    current_password: str | None = None,
    new_password: str | None = None,
) -> dict[str, Any] | None:
    user = get_user_by_id(conn, user_id)
    if user is None:
        return None

    next_display_name = display_name.strip() if display_name is not None else user["display_name"]
    if not next_display_name:
        raise ValueError("名称不能为空")

    next_password_hash = user["password_hash"]
    if new_password is not None and new_password.strip():
        if len(new_password.strip()) < 8:
            raise ValueError("密码至少需要 8 位")
        if not current_password or not check_password_hash(user["password_hash"], current_password):
            raise ValueError("当前密码不正确")
        next_password_hash = generate_password_hash(new_password)

    conn.execute(
        """
        UPDATE users
        SET display_name=?, password_hash=?, updated_at=?
        WHERE id=?
        """,
        (next_display_name, next_password_hash, now_iso(), user_id),
    )
    conn.commit()
    return serialize_user(get_user_by_id(conn, user_id))


def delete_user(conn: DBConnection, *, tenant_id: str, user_id: str, current_user_id: str | None = None) -> bool:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    user = get_user_by_id(conn, user_id)
    if user is None or str(user.get("tenant_id") or "") != normalized_tenant_id:
        return False
    if current_user_id and user_id == current_user_id:
        raise ValueError("不能删除当前登录的管理员")
    if user["role"] == "admin" and user["status"] == "active":
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM users
            WHERE tenant_id=? AND role='admin' AND status='active'
            """,
            (normalized_tenant_id,),
        ).fetchone()
        if int((row or {}).get("total") or 0) <= 1:
            raise ValueError("至少保留一个启用中的管理员")
    conn.execute("DELETE FROM users WHERE id=? AND tenant_id=?", (user_id, normalized_tenant_id))
    conn.commit()
    return True


def ensure_session(conn: DBConnection, *, tenant_id: str, session_id: str, owner_user_id: str) -> None:
    now = now_iso()
    existing = get_session(conn, tenant_id=tenant_id, session_id=session_id)
    if existing is None:
        conn.execute(
            """
            INSERT INTO sessions (id, tenant_id, owner_user_id, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (session_db_id(tenant_id, session_id), tenant_id, owner_user_id, now, now),
        )
        conn.commit()
        return

    existing_owner = str(existing.get("owner_user_id") or "").strip()
    if existing_owner and existing_owner != owner_user_id:
        raise PermissionError("session_forbidden")

    conn.execute(
        """
        UPDATE sessions
        SET owner_user_id=?, updated_at=?
        WHERE id=?
        """,
        (owner_user_id, now, session_db_id(tenant_id, session_id)),
    )
    conn.commit()


def insert_message(conn: DBConnection, *, tenant_id: str, session_id: str, role: str, content: str) -> str:
    message_id = new_id("msg")
    conn.execute(
        """
        INSERT INTO messages (id, session_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_id, session_db_id(tenant_id, session_id), role, content, now_iso()),
    )
    conn.commit()
    return message_id


def insert_message_attachment(
    conn: DBConnection,
    *,
    message_id: str,
    tenant_id: str,
    owner_user_id: str,
    session_id: str,
    file_name: str,
    file_path: str,
    mime_type: str | None,
    file_size: int,
    preview_text: str | None,
) -> dict[str, Any]:
    attachment_id = new_id("attachment")
    created_at = now_iso()
    conn.execute(
        """
        INSERT INTO message_attachments (
          id,
          message_id,
          tenant_id,
          owner_user_id,
          session_id,
          file_name,
          file_path,
          mime_type,
          file_size,
          preview_text,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attachment_id,
            message_id,
            tenant_id,
            owner_user_id,
            session_db_id(tenant_id, session_id),
            file_name,
            file_path,
            mime_type,
            file_size,
            preview_text,
            created_at,
        ),
    )
    conn.commit()
    return {
        "id": attachment_id,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size": file_size,
        "preview_text": preview_text,
        "created_at": created_at,
    }


def get_session_history(
    conn: DBConnection,
    session_id: str,
    tenant_id: str,
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    session = get_session(conn, tenant_id=tenant_id, session_id=session_id)
    if session is None:
        return []

    existing_owner = str(session.get("owner_user_id") or "").strip()
    if owner_user_id and existing_owner and existing_owner != owner_user_id:
        raise PermissionError("session_forbidden")

    if owner_user_id and not existing_owner:
        conn.execute(
            "UPDATE sessions SET owner_user_id=?, updated_at=? WHERE id=?",
            (owner_user_id, now_iso(), session_db_id(tenant_id, session_id)),
        )
        conn.commit()

    rows = conn.execute(
        """
        SELECT m.id, m.role, m.content, m.created_at
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        WHERE m.session_id=? AND s.tenant_id=?
        ORDER BY m.created_at ASC
        """,
        (session_db_id(tenant_id, session_id), tenant_id),
    ).fetchall()
    attachment_rows = conn.execute(
        """
        SELECT id, message_id, file_name, mime_type, file_size, preview_text, created_at
        FROM message_attachments
        WHERE tenant_id=? AND session_id=?
        ORDER BY created_at ASC
        """,
        (tenant_id, session_db_id(tenant_id, session_id)),
    ).fetchall()

    attachments_by_message: dict[str, list[dict[str, Any]]] = {}
    for row in attachment_rows:
        attachment = dict(row)
        message_id = str(attachment.pop("message_id") or "")
        attachments_by_message.setdefault(message_id, []).append(attachment)

    history: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["attachments"] = attachments_by_message.get(str(item.get("id") or ""), [])
        history.append(item)
    return history


def insert_qa_log(
    conn: DBConnection,
    *,
    tenant_id: str,
    owner_user_id: str,
    session_id: str,
    question: str,
    answer: str,
    status: str,
    sources: list[dict[str, Any]],
    handoff_required: bool,
    confidence: str,
    reason: str | None,
) -> str:
    log_id = new_id("qa")
    conn.execute(
        """
        INSERT INTO qa_logs (id, tenant_id, owner_user_id, session_id, question, answer, status, sources_json, handoff_required, confidence, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            tenant_id,
            owner_user_id,
            session_id,
            redact_sensitive_text(question) or "",
            redact_sensitive_text(answer) or "",
            status,
            json.dumps(sources, ensure_ascii=False),
            1 if handoff_required else 0,
            confidence,
            redact_sensitive_text(reason),
            now_iso(),
        ),
    )
    if handoff_required:
        conn.execute(
            """
            INSERT INTO handoff_logs (id, tenant_id, owner_user_id, session_id, question, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                new_id("handoff"),
                tenant_id,
                owner_user_id,
                session_id,
                redact_sensitive_text(question) or "",
                redact_sensitive_text(reason) or "handoff_required",
                now_iso(),
            ),
        )
    conn.commit()
    return log_id


def serialize_qa_log(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["sources"] = decode_result_json(item.pop("sources_json", "[]")) or []
    item["handoff_required"] = bool(item.get("handoff_required"))
    return item


def get_qa_log(
    conn: DBConnection,
    *,
    tenant_id: str,
    log_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, tenant_id, owner_user_id, session_id, question, answer, status, sources_json, handoff_required, confidence, reason, created_at
        FROM qa_logs
        WHERE id=? AND tenant_id=?
        """,
        (log_id, sanitize_tenant_id(tenant_id)),
    ).fetchone()
    return serialize_qa_log(row)


def create_qa_log_entry(
    conn: DBConnection,
    *,
    tenant_id: str,
    owner_user_id: str,
    session_id: str,
    question: str,
    answer: str,
    status: str,
    confidence: str | None = None,
    reason: str | None = None,
    handoff_required: bool = False,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    next_session_id = session_id.strip()
    next_question = question.strip()
    next_answer = answer.strip()
    next_status = status.strip()
    next_confidence = (confidence or "").strip() or "medium"
    if not next_session_id:
        raise ValueError("session_id 不能为空")
    if not next_question:
        raise ValueError("问题不能为空")
    if not next_answer:
        raise ValueError("答案不能为空")
    if not next_status:
        raise ValueError("状态不能为空")

    log_id = insert_qa_log(
        conn,
        tenant_id=normalized_tenant_id,
        owner_user_id=owner_user_id,
        session_id=next_session_id,
        question=next_question,
        answer=next_answer,
        status=next_status,
        sources=list(sources or []),
        handoff_required=handoff_required,
        confidence=next_confidence,
        reason=reason.strip() if reason is not None else None,
    )
    return get_qa_log(conn, tenant_id=normalized_tenant_id, log_id=log_id) or {}


def update_qa_log(
    conn: DBConnection,
    *,
    tenant_id: str,
    log_id: str,
    session_id: str | None = None,
    question: str | None = None,
    answer: str | None = None,
    status: str | None = None,
    confidence: str | None = None,
    reason: str | None = None,
    handoff_required: bool | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    item = get_qa_log(conn, tenant_id=tenant_id, log_id=log_id)
    if item is None:
        return None

    next_session_id = session_id.strip() if session_id is not None else str(item.get("session_id") or "")
    next_question = question.strip() if question is not None else str(item.get("question") or "")
    next_answer = answer.strip() if answer is not None else str(item.get("answer") or "")
    next_status = status.strip() if status is not None else str(item.get("status") or "")
    next_confidence = confidence.strip() if confidence is not None else str(item.get("confidence") or "")
    next_reason = reason.strip() if reason is not None else item.get("reason")
    next_handoff_required = handoff_required if handoff_required is not None else bool(item.get("handoff_required"))
    next_sources = list(sources) if sources is not None else list(item.get("sources") or [])

    if not next_session_id:
        raise ValueError("session_id 不能为空")
    if not next_question:
        raise ValueError("问题不能为空")
    if not next_answer:
        raise ValueError("答案不能为空")
    if not next_status:
        raise ValueError("状态不能为空")

    conn.execute(
        """
        UPDATE qa_logs
        SET session_id=?, question=?, answer=?, status=?, sources_json=?, handoff_required=?, confidence=?, reason=?
        WHERE id=? AND tenant_id=?
        """,
        (
            next_session_id,
            redact_sensitive_text(next_question) or "",
            redact_sensitive_text(next_answer) or "",
            next_status,
            json.dumps(next_sources, ensure_ascii=False),
            1 if next_handoff_required else 0,
            next_confidence or None,
            redact_sensitive_text(next_reason),
            log_id,
            sanitize_tenant_id(tenant_id),
        ),
    )
    conn.commit()
    return get_qa_log(conn, tenant_id=tenant_id, log_id=log_id)


def delete_qa_log(conn: DBConnection, *, tenant_id: str, log_id: str) -> bool:
    item = get_qa_log(conn, tenant_id=tenant_id, log_id=log_id)
    if item is None:
        return False
    conn.execute("DELETE FROM qa_logs WHERE id=? AND tenant_id=?", (log_id, sanitize_tenant_id(tenant_id)))
    conn.commit()
    return True


def list_qa_logs(
    conn: DBConnection,
    *,
    limit: int = 100,
    tenant_id: str | None = None,
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    if tenant_id and owner_user_id:
        rows = conn.execute(
            """
            SELECT id, tenant_id, owner_user_id, session_id, question, answer, status, sources_json, handoff_required, confidence, reason, created_at
            FROM qa_logs
            WHERE tenant_id=? AND owner_user_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tenant_id, owner_user_id, limit),
        ).fetchall()
    elif tenant_id:
        rows = conn.execute(
            """
            SELECT id, tenant_id, owner_user_id, session_id, question, answer, status, sources_json, handoff_required, confidence, reason, created_at
            FROM qa_logs
            WHERE tenant_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tenant_id, owner_user_id, session_id, question, answer, status, sources_json, handoff_required, confidence, reason, created_at
            FROM qa_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [serialize_qa_log(dict(row)) or {} for row in rows]


def create_ingestion_job(
    conn: DBConnection,
    *,
    tenant_id: str,
    file_name: str | None,
    file_path: str | None,
) -> str:
    job_id = new_id("job")
    now = now_iso()
    conn.execute(
        """
        INSERT INTO ingestion_jobs (id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'running', NULL, NULL, ?, ?)
        """,
        (job_id, tenant_id, file_name, file_path, now, now),
    )
    conn.commit()
    return job_id


def update_ingestion_job(
    conn: DBConnection,
    *,
    job_id: str,
    status: str,
    error_message: str | None,
    result_payload: dict[str, Any] | None,
) -> None:
    conn.execute(
        """
        UPDATE ingestion_jobs
        SET status=?, error_message=?, result_json=?, updated_at=?
        WHERE id=?
        """,
        (
            status,
            redact_sensitive_text(error_message),
            json.dumps(result_payload, ensure_ascii=False) if result_payload is not None else None,
            now_iso(),
            job_id,
        ),
    )
    conn.commit()


def get_ingestion_job(conn: DBConnection, job_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    if tenant_id:
        row = conn.execute(
            """
            SELECT id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at
            FROM ingestion_jobs WHERE id=? AND tenant_id=?
            """,
            (job_id, tenant_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at
            FROM ingestion_jobs WHERE id=?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["result"] = decode_result_json(item.pop("result_json", None))
    return item


def update_ingestion_job_record(
    conn: DBConnection,
    *,
    tenant_id: str,
    job_id: str,
    file_name: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    item = get_ingestion_job(conn, job_id, tenant_id=sanitize_tenant_id(tenant_id))
    if item is None:
        return None

    next_file_name = file_name.strip() if file_name is not None else item.get("file_name")
    next_status = status.strip() if status is not None else str(item.get("status") or "")
    next_error_message = error_message.strip() if error_message is not None else item.get("error_message")
    if not next_status:
        raise ValueError("状态不能为空")

    conn.execute(
        """
        UPDATE ingestion_jobs
        SET file_name=?, status=?, error_message=?, updated_at=?
        WHERE id=? AND tenant_id=?
        """,
        (
            next_file_name,
            next_status,
            redact_sensitive_text(next_error_message),
            now_iso(),
            job_id,
            sanitize_tenant_id(tenant_id),
        ),
    )
    conn.commit()
    return get_ingestion_job(conn, job_id, tenant_id=sanitize_tenant_id(tenant_id))


def delete_ingestion_job(conn: DBConnection, *, tenant_id: str, job_id: str) -> bool:
    item = get_ingestion_job(conn, job_id, tenant_id=sanitize_tenant_id(tenant_id))
    if item is None:
        return False
    conn.execute("DELETE FROM ingestion_jobs WHERE id=? AND tenant_id=?", (job_id, sanitize_tenant_id(tenant_id)))
    conn.commit()
    return True


def list_ingestion_jobs(
    conn: DBConnection,
    *,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if tenant_id:
        rows = conn.execute(
            """
            SELECT id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at
            FROM ingestion_jobs
            WHERE tenant_id=?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at
            FROM ingestion_jobs
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["result"] = decode_result_json(item.pop("result_json", None))
        items.append(item)
    return items


def upsert_knowledge_docs(conn: DBConnection, *, tenant_id: str, docs: list[dict[str, Any]]) -> None:
    now = now_iso()
    for doc in docs:
        kb_id = str(doc.get("kb_id") or "").strip()
        if not kb_id:
            continue
        conn.execute(
            """
            INSERT INTO knowledge_docs (id, tenant_id, title, category, status, version, visibility, source_path, chunk_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              category=excluded.category,
              status=excluded.status,
              version=excluded.version,
              visibility=excluded.visibility,
              source_path=excluded.source_path,
              chunk_count=excluded.chunk_count,
              updated_at=excluded.updated_at
            """,
            (
                knowledge_doc_db_id(tenant_id, kb_id),
                tenant_id,
                str(doc.get("title") or ""),
                str(doc.get("category") or ""),
                str(doc.get("status") or "draft"),
                str(doc.get("version") or ""),
                str(doc.get("visibility") or "external"),
                str(doc.get("file_name") or ""),
                int(doc.get("chunk_count") or 0),
                now,
                now,
            ),
        )
    conn.commit()


def get_knowledge_doc(
    conn: DBConnection,
    *,
    tenant_id: str,
    knowledge_id: str,
) -> dict[str, Any] | None:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    row = conn.execute(
        """
        SELECT id, tenant_id, title, category, status, version, visibility, source_path, chunk_count, created_at, updated_at
        FROM knowledge_docs
        WHERE id=? AND tenant_id=?
        """,
        (knowledge_doc_db_id(normalized_tenant_id, knowledge_id), normalized_tenant_id),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["id"] = extract_public_id(str(item.get("id") or ""), normalized_tenant_id)
    return item


def update_knowledge_doc(
    conn: DBConnection,
    *,
    tenant_id: str,
    knowledge_id: str,
    title: str | None = None,
    category: str | None = None,
    status: str | None = None,
    visibility: str | None = None,
    version: str | None = None,
) -> dict[str, Any] | None:
    item = get_knowledge_doc(conn, tenant_id=tenant_id, knowledge_id=knowledge_id)
    if item is None:
        return None

    next_title = title.strip() if title is not None else str(item.get("title") or "")
    next_category = category.strip() if category is not None else str(item.get("category") or "")
    next_status = status.strip() if status is not None else str(item.get("status") or "")
    next_visibility = visibility.strip() if visibility is not None else str(item.get("visibility") or "")
    next_version = version.strip() if version is not None else item.get("version")

    if not next_title:
        raise ValueError("标题不能为空")
    if not next_category:
        raise ValueError("分类不能为空")
    if not next_status:
        raise ValueError("状态不能为空")
    if not next_visibility:
        raise ValueError("可见范围不能为空")

    conn.execute(
        """
        UPDATE knowledge_docs
        SET title=?, category=?, status=?, version=?, visibility=?, updated_at=?
        WHERE id=? AND tenant_id=?
        """,
        (
            next_title,
            next_category,
            next_status,
            next_version,
            next_visibility,
            now_iso(),
            knowledge_doc_db_id(sanitize_tenant_id(tenant_id), knowledge_id),
            sanitize_tenant_id(tenant_id),
        ),
    )
    conn.commit()
    return get_knowledge_doc(conn, tenant_id=tenant_id, knowledge_id=knowledge_id)


def delete_knowledge_doc(conn: DBConnection, *, tenant_id: str, knowledge_id: str) -> bool:
    item = get_knowledge_doc(conn, tenant_id=tenant_id, knowledge_id=knowledge_id)
    if item is None:
        return False
    conn.execute(
        "DELETE FROM knowledge_docs WHERE id=? AND tenant_id=?",
        (knowledge_doc_db_id(sanitize_tenant_id(tenant_id), knowledge_id), sanitize_tenant_id(tenant_id)),
    )
    conn.commit()
    return True


def list_knowledge_docs(
    conn: DBConnection,
    *,
    limit: int = 200,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    if tenant_id:
        rows = conn.execute(
            """
            SELECT id, tenant_id, title, category, status, version, visibility, source_path, chunk_count, created_at, updated_at
            FROM knowledge_docs
            WHERE tenant_id=?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tenant_id, title, category, status, version, visibility, source_path, chunk_count, created_at, updated_at
            FROM knowledge_docs
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["id"] = extract_public_id(str(item.get("id") or ""), str(item.get("tenant_id") or ""))
        items.append(item)
    return items


def dashboard_summary(conn: DBConnection, *, tenant_id: str | None = None) -> dict[str, int]:
    if tenant_id:
        users = conn.execute("SELECT COUNT(*) AS total FROM users WHERE tenant_id=?", (tenant_id,)).fetchone()
        docs = conn.execute("SELECT COUNT(*) AS total FROM knowledge_docs WHERE tenant_id=?", (tenant_id,)).fetchone()
        jobs = conn.execute("SELECT COUNT(*) AS total FROM ingestion_jobs WHERE tenant_id=?", (tenant_id,)).fetchone()
        logs = conn.execute("SELECT COUNT(*) AS total FROM qa_logs WHERE tenant_id=?", (tenant_id,)).fetchone()
        agent_runs = conn.execute("SELECT COUNT(*) AS total FROM agent_task_runs WHERE tenant_id=?", (tenant_id,)).fetchone()
        tickets = conn.execute("SELECT COUNT(*) AS total FROM demo_tickets WHERE tenant_id=?", (tenant_id,)).fetchone()
    else:
        users = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        docs = conn.execute("SELECT COUNT(*) AS total FROM knowledge_docs").fetchone()
        jobs = conn.execute("SELECT COUNT(*) AS total FROM ingestion_jobs").fetchone()
        logs = conn.execute("SELECT COUNT(*) AS total FROM qa_logs").fetchone()
        agent_runs = conn.execute("SELECT COUNT(*) AS total FROM agent_task_runs").fetchone()
        tickets = conn.execute("SELECT COUNT(*) AS total FROM demo_tickets").fetchone()

    return {
        "users": int((users or {}).get("total") or 0),
        "knowledge_docs": int((docs or {}).get("total") or 0),
        "ingestion_jobs": int((jobs or {}).get("total") or 0),
        "qa_logs": int((logs or {}).get("total") or 0),
        "agent_task_runs": int((agent_runs or {}).get("total") or 0),
        "demo_tickets": int((tickets or {}).get("total") or 0),
    }


def call_gateway_query(settings: BackendSettings, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return invoke_gateway_runner("query", payload)
    except RuntimeError:
        pass

    request = urllib.request.Request(
        url=f"{settings.gateway_base_url}/query",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    if settings.gateway_api_key:
        request.add_header("x-api-key", settings.gateway_api_key)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        if exc.code in {401, 403, 404, 502, 503}:
            return invoke_gateway_runner("query", payload)
        raise RuntimeError(f"Gateway 调用失败: HTTP {exc.code} {detail or exc.reason}") from exc
    except urllib.error.URLError:
        return invoke_gateway_runner("query", payload)


def invoke_gateway_runner(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "gateway/app/runner_cli.py", action],
        cwd=ROOT,
        env=env,
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr.decode("utf-8", errors="ignore") if result.stderr else "") or (
            result.stdout.decode("utf-8", errors="ignore") if result.stdout else ""
        )
        detail = detail.strip()
        raise RuntimeError(detail or f"gateway runner 执行失败: {result.returncode}")
    stdout = result.stdout.decode("utf-8", errors="ignore") if result.stdout else "{}"
    return json.loads(stdout or "{}")


def save_uploaded_file(
    settings: BackendSettings,
    *,
    tenant_id: str,
    file_name: str,
    content: bytes,
    area: str = "raw",
) -> str:
    upload_root = Path(settings.upload_dir) / sanitize_tenant_id(tenant_id) / area
    day_dir = upload_root / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    final_path = day_dir / sanitize_file_name(file_name)
    final_path.write_bytes(content)
    return str(final_path)


def run_ingestion_job(
    settings: BackendSettings,
    *,
    tenant_id: str,
    file_name: str | None,
    file_path: str | None,
    publish_status: str | None = None,
) -> dict[str, Any]:
    payload = {
        "tenant_id": tenant_id,
        "prepare_raw": True,
        "refresh_index": settings.default_refresh_index,
        "publish_status": publish_status or settings.default_publish_status,
        "prepare_use_llm": False,
    }
    if file_path:
        payload["target_file_path"] = file_path
    result = invoke_gateway_runner("ingest_rebuild", payload)
    result["tenant_id"] = tenant_id
    if file_name:
        result["file_name"] = file_name
    if file_path:
        result["file_path"] = file_path
    return result


def parse_multipart_form(handler: Any) -> dict[str, Any]:
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
    }
    form = cgi.FieldStorage(fp=handler.rfile, headers=handler.headers, environ=environ, keep_blank_values=True)
    result: dict[str, Any] = {"fields": {}, "files": {}}
    if not form.list:
        return result
    for item in form.list:
        if item.filename:
            result["files"][item.name] = {
                "filename": item.filename,
                "content": item.file.read(),
            }
        else:
            result["fields"][item.name] = item.value
    return result
