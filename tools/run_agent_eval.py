from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_service.agent_tasks import run_demo_task_agent
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


def evaluate_case(result: dict, expected: dict) -> dict:
    checks = {
        "status_match": result.get("status") == expected.get("status"),
        "ticket_match": bool(result.get("ticket")) == bool(expected.get("expects_ticket")),
        "failure_reason_match": expected.get("failure_reason") is None
        or result.get("failure_reason") == expected.get("failure_reason"),
        "order_match": expected.get("order_no") is None
        or str((result.get("order") or {}).get("order_no") or "") == expected.get("order_no"),
        "handoff_match": bool(result.get("handoff_required")) == bool(expected.get("handoff_required")),
    }
    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark cases for the task agent.")
    parser.add_argument("--tenant-id", default="foreign_trade_demo")
    args = parser.parse_args()

    cases = [
        {
            "name": "order_lookup_success",
            "request": "帮我查一下订单 FT-2026-0001 的状态",
            "expected": {
                "status": "success",
                "order_no": "FT-2026-0001",
                "expects_ticket": False,
                "handoff_required": False,
                "failure_reason": None,
            },
        },
        {
            "name": "order_not_found_refusal",
            "request": "帮我查一下订单 FT-2026-9999 的状态",
            "expected": {
                "status": "refused",
                "order_no": None,
                "expects_ticket": False,
                "handoff_required": False,
                "failure_reason": "order_not_found",
            },
        },
        {
            "name": "inventory_shortage_ticket",
            "request": "帮我查一下订单 FT-2026-0002 的库存，不够就创建跟进工单",
            "expected": {
                "status": "success",
                "order_no": "FT-2026-0002",
                "expects_ticket": True,
                "handoff_required": False,
                "failure_reason": None,
            },
        },
        {
            "name": "high_risk_handoff",
            "request": "请直接取消订单 FT-2026-0003 并退款",
            "expected": {
                "status": "handoff",
                "order_no": "FT-2026-0003",
                "expects_ticket": True,
                "handoff_required": True,
                "failure_reason": "unsupported_or_high_risk",
            },
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = make_settings(Path(tmp_dir))
        init_db(settings)
        conn = connect(settings)

        results = []
        for index, case in enumerate(cases, start=1):
            run_result = run_demo_task_agent(
                conn,
                tenant_id=args.tenant_id,
                owner_user_id=f"eval_user_{index}",
                session_id=f"eval_session_{index}",
                user_request=case["request"],
            )
            evaluation = evaluate_case(run_result, case["expected"])
            results.append(
                {
                    "name": case["name"],
                    "request": case["request"],
                    "status": run_result.get("status"),
                    "failure_reason": run_result.get("failure_reason"),
                    "latency_ms": int((run_result.get("metrics") or {}).get("latency_ms") or 0),
                    "ticket_created": bool(run_result.get("ticket")),
                    "hallucination_detected": bool((run_result.get("metrics") or {}).get("hallucination_detected")),
                    "passed": evaluation["passed"],
                    "checks": evaluation["checks"],
                }
            )

        conn.close()

    total = len(results)
    passed_total = sum(1 for item in results if item["passed"])
    refusal_total = sum(1 for item in results if item["status"] == "refused")
    handoff_total = sum(1 for item in results if item["status"] == "handoff")
    hallucination_total = sum(1 for item in results if item["hallucination_detected"])
    avg_latency_ms = int(sum(item["latency_ms"] for item in results) / total) if total else 0

    summary = {
        "total_cases": total,
        "accuracy": round(passed_total / total, 4) if total else 0.0,
        "refusal_rate": round(refusal_total / total, 4) if total else 0.0,
        "hallucination_rate": round(hallucination_total / total, 4) if total else 0.0,
        "handoff_rate": round(handoff_total / total, 4) if total else 0.0,
        "average_latency_ms": avg_latency_ms,
        "cases": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
