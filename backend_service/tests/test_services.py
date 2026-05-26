from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend_service.config import BackendSettings
from backend_service.database import connect, init_db
from backend_service.server import build_gateway_message_text_limited, build_gateway_query_payload
from backend_service.services import (
    authenticate_user,
    build_attachment_preview,
    build_scoped_id,
    create_user,
    create_qa_log_entry,
    dashboard_summary,
    delete_ingestion_job,
    delete_knowledge_doc,
    delete_qa_log,
    delete_user,
    ensure_bootstrap_admin,
    ensure_session,
    extract_attachment_preview,
    extract_public_id,
    get_knowledge_doc,
    get_qa_log,
    get_session_history,
    insert_message,
    insert_message_attachment,
    insert_qa_log,
    list_knowledge_docs,
    list_qa_logs,
    list_users,
    redact_sensitive_text,
    run_ingestion_job,
    save_uploaded_file,
    update_user,
    update_ingestion_job_record,
    update_knowledge_doc,
    update_qa_log,
    upsert_knowledge_docs,
)


def make_settings(root: Path) -> BackendSettings:
    return BackendSettings(
        app_host="127.0.0.1",
        app_port=8877,
        gateway_base_url="http://127.0.0.1:8765/gateways/rag_kefu_gateway",
        gateway_api_key="",
        auth_secret="dev-only-change-me",
        auth_token_ttl_hours=72,
        bootstrap_admin_email="admin@foreigntrade.local",
        bootstrap_admin_password="Admin@123456",
        bootstrap_admin_name="系统管理员",
        upload_dir=str(root / "tenant_kb"),
        db_driver="sqlite",
        db_path=str(root / "data" / "app.db"),
        database_url="",
        default_tenant_id="foreign_trade_demo",
        default_publish_status="active",
        default_refresh_index=True,
        app_log_dir=str(root / "logs"),
        request_body_max_bytes=65536,
        upload_max_bytes=25 * 1024 * 1024,
        rate_limit_per_minute=120,
    )


