from __future__ import annotations

import time
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from apiflask import APIFlask
from flask import Response, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import BackendSettings, load_settings
from .database import connect, init_db
from .services import (
    authenticate_user,
    call_gateway_query,
    create_qa_log_entry,
    create_ingestion_job,
    create_user,
    dashboard_summary,
    delete_ingestion_job,
    delete_knowledge_doc,
    delete_qa_log,
    delete_user,
    ensure_bootstrap_admin,
    ensure_session,
    extract_attachment_preview,
    get_knowledge_doc,
    get_qa_log,
    get_ingestion_job,
    get_session_history,
    get_user_by_id,
    insert_message,
    insert_message_attachment,
    insert_qa_log,
    list_ingestion_jobs,
    list_knowledge_docs,
    list_qa_logs,
    list_users,
    run_ingestion_job,
    save_uploaded_file,
    touch_user_login,
    update_current_user,
    update_ingestion_job_record,
    update_knowledge_doc,
    update_qa_log,
    update_ingestion_job,
    update_user,
    upsert_knowledge_docs,
)
from shared.tenant_profile import load_tenant_profile


RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
MAX_CHAT_ATTACHMENTS = 5
GATEWAY_QUESTION_MAX_CHARS = 1800
GATEWAY_HISTORY_ITEM_MAX_CHARS = 520


def json_response(status: HTTPStatus, *, data: Any = None, code: int = 0, message: str = "ok"):
    return {"code": code, "message": message, "data": data}, status.value


def error_response(status: HTTPStatus, code: int, message: str):
    return json_response(status, data=None, code=code, message=message)


def build_gateway_message_text(content: str, attachments: list[dict[str, Any]]) -> str:
    normalized_content = content.strip()
    if not attachments:
        return normalized_content

    attachment_sections: list[str] = []
    for index, attachment in enumerate(attachments, start=1):
        file_name = str(attachment.get("file_name") or f"附件 {index}")
        preview_text = str(attachment.get("preview_text") or "").strip()
        mime_type = str(attachment.get("mime_type") or "unknown")
        if preview_text:
            attachment_sections.append(f"附件 {index}: {file_name}\n{preview_text}")
        else:
            attachment_sections.append(f"附件 {index}: {file_name}\n[文件类型: {mime_type}，未提取到可读文本]")

    parts = [normalized_content] if normalized_content else []
    parts.append("用户补充了以下附件内容：\n" + "\n\n".join(attachment_sections))
    return "\n\n".join(parts).strip()


