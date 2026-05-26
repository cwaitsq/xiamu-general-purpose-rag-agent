from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend_service.config import BackendSettings
from backend_service.server import create_app


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


class AgentRouteTests(unittest.TestCase):
    def test_demo_agent_route_returns_task_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            with patch("backend_service.server.load_settings", return_value=settings):
                app = create_app()
            try:
                client = app.test_client()

                response = client.post(
                    "/api/demo/agent/tasks/run",
                    json={"tenant_id": "foreign_trade_demo", "request": "帮我查一下订单 FT-2026-0001 的状态"},
                )
                payload = response.get_json()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload["data"]["status"], "success")
                self.assertEqual(payload["data"]["order"]["order_no"], "FT-2026-0001")
            finally:
                app.config["DB_CONN"].close()

    def test_admin_agent_metrics_route_requires_auth_and_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            with patch("backend_service.server.load_settings", return_value=settings):
                app = create_app()
            try:
                client = app.test_client()

                login_response = client.post(
                    "/api/auth/login",
                    json={
                        "tenant_id": "foreign_trade_demo",
                        "email": "admin@foreigntrade.local",
                        "password": "Admin@123456",
                    },
                )
                token = login_response.get_json()["data"]["token"]

                client.post(
                    "/api/agent/tasks/run",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"session_id": "agent_route_001", "request": "帮我查一下订单 FT-2026-0002 的库存，不够就创建跟进工单"},
                )

                response = client.get(
                    "/api/admin/agent/tasks/metrics",
                    headers={"Authorization": f"Bearer {token}"},
                )
                payload = response.get_json()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload["data"]["total_runs"], 1)
                self.assertIn("task_success_rate", payload["data"])
            finally:
                app.config["DB_CONN"].close()


if __name__ == "__main__":
    unittest.main()