class BackendServiceTests(unittest.TestCase):
    def test_init_db_creates_core_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)

            conn = connect(settings)
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            conn.close()

            table_names = {row["name"] for row in rows}
            self.assertIn("sessions", table_names)
            self.assertIn("messages", table_names)
            self.assertIn("message_attachments", table_names)
            self.assertIn("knowledge_docs", table_names)
            self.assertIn("ingestion_jobs", table_names)
            self.assertIn("qa_logs", table_names)

    def test_knowledge_doc_ids_are_scoped_in_db_but_public_on_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            upsert_knowledge_docs(
                conn,
                tenant_id="tenant_a",
                docs=[
                    {
                        "kb_id": "faq_001",
                        "title": "外贸 FAQ",
                        "category": "faq",
                        "status": "active",
                        "version": "2026-05-22",
                        "visibility": "external",
                        "file_name": "faq.md",
                        "chunk_count": 3,
                    }
                ],
            )
            upsert_knowledge_docs(
                conn,
                tenant_id="tenant_b",
                docs=[
                    {
                        "kb_id": "faq_001",
                        "title": "另一个租户 FAQ",
                        "category": "faq",
                        "status": "active",
                        "version": "2026-05-22",
                        "visibility": "external",
                        "file_name": "faq_other.md",
                        "chunk_count": 2,
                    }
                ],
            )

            items = list_knowledge_docs(conn, tenant_id="tenant_a")
            raw_rows = conn.execute("SELECT id, tenant_id FROM knowledge_docs ORDER BY tenant_id ASC").fetchall()
            conn.close()

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "faq_001")
            self.assertEqual(items[0]["tenant_id"], "tenant_a")
            self.assertEqual(raw_rows[0]["id"], "tenant_a::faq_001")
            self.assertEqual(raw_rows[1]["id"], "tenant_b::faq_001")

    def test_knowledge_doc_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            upsert_knowledge_docs(
                conn,
                tenant_id="tenant_demo",
                docs=[
                    {
                        "kb_id": "faq_001",
                        "title": "旧标题",
                        "category": "faq",
                        "status": "draft",
                        "visibility": "internal",
                        "file_name": "faq.md",
                        "chunk_count": 1,
                    }
                ],
            )

            updated = update_knowledge_doc(
                conn,
                tenant_id="tenant_demo",
                knowledge_id="faq_001",
                title="新标题",
                status="active",
                visibility="external",
            )
            fetched = get_knowledge_doc(conn, tenant_id="tenant_demo", knowledge_id="faq_001")
            deleted = delete_knowledge_doc(conn, tenant_id="tenant_demo", knowledge_id="faq_001")
            conn.close()

            self.assertIsNotNone(updated)
            self.assertEqual(fetched["title"], "新标题")
            self.assertTrue(deleted)

    def test_ingestion_job_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            job_id = run_ingestion_job.__name__
            created_id = None
            conn.execute(
                """
                INSERT INTO ingestion_jobs (id, tenant_id, file_name, file_path, status, error_message, result_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("job_001", "tenant_demo", "faq.md", "C:/demo/faq.md", "running", None, None, "2026-05-25T00:00:00", "2026-05-25T00:00:00"),
            )
            conn.commit()

            updated = update_ingestion_job_record(
                conn,
                tenant_id="tenant_demo",
                job_id="job_001",
                status="failed",
                error_message="boom",
            )
            deleted = delete_ingestion_job(conn, tenant_id="tenant_demo", job_id="job_001")
            conn.close()

            self.assertIsNotNone(updated)
            self.assertEqual(updated["status"], "failed")
            self.assertTrue(deleted)

    def test_qa_log_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            user = create_user(
                conn,
                tenant_id="tenant_demo",
                email="admin@example.com",
                password="Secret123",
                display_name="Admin",
                role="admin",
            )
            created = create_qa_log_entry(
                conn,
                tenant_id="tenant_demo",
                owner_user_id=user["id"],
                session_id="session_001",
                question="How much?",
                answer="100",
                status="answered",
                confidence="high",
                reason="manual",
                sources=[{"doc_id": "faq_001"}],
            )
            updated = update_qa_log(
                conn,
                tenant_id="tenant_demo",
                log_id=created["id"],
                question="How much is shipping?",
                answer="Depends",
                status="fallback",
                confidence="medium",
                reason="needs review",
            )
            fetched = get_qa_log(conn, tenant_id="tenant_demo", log_id=created["id"])
            deleted = delete_qa_log(conn, tenant_id="tenant_demo", log_id=created["id"])
            conn.close()

            self.assertIsNotNone(updated)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["status"], "fallback")
            self.assertTrue(deleted)

    def test_save_uploaded_file_uses_tenant_raw_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            saved_path = Path(
                save_uploaded_file(
                    settings,
                    tenant_id="ACME 外贸客户",
                    file_name="报价单?.txt",
                    content="测试内容".encode("utf-8"),
                )
            )

            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.read_text(encoding="utf-8"), "测试内容")
            self.assertIn("/tenant_kb/ACME/raw/", saved_path.as_posix())
            self.assertEqual(saved_path.name, "报价单_.txt")

    def test_build_attachment_preview_for_text_file(self) -> None:
        preview = build_attachment_preview("brief.md", "# Title\n\nhello".encode("utf-8"), "text/markdown")
        self.assertIn("Title", preview or "")
        self.assertIn("hello", preview or "")

    def test_extract_attachment_preview_uses_gateway_text_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            sample_path = Path(tmp_dir) / "quote.png"
            sample_path.write_bytes(b"fake-image")

            with patch(
                "backend_service.services.invoke_gateway_runner",
                return_value={
                    "media_type": "image",
                    "text": "Extracted text from OCR",
                    "warnings": ["ocr_used"],
                },
            ) as mock_runner:
                result = extract_attachment_preview(
                    settings,
                    tenant_id="foreign_trade_demo",
                    file_path=str(sample_path),
                    file_name="quote.png",
                    content=b"fake-image",
                    mime_type="image/png",
                )

            action, payload = mock_runner.call_args.args
            self.assertEqual(action, "extract_attachment")
            self.assertEqual(payload["file_path"], str(sample_path))
            self.assertEqual(result["preview_text"], "Extracted text from OCR")
            self.assertEqual(result["media_type"], "image")
            self.assertTrue(result["used_gateway"])
            self.assertEqual(result["warnings"], ["ocr_used"])

    def test_extract_attachment_preview_falls_back_to_local_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            sample_path = Path(tmp_dir) / "brief.txt"
            sample_path.write_text("fallback body", encoding="utf-8")

            with patch("backend_service.services.invoke_gateway_runner", side_effect=RuntimeError("multimodal disabled")):
                result = extract_attachment_preview(
                    settings,
                    tenant_id="foreign_trade_demo",
                    file_path=str(sample_path),
                    file_name="brief.txt",
                    content="fallback body".encode("utf-8"),
                    mime_type="text/plain",
                )

            self.assertEqual(result["preview_text"], "fallback body")
            self.assertIsNone(result["media_type"])
            self.assertFalse(result["used_gateway"])
            self.assertEqual(result["warnings"], ["multimodal disabled"])

    def test_extract_attachment_preview_summarizes_runner_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            sample_path = Path(tmp_dir) / "image.png"
            sample_path.write_bytes(b"fake-image")
            traceback_text = "\n".join(
                [
                    "Traceback (most recent call last):",
                    "  File \"runner.py\", line 1, in <module>",
                    "requests.exceptions.SSLError: upstream handshake failed",
                ]
            )

            with patch("backend_service.services.invoke_gateway_runner", side_effect=RuntimeError(traceback_text)):
                result = extract_attachment_preview(
                    settings,
                    tenant_id="foreign_trade_demo",
                    file_path=str(sample_path),
                    file_name="image.png",
                    content=b"fake-image",
                    mime_type="image/png",
                )

            self.assertEqual(result["warnings"], ["upstream handshake failed"])

    def test_build_gateway_message_text_limited_clips_long_attachment_text(self) -> None:
        content = build_gateway_message_text_limited(
            "Please review this file.",
            [
                {
                    "file_name": "catalog.pdf",
                    "mime_type": "application/pdf",
                    "preview_text": "A" * 5000,
                }
            ],
            max_chars=320,
        )

        self.assertLessEqual(len(content), 320)
        self.assertIn("catalog.pdf", content)

    def test_build_gateway_query_payload_uses_tenant_profile_defaults(self) -> None:
        with patch(
            "backend_service.server.load_tenant_profile",
            return_value=type(
                "Profile",
                (),
                {
                    "default_kb_scope": ("support", "policy"),
                    "default_top_k": 8,
                },
            )(),
        ):
            payload = build_gateway_query_payload(
                tenant_id="tenant_demo",
                session_id="session_001",
                question="hello",
                history=[],
            )

        self.assertEqual(payload["kb_scope"], ["support", "policy"])
        self.assertEqual(payload["top_k"], 8)

    def test_run_ingestion_job_builds_expected_runner_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            fake_result = {"status": "success", "docs": [{"kb_id": "faq_001"}]}

            with patch("backend_service.services.invoke_gateway_runner", return_value=fake_result) as mock_runner:
                result = run_ingestion_job(
                    settings,
                    tenant_id="foreign_trade_demo",
                    file_name="faq.txt",
                    file_path="C:/demo/faq.txt",
                    publish_status="draft",
                )

            action, payload = mock_runner.call_args.args
            self.assertEqual(action, "ingest_rebuild")
            self.assertEqual(payload["tenant_id"], "foreign_trade_demo")
            self.assertTrue(payload["prepare_raw"])
            self.assertTrue(payload["refresh_index"])
            self.assertFalse(payload["prepare_use_llm"])
            self.assertEqual(payload["publish_status"], "draft")
            self.assertEqual(payload["target_file_path"], "C:/demo/faq.txt")
            self.assertEqual(result["tenant_id"], "foreign_trade_demo")
            self.assertEqual(result["file_name"], "faq.txt")

    def test_sensitive_text_is_redacted_in_logs(self) -> None:
        raw_text = "调用失败，使用 key: sk-1234567890abcdef"
        self.assertEqual(redact_sensitive_text(raw_text), "调用失败，使用 key: [REDACTED_KEY]")

    def test_scoped_id_helpers_round_trip(self) -> None:
        scoped_id = build_scoped_id("tenant_a", "faq_001")
        self.assertEqual(scoped_id, "tenant_a::faq_001")
        self.assertEqual(extract_public_id(scoped_id, "tenant_a"), "faq_001")
        self.assertEqual(extract_public_id(scoped_id, "tenant_b"), scoped_id)

    def test_bootstrap_admin_and_auth_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            ensure_bootstrap_admin(conn, settings)
            users = list_users(conn, tenant_id="foreign_trade_demo")
            admin = authenticate_user(
                conn,
                tenant_id="foreign_trade_demo",
                email="admin@foreigntrade.local",
                password="Admin@123456",
            )
            conn.close()

            self.assertEqual(len(users), 1)
            self.assertIsNotNone(admin)
            self.assertEqual(admin["role"], "admin")

    def test_user_create_update_delete_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            admin = create_user(
                conn,
                tenant_id="tenant_demo",
                email="admin@example.com",
                password="Secret123",
                display_name="Admin",
                role="admin",
            )
            user = create_user(
                conn,
                tenant_id="tenant_demo",
                email="alice@example.com",
                password="Secret123",
                display_name="Alice",
            )
            updated = update_user(conn, user_id=user["id"], role="admin", status="disabled", display_name="Alice Admin")
            summary_before_delete = dashboard_summary(conn, tenant_id="tenant_demo")
            deleted = delete_user(conn, tenant_id="tenant_demo", user_id=user["id"], current_user_id=admin["id"])
            summary_after_delete = dashboard_summary(conn, tenant_id="tenant_demo")
            conn.close()

            self.assertEqual(user["role"], "user")
            self.assertIsNotNone(updated)
            self.assertEqual(updated["role"], "admin")
            self.assertEqual(updated["status"], "disabled")
            self.assertEqual(updated["display_name"], "Alice Admin")
            self.assertEqual(summary_before_delete["users"], 2)
            self.assertTrue(deleted)
            self.assertEqual(summary_after_delete["users"], 1)

    def test_cannot_delete_last_active_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)
            admin = create_user(
                conn,
                tenant_id="tenant_demo",
                email="admin@example.com",
                password="Secret123",
                display_name="Admin",
                role="admin",
            )

            with self.assertRaises(ValueError):
                delete_user(conn, tenant_id="tenant_demo", user_id=admin["id"], current_user_id="another_admin")

            conn.close()

    def test_session_logs_and_attachments_are_isolated_by_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            user_a = create_user(
                conn,
                tenant_id="tenant_demo",
                email="alice@example.com",
                password="Secret123",
                display_name="Alice",
            )
            user_b = create_user(
                conn,
                tenant_id="tenant_demo",
                email="bob@example.com",
                password="Secret123",
                display_name="Bob",
            )

            ensure_session(conn, tenant_id="tenant_demo", session_id="s_001", owner_user_id=user_a["id"])
            user_message_id = insert_message(conn, tenant_id="tenant_demo", session_id="s_001", role="user", content="hello")
            insert_message_attachment(
                conn,
                message_id=user_message_id,
                tenant_id="tenant_demo",
                owner_user_id=user_a["id"],
                session_id="s_001",
                file_name="brief.txt",
                file_path="C:/tmp/brief.txt",
                mime_type="text/plain",
                file_size=5,
                preview_text="hello",
            )
            insert_message(conn, tenant_id="tenant_demo", session_id="s_001", role="assistant", content="world")
            insert_qa_log(
                conn,
                tenant_id="tenant_demo",
                owner_user_id=user_a["id"],
                session_id="s_001",
                question="hello",
                answer="world",
                status="answered",
                sources=[],
                handoff_required=False,
                confidence="high",
                reason=None,
            )

            own_history = get_session_history(conn, "s_001", tenant_id="tenant_demo", owner_user_id=user_a["id"])
            own_logs = list_qa_logs(conn, tenant_id="tenant_demo", owner_user_id=user_a["id"])
            other_logs = list_qa_logs(conn, tenant_id="tenant_demo", owner_user_id=user_b["id"])

            with self.assertRaises(PermissionError):
                ensure_session(conn, tenant_id="tenant_demo", session_id="s_001", owner_user_id=user_b["id"])

            with self.assertRaises(PermissionError):
                get_session_history(conn, "s_001", tenant_id="tenant_demo", owner_user_id=user_b["id"])

            conn.close()

            self.assertEqual(len(own_history), 2)
            self.assertEqual(len(own_history[0]["attachments"]), 1)
            self.assertEqual(own_history[0]["attachments"][0]["file_name"], "brief.txt")
            self.assertEqual(len(own_logs), 1)
            self.assertEqual(len(other_logs), 0)


if __name__ == "__main__":
    unittest.main()
