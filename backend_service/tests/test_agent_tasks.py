from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend_service.agent_tasks import (
    ensure_demo_agent_seed_data,
    get_demo_inventory,
    get_demo_order,
    list_agent_task_runs,
    run_demo_task_agent,
    summarize_agent_task_runs,
)
from backend_service.config import BackendSettings
from backend_service.database import connect, init_db


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


class AgentTaskTests(unittest.TestCase):
    def test_seed_data_and_lookup_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            ensure_demo_agent_seed_data(conn, tenant_id="foreign_trade_demo")
            order = get_demo_order(conn, tenant_id="foreign_trade_demo", order_no="FT-2026-0001")
            inventory = get_demo_inventory(conn, tenant_id="foreign_trade_demo", sku="SKU-MUG-RED")
            conn.close()

            self.assertIsNotNone(order)
            self.assertEqual(order["sku"], "SKU-MUG-RED")
            self.assertIsNotNone(inventory)
            self.assertEqual(inventory["available_qty"], 680)

    def test_run_agent_order_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            result = run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_001",
                user_request="帮我查一下订单 FT-2026-0001 的状态",
            )
            conn.close()

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["task_type"], "order_lookup")
            self.assertEqual(result["order"]["order_no"], "FT-2026-0001")
            self.assertGreaterEqual(len(result["tool_calls"]), 1)

    def test_run_agent_creates_ticket_when_inventory_is_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            result = run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_002",
                user_request="帮我查一下订单 FT-2026-0002 的库存，不够就创建跟进工单",
            )
            conn.close()

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["task_type"], "order_inventory_ticket")
            self.assertIsNotNone(result["ticket"])
            self.assertEqual(result["inventory"]["sku"], "SKU-LAMP-01")

    def test_run_agent_handoffs_high_risk_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            result = run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_003",
                user_request="请直接取消订单 FT-2026-0003 并退款",
            )
            conn.close()

            self.assertEqual(result["status"], "handoff")
            self.assertEqual(result["failure_reason"], "unsupported_or_high_risk")
            self.assertIsNotNone(result["ticket"])

    def test_run_agent_refuses_unknown_order_without_hallucination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            result = run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_004",
                user_request="帮我查一下订单 FT-2026-9999 的状态",
            )
            conn.close()

            self.assertEqual(result["status"], "refused")
            self.assertEqual(result["failure_reason"], "order_not_found")
            self.assertFalse(result["metrics"]["hallucination_detected"])

    def test_agent_run_summary_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = make_settings(Path(tmp_dir))
            init_db(settings)
            conn = connect(settings)

            run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_005",
                user_request="帮我查一下订单 FT-2026-0001 的状态",
            )
            run_demo_task_agent(
                conn,
                tenant_id="foreign_trade_demo",
                owner_user_id="user_001",
                session_id="agent_006",
                user_request="帮我查一下订单 FT-2026-9999 的状态",
            )

            items = list_agent_task_runs(conn, tenant_id="foreign_trade_demo", limit=20)
            summary = summarize_agent_task_runs(conn, tenant_id="foreign_trade_demo", limit=20)
            conn.close()

            self.assertEqual(len(items), 2)
            self.assertEqual(summary["total_runs"], 2)
            self.assertIn("average_latency_ms", summary)


if __name__ == "__main__":
    unittest.main()