def clip_text(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def build_gateway_message_text_limited(content: str, attachments: list[dict[str, Any]], *, max_chars: int) -> str:
    normalized_content = clip_text(content.strip(), max_chars)
    if not attachments:
        return normalized_content

    attachment_sections: list[str] = []
    remaining = max_chars - len(normalized_content)
    if normalized_content:
        remaining -= 2
    if remaining <= 0:
        return normalized_content

    intro = "User attachments:\n"
    remaining -= len(intro)
    if remaining <= 0:
        return normalized_content

    for index, attachment in enumerate(attachments, start=1):
        if remaining <= 0:
            break
        file_name = str(attachment.get("file_name") or f"attachment-{index}")
        preview_text = str(attachment.get("preview_text") or "").strip()
        mime_type = str(attachment.get("mime_type") or "unknown")
        heading = f"[Attachment {index}] {file_name}\n"
        if preview_text:
            available_text = max(0, remaining - len(heading) - 2)
            if available_text <= 0:
                break
            attachment_sections.append(heading + clip_text(preview_text, available_text))
        else:
            attachment_sections.append(heading + f"[mime_type: {mime_type}, no readable text extracted]")
        remaining = max_chars - len(normalized_content)
        if normalized_content:
            remaining -= 2
        remaining -= len(intro)
        remaining -= len("\n\n".join(attachment_sections))
        if remaining > 0:
            remaining -= 2

    parts = [normalized_content] if normalized_content else []
    if attachment_sections:
        parts.append(intro + "\n\n".join(attachment_sections))
    return "\n\n".join(parts).strip()


def build_gateway_query_payload(
    *,
    tenant_id: str,
    session_id: str,
    question: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    profile = load_tenant_profile(tenant_id)
    return {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "question": question,
        "history": history,
        "kb_scope": list(profile.default_kb_scope),
        "top_k": profile.default_top_k,
    }


def create_app() -> APIFlask:
    settings = load_settings()
    init_db(settings)
    conn = connect(settings)
    ensure_bootstrap_admin(conn, settings)

    app = APIFlask("foreign_trade_backend")
    app.json.ensure_ascii = False
    app.config["BACKEND_SETTINGS"] = settings
    app.config["DB_CONN"] = conn
    app.config["AUTH_SERIALIZER"] = URLSafeTimedSerializer(settings.auth_secret, salt="foreign-trade-auth")

    def current_settings() -> BackendSettings:
        return app.config["BACKEND_SETTINGS"]

    def current_conn():
        return app.config["DB_CONN"]

    def current_serializer() -> URLSafeTimedSerializer:
        return app.config["AUTH_SERIALIZER"]

    def issue_auth_token(user: dict[str, Any]) -> str:
        return current_serializer().dumps(
            {
                "user_id": user["id"],
                "tenant_id": user["tenant_id"],
                "role": user["role"],
            }
        )

    def current_user_from_request() -> dict[str, Any] | None:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header[7:].strip()
        if not token:
            return None
        try:
            payload = current_serializer().loads(token, max_age=current_settings().auth_token_ttl_hours * 3600)
        except (BadSignature, SignatureExpired):
            return None
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return None
        user = get_user_by_id(current_conn(), user_id)
        if user is None or user.get("status") != "active":
            return None
        return {
            "id": user["id"],
            "tenant_id": user["tenant_id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "role": user["role"],
            "status": user["status"],
            "created_at": user["created_at"],
            "updated_at": user["updated_at"],
            "last_login_at": user.get("last_login_at"),
        }

    def require_auth(admin_only: bool = False):
        def decorator(func: Callable[..., Any]):
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any):
                user = current_user_from_request()
                if user is None:
                    return error_response(HTTPStatus.UNAUTHORIZED, 4010, "auth_required")
                if admin_only and user["role"] != "admin":
                    return error_response(HTTPStatus.FORBIDDEN, 4030, "admin_only")
                g.current_user = user
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def run_ingestion(*, tenant_id: str, file_name: str | None, file_path: str | None):
        job_id = create_ingestion_job(current_conn(), tenant_id=tenant_id, file_name=file_name, file_path=file_path)
        try:
            result = run_ingestion_job(current_settings(), tenant_id=tenant_id, file_name=file_name, file_path=file_path)
            upsert_knowledge_docs(current_conn(), tenant_id=tenant_id, docs=list(result.get("docs") or []))
            update_ingestion_job(current_conn(), job_id=job_id, status="success", error_message=None, result_payload=result)
        except RuntimeError as exc:
            update_ingestion_job(current_conn(), job_id=job_id, status="failed", error_message=str(exc), result_payload=None)
            return None, error_response(HTTPStatus.BAD_GATEWAY, 5003, str(exc)), job_id
        return result, None, job_id

    @app.before_request
    def apply_rate_limit():
        client_ip = (request.headers.get("x-forwarded-for") or request.remote_addr or "unknown").split(",")[0].strip()
        now = time.time()
        window_start = now - 60
        bucket = RATE_LIMIT_BUCKETS.setdefault(client_ip, [])
        bucket[:] = [timestamp for timestamp in bucket if timestamp >= window_start]
        if len(bucket) >= current_settings().rate_limit_per_minute:
            return error_response(HTTPStatus.TOO_MANY_REQUESTS, 4290, "请求过于频繁，请稍后再试")
        bucket.append(now)
        return None

    @app.get("/")
    def index():
        path = Path(__file__).resolve().parent / "static" / "index.html"
        return Response(path.read_bytes(), mimetype="text/html")

    @app.get("/health")
    def health():
        settings = current_settings()
        return json_response(
            HTTPStatus.OK,
            data={
                "status": "ok",
                "gateway_base_url": settings.gateway_base_url,
                "db_driver": settings.db_driver,
                "db_path": settings.db_path,
                "rate_limit_per_minute": settings.rate_limit_per_minute,
                "auth_token_ttl_hours": settings.auth_token_ttl_hours,
            },
        )

    @app.post("/api/auth/register")
    def register():
        payload = request.get_json(silent=True) or {}
        tenant_id = str(payload.get("tenant_id") or current_settings().default_tenant_id).strip() or current_settings().default_tenant_id
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        display_name = str(payload.get("display_name") or "").strip()
        try:
            user = create_user(
                current_conn(),
                tenant_id=tenant_id,
                email=email,
                password=password,
                display_name=display_name,
                role="user",
                status="active",
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        token = issue_auth_token(user)
        return json_response(HTTPStatus.OK, data={"token": token, "user": user})

    @app.post("/api/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        tenant_id = str(payload.get("tenant_id") or current_settings().default_tenant_id).strip() or current_settings().default_tenant_id
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        try:
            user = authenticate_user(current_conn(), tenant_id=tenant_id, email=email, password=password)
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if user is None:
            return error_response(HTTPStatus.UNAUTHORIZED, 4011, "邮箱或密码错误")
        touch_user_login(current_conn(), user_id=user["id"])
        refreshed_user = get_user_by_id(current_conn(), user["id"])
        if refreshed_user is None:
            return error_response(HTTPStatus.UNAUTHORIZED, 4012, "登录状态异常")
        safe_user = {
            "id": refreshed_user["id"],
            "tenant_id": refreshed_user["tenant_id"],
            "email": refreshed_user["email"],
            "display_name": refreshed_user["display_name"],
            "role": refreshed_user["role"],
            "status": refreshed_user["status"],
            "created_at": refreshed_user["created_at"],
            "updated_at": refreshed_user["updated_at"],
            "last_login_at": refreshed_user.get("last_login_at"),
        }
        token = issue_auth_token(safe_user)
        return json_response(HTTPStatus.OK, data={"token": token, "user": safe_user})

    @app.post("/api/auth/logout")
    def logout():
        return json_response(HTTPStatus.OK, data={"ok": True})

    @app.get("/api/auth/me")
    @require_auth()
    def me():
        return json_response(HTTPStatus.OK, data=g.current_user)

    @app.patch("/api/auth/me")
    @require_auth()
    def me_update():
        payload = request.get_json(silent=True) or {}
        try:
            user = update_current_user(
                current_conn(),
                user_id=g.current_user["id"],
                display_name=str(payload.get("display_name")).strip()
                if payload.get("display_name") is not None
                else None,
                current_password=str(payload.get("current_password") or "").strip() or None,
                new_password=str(payload.get("new_password") or "").strip() or None,
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if user is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "用户不存在")
        return json_response(HTTPStatus.OK, data=user)

    @app.post("/api/chat/send")
    @require_auth()
    def chat_send():
        tenant_id = g.current_user["tenant_id"]
        owner_user_id = g.current_user["id"]
        uploads = request.files.getlist("files") if request.files else []
        if (request.mimetype or "").startswith("multipart/"):
            payload = request.form.to_dict(flat=True)
        else:
            payload = request.get_json(silent=True) or {}

        session_id = str(payload.get("session_id") or "").strip()
        question = str(payload.get("question") or "").strip()
        if not question and uploads:
            question = "请先阅读我上传的附件，再提炼重点并给出回复。"

        if not session_id or not question:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, "session_id 和 question 不能为空")
        if len(uploads) > MAX_CHAT_ATTACHMENTS:
            return error_response(HTTPStatus.BAD_REQUEST, 4002, f"单次最多上传 {MAX_CHAT_ATTACHMENTS} 个附件")
        if uploads and (request.content_length or 0) > current_settings().upload_max_bytes:
            return error_response(HTTPStatus.BAD_REQUEST, 4002, f"上传内容过大，不能超过 {current_settings().upload_max_bytes} bytes")

        try:
            ensure_session(current_conn(), tenant_id=tenant_id, session_id=session_id, owner_user_id=owner_user_id)
        except PermissionError:
            return error_response(HTTPStatus.FORBIDDEN, 4031, "session_forbidden")

        user_message_id = insert_message(current_conn(), tenant_id=tenant_id, session_id=session_id, role="user", content=question)
        saved_attachments: list[dict[str, Any]] = []
        for upload in uploads:
            file_name = upload.filename or "attachment.bin"
            content = upload.read()
            file_path = save_uploaded_file(
                current_settings(),
                tenant_id=tenant_id,
                file_name=file_name,
                content=content,
                area="chat",
            )
            extraction = extract_attachment_preview(
                current_settings(),
                tenant_id=tenant_id,
                file_path=file_path,
                file_name=file_name,
                content=content,
                mime_type=upload.mimetype,
            )
            saved_attachment = insert_message_attachment(
                current_conn(),
                message_id=user_message_id,
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                session_id=session_id,
                file_name=file_name,
                file_path=file_path,
                mime_type=upload.mimetype,
                file_size=len(content),
                preview_text=extraction.get("preview_text"),
            )
            saved_attachment["media_type"] = extraction.get("media_type")
            saved_attachment["used_gateway"] = extraction.get("used_gateway", False)
            if extraction.get("warnings"):
                saved_attachment["warnings"] = extraction["warnings"]
            saved_attachments.append(saved_attachment)

        try:
            history_rows = get_session_history(
                current_conn(),
                session_id,
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
            )
        except PermissionError:
            return error_response(HTTPStatus.FORBIDDEN, 4031, "session_forbidden")

        history = [
            {
                "role": str(row.get("role") or ""),
                "content": build_gateway_message_text_limited(
                    str(row.get("content") or ""),
                    list(row.get("attachments") or []),
                    max_chars=GATEWAY_HISTORY_ITEM_MAX_CHARS,
                ),
            }
            for row in history_rows[:-1][-6:]
            if str(row.get("content") or "").strip() or row.get("attachments")
        ]
        gateway_payload = build_gateway_query_payload(
            tenant_id=tenant_id,
            session_id=session_id,
            question=build_gateway_message_text_limited(
                question,
                saved_attachments,
                max_chars=GATEWAY_QUESTION_MAX_CHARS,
            ),
            history=history,
        )
        try:
            result = call_gateway_query(current_settings(), gateway_payload)
        except RuntimeError as exc:
            return error_response(HTTPStatus.BAD_GATEWAY, 5001, str(exc))

        answer = str(result.get("answer") or "")
        insert_message(current_conn(), tenant_id=tenant_id, session_id=session_id, role="assistant", content=answer)
        insert_qa_log(
            current_conn(),
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            session_id=session_id,
            question=question,
            answer=answer,
            status=str(result.get("status") or "blocked"),
            sources=list(result.get("sources") or []),
            handoff_required=bool(result.get("handoff_required")),
            confidence=str(result.get("confidence") or "low"),
            reason=(str(result.get("reason")) if result.get("reason") is not None else None),
        )
        result["uploaded_attachments"] = saved_attachments
        return json_response(HTTPStatus.OK, data=result)

    @app.get("/api/chat/history")
    @require_auth()
    def chat_history():
        session_id = (request.args.get("session_id") or "").strip()
        tenant_id = g.current_user["tenant_id"]
        owner_user_id = g.current_user["id"]
        if not session_id:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, "session_id 不能为空")
        try:
            history = get_session_history(current_conn(), session_id, tenant_id=tenant_id, owner_user_id=owner_user_id)
        except PermissionError:
            return error_response(HTTPStatus.FORBIDDEN, 4031, "session_forbidden")
        return json_response(HTTPStatus.OK, data={"session_id": session_id, "messages": history})

    @app.get("/api/knowledge/list")
    @require_auth()
    def knowledge_list():
        items = list_knowledge_docs(current_conn(), tenant_id=g.current_user["tenant_id"])
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.get("/api/logs/qa")
    @require_auth()
    def qa_logs():
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 500))
        except ValueError:
            limit = 100
        items = list_qa_logs(
            current_conn(),
            tenant_id=g.current_user["tenant_id"],
            owner_user_id=g.current_user["id"],
            limit=limit,
        )
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.post("/api/knowledge/upload")
    @require_auth(admin_only=True)
    def knowledge_upload():
        content_length = request.content_length or 0
        if content_length > current_settings().upload_max_bytes:
            return error_response(HTTPStatus.BAD_REQUEST, 4002, f"上传文件过大，不能超过 {current_settings().upload_max_bytes} bytes")

        tenant_id = g.current_user["tenant_id"]
        file_name: str | None = None
        file_path: str | None = None
        if request.files.get("file") is not None:
            upload = request.files["file"]
            file_name = upload.filename or "upload.bin"
            file_path = save_uploaded_file(
                current_settings(),
                tenant_id=tenant_id,
                file_name=file_name,
                content=upload.read(),
            )
        else:
            payload = request.get_json(silent=True) or {}
            file_path = str(payload.get("file_path") or "").strip()
            if not file_path:
                return error_response(HTTPStatus.BAD_REQUEST, 4001, "缺少 file_path")
            file_name = str(payload.get("file_name") or "").strip() or Path(file_path).name

        result, error, job_id = run_ingestion(tenant_id=tenant_id, file_name=file_name, file_path=file_path)
        if error is not None:
            return error
        return json_response(
            HTTPStatus.OK,
            data={
                "job_id": job_id,
                "status": "success",
                "file_name": file_name,
                "file_path": file_path,
                "result": result,
            },
        )

    @app.post("/api/ingestion/jobs")
    @require_auth(admin_only=True)
    def ingestion_jobs_create():
        payload = request.get_json(silent=True) or {}
        tenant_id = g.current_user["tenant_id"]
        file_path = str(payload.get("file_path") or "").strip()
        file_name = str(payload.get("file_name") or "").strip() or None
        if not file_path:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, "file_path 不能为空")
        result, error, job_id = run_ingestion(tenant_id=tenant_id, file_name=file_name, file_path=file_path)
        if error is not None:
            return error
        return json_response(HTTPStatus.OK, data={"job_id": job_id, "status": "success", "result": result})

    @app.get("/api/ingestion/jobs/<job_id>")
    @require_auth(admin_only=True)
    def ingestion_jobs_get(job_id: str):
        item = get_ingestion_job(current_conn(), job_id, tenant_id=g.current_user["tenant_id"])
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "job 不存在")
        return json_response(HTTPStatus.OK, data=item)

    @app.get("/api/admin/overview")
    @require_auth(admin_only=True)
    def admin_overview():
        tenant_id = g.current_user["tenant_id"]
        return json_response(
            HTTPStatus.OK,
            data={
                "tenant_id": tenant_id,
                "summary": dashboard_summary(current_conn(), tenant_id=tenant_id),
                "me": g.current_user,
            },
        )

    @app.get("/api/admin/users")
    @require_auth(admin_only=True)
    def admin_users():
        items = list_users(current_conn(), tenant_id=g.current_user["tenant_id"])
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.post("/api/admin/users")
    @require_auth(admin_only=True)
    def admin_users_create():
        payload = request.get_json(silent=True) or {}
        try:
            user = create_user(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                email=str(payload.get("email") or "").strip(),
                password=str(payload.get("password") or ""),
                display_name=str(payload.get("display_name") or "").strip(),
                role=str(payload.get("role") or "user").strip() or "user",
                status=str(payload.get("status") or "active").strip() or "active",
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        return json_response(HTTPStatus.OK, data=user)

    @app.patch("/api/admin/users/<user_id>")
    @require_auth(admin_only=True)
    def admin_users_update(user_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            user = update_user(
                current_conn(),
                user_id=user_id,
                display_name=str(payload.get("display_name")).strip() if payload.get("display_name") is not None else None,
                role=str(payload.get("role")).strip() if payload.get("role") is not None else None,
                status=str(payload.get("status")).strip() if payload.get("status") is not None else None,
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if user is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "用户不存在")
        return json_response(HTTPStatus.OK, data=user)

    @app.delete("/api/admin/users/<user_id>")
    @require_auth(admin_only=True)
    def admin_users_delete(user_id: str):
        try:
            deleted = delete_user(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                user_id=user_id,
                current_user_id=g.current_user["id"],
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if not deleted:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "用户不存在")
        return json_response(HTTPStatus.OK, data={"id": user_id, "deleted": True})

    @app.get("/api/admin/knowledge/list")
    @require_auth(admin_only=True)
    def admin_knowledge_list():
        items = list_knowledge_docs(current_conn(), tenant_id=g.current_user["tenant_id"])
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.post("/api/admin/knowledge/upload")
    @require_auth(admin_only=True)
    def admin_knowledge_upload():
        if request.files.get("file") is None:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, "缺少 file")
        upload = request.files["file"]
        file_name = upload.filename or "upload.bin"
        file_path = save_uploaded_file(
            current_settings(),
            tenant_id=g.current_user["tenant_id"],
            file_name=file_name,
            content=upload.read(),
        )
        result, error, job_id = run_ingestion(tenant_id=g.current_user["tenant_id"], file_name=file_name, file_path=file_path)
        if error is not None:
            return error
        return json_response(
            HTTPStatus.OK,
            data={
                "job_id": job_id,
                "status": "success",
                "file_name": file_name,
                "file_path": file_path,
                "result": result,
            },
        )

    @app.get("/api/admin/knowledge/<knowledge_id>")
    @require_auth(admin_only=True)
    def admin_knowledge_get(knowledge_id: str):
        item = get_knowledge_doc(
            current_conn(),
            tenant_id=g.current_user["tenant_id"],
            knowledge_id=knowledge_id,
        )
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "knowledge_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.patch("/api/admin/knowledge/<knowledge_id>")
    @require_auth(admin_only=True)
    def admin_knowledge_update(knowledge_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            item = update_knowledge_doc(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                knowledge_id=knowledge_id,
                title=str(payload.get("title")).strip() if payload.get("title") is not None else None,
                category=str(payload.get("category")).strip() if payload.get("category") is not None else None,
                status=str(payload.get("status")).strip() if payload.get("status") is not None else None,
                visibility=str(payload.get("visibility")).strip() if payload.get("visibility") is not None else None,
                version=str(payload.get("version")).strip() if payload.get("version") is not None else None,
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "knowledge_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.delete("/api/admin/knowledge/<knowledge_id>")
    @require_auth(admin_only=True)
    def admin_knowledge_delete(knowledge_id: str):
        deleted = delete_knowledge_doc(
            current_conn(),
            tenant_id=g.current_user["tenant_id"],
            knowledge_id=knowledge_id,
        )
        if not deleted:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "knowledge_not_found")
        return json_response(HTTPStatus.OK, data={"id": knowledge_id, "deleted": True})

    @app.get("/api/admin/ingestion/jobs")
    @require_auth(admin_only=True)
    def admin_ingestion_jobs():
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 300))
        except ValueError:
            limit = 100
        items = list_ingestion_jobs(current_conn(), tenant_id=g.current_user["tenant_id"], limit=limit)
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.post("/api/admin/ingestion/jobs")
    @require_auth(admin_only=True)
    def admin_ingestion_jobs_create():
        payload = request.get_json(silent=True) or {}
        tenant_id = g.current_user["tenant_id"]
        file_path = str(payload.get("file_path") or "").strip()
        file_name = str(payload.get("file_name") or "").strip() or None
        if not file_path:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, "file_path 不能为空")
        result, error, job_id = run_ingestion(tenant_id=tenant_id, file_name=file_name, file_path=file_path)
        if error is not None:
            return error
        return json_response(HTTPStatus.OK, data={"job_id": job_id, "status": "success", "result": result})

    @app.get("/api/admin/ingestion/jobs/<job_id>")
    @require_auth(admin_only=True)
    def admin_ingestion_jobs_get(job_id: str):
        item = get_ingestion_job(current_conn(), job_id, tenant_id=g.current_user["tenant_id"])
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "job_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.patch("/api/admin/ingestion/jobs/<job_id>")
    @require_auth(admin_only=True)
    def admin_ingestion_jobs_update(job_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            item = update_ingestion_job_record(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                job_id=job_id,
                file_name=str(payload.get("file_name")).strip() if payload.get("file_name") is not None else None,
                status=str(payload.get("status")).strip() if payload.get("status") is not None else None,
                error_message=str(payload.get("error_message")).strip()
                if payload.get("error_message") is not None
                else None,
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "job_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.delete("/api/admin/ingestion/jobs/<job_id>")
    @require_auth(admin_only=True)
    def admin_ingestion_jobs_delete(job_id: str):
        deleted = delete_ingestion_job(current_conn(), tenant_id=g.current_user["tenant_id"], job_id=job_id)
        if not deleted:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "job_not_found")
        return json_response(HTTPStatus.OK, data={"id": job_id, "deleted": True})

    @app.get("/api/admin/logs/qa")
    @require_auth(admin_only=True)
    def admin_logs():
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 300))
        except ValueError:
            limit = 100
        items = list_qa_logs(current_conn(), tenant_id=g.current_user["tenant_id"], limit=limit)
        return json_response(HTTPStatus.OK, data={"items": items})

    @app.post("/api/admin/logs/qa")
    @require_auth(admin_only=True)
    def admin_logs_create():
        payload = request.get_json(silent=True) or {}
        try:
            item = create_qa_log_entry(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                owner_user_id=g.current_user["id"],
                session_id=str(payload.get("session_id") or "").strip(),
                question=str(payload.get("question") or "").strip(),
                answer=str(payload.get("answer") or "").strip(),
                status=str(payload.get("status") or "answered").strip() or "answered",
                confidence=str(payload.get("confidence") or "medium").strip() or "medium",
                reason=str(payload.get("reason") or "").strip() or None,
                handoff_required=bool(payload.get("handoff_required")),
                sources=list(payload.get("sources") or []),
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        return json_response(HTTPStatus.OK, data=item)

    @app.get("/api/admin/logs/qa/<log_id>")
    @require_auth(admin_only=True)
    def admin_logs_get(log_id: str):
        item = get_qa_log(current_conn(), tenant_id=g.current_user["tenant_id"], log_id=log_id)
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "qa_log_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.patch("/api/admin/logs/qa/<log_id>")
    @require_auth(admin_only=True)
    def admin_logs_update(log_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            item = update_qa_log(
                current_conn(),
                tenant_id=g.current_user["tenant_id"],
                log_id=log_id,
                session_id=str(payload.get("session_id")).strip() if payload.get("session_id") is not None else None,
                question=str(payload.get("question")).strip() if payload.get("question") is not None else None,
                answer=str(payload.get("answer")).strip() if payload.get("answer") is not None else None,
                status=str(payload.get("status")).strip() if payload.get("status") is not None else None,
                confidence=str(payload.get("confidence")).strip() if payload.get("confidence") is not None else None,
                reason=str(payload.get("reason")).strip() if payload.get("reason") is not None else None,
                handoff_required=bool(payload.get("handoff_required"))
                if payload.get("handoff_required") is not None
                else None,
                sources=list(payload.get("sources") or [])
                if payload.get("sources") is not None
                else None,
            )
        except ValueError as exc:
            return error_response(HTTPStatus.BAD_REQUEST, 4001, str(exc))
        if item is None:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "qa_log_not_found")
        return json_response(HTTPStatus.OK, data=item)

    @app.delete("/api/admin/logs/qa/<log_id>")
    @require_auth(admin_only=True)
    def admin_logs_delete(log_id: str):
        deleted = delete_qa_log(current_conn(), tenant_id=g.current_user["tenant_id"], log_id=log_id)
        if not deleted:
            return error_response(HTTPStatus.NOT_FOUND, 4004, "qa_log_not_found")
        return json_response(HTTPStatus.OK, data={"id": log_id, "deleted": True})

    return app


app = create_app()


def run() -> None:
    settings: BackendSettings = app.config["BACKEND_SETTINGS"]
    print(f"Backend listening on http://{settings.app_host}:{settings.app_port}")
    app.run(host=settings.app_host, port=settings.app_port, debug=False)


if __name__ == "__main__":
    run()
