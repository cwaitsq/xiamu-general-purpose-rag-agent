from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from .database import DBConnection, decode_result_json
from .services import new_id, now_iso, redact_sensitive_text, sanitize_tenant_id


ORDER_NO_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{4}-\d{4}\b", re.IGNORECASE)
SKU_PATTERN = re.compile(r"\bSKU-[A-Z0-9-]+\b", re.IGNORECASE)

ORDER_HINTS = ("订单", "order", "发货", "交期", "状态", "进度")
INVENTORY_HINTS = ("库存", "stock", "inventory", "有货")
TICKET_HINTS = ("工单", "ticket", "售后", "投诉", "跟进", "补发", "索赔")
HIGH_RISK_HINTS = ("退款", "改价", "改收款", "取消订单", "修改地址", "直接取消", "直接退款")
AUTO_TICKET_HINTS = ("不够就创建工单", "不足就创建工单", "不够就帮我建工单", "库存不足就创建工单", "不够就创建跟进工单")


def order_db_id(tenant_id: str, order_no: str) -> str:
    return f"{sanitize_tenant_id(tenant_id)}::{order_no.upper()}"


def inventory_db_id(tenant_id: str, sku: str) -> str:
    return f"{sanitize_tenant_id(tenant_id)}::{sku.upper()}"


def ensure_demo_agent_seed_data(conn: DBConnection, *, tenant_id: str) -> None:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    now = now_iso()

    orders = [
        {
            "id": order_db_id(normalized_tenant_id, "FT-2026-0001"),
            "tenant_id": normalized_tenant_id,
            "order_no": "FT-2026-0001",
            "customer_name": "ACME GmbH",
            "sku": "SKU-MUG-RED",
            "quantity": 1200,
            "currency": "USD",
            "amount": 5400.0,
            "status": "pending_payment",
            "eta_date": "2026-06-03",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": order_db_id(normalized_tenant_id, "FT-2026-0002"),
            "tenant_id": normalized_tenant_id,
            "order_no": "FT-2026-0002",
            "customer_name": "Nordic Living",
            "sku": "SKU-LAMP-01",
            "quantity": 300,
            "currency": "USD",
            "amount": 7200.0,
            "status": "production",
            "eta_date": "2026-06-18",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": order_db_id(normalized_tenant_id, "FT-2026-0003"),
            "tenant_id": normalized_tenant_id,
            "order_no": "FT-2026-0003",
            "customer_name": "Blue Harbor",
            "sku": "SKU-CHAIR-07",
            "quantity": 80,
            "currency": "USD",
            "amount": 3600.0,
            "status": "shipped",
            "eta_date": "2026-05-30",
            "created_at": now,
            "updated_at": now,
        },
    ]
    inventory_items = [
        {
            "id": inventory_db_id(normalized_tenant_id, "SKU-MUG-RED"),
            "tenant_id": normalized_tenant_id,
            "sku": "SKU-MUG-RED",
            "available_qty": 680,
            "reserved_qty": 120,
            "updated_at": now,
        },
        {
            "id": inventory_db_id(normalized_tenant_id, "SKU-LAMP-01"),
            "tenant_id": normalized_tenant_id,
            "sku": "SKU-LAMP-01",
            "available_qty": 42,
            "reserved_qty": 90,
            "updated_at": now,
        },
        {
            "id": inventory_db_id(normalized_tenant_id, "SKU-CHAIR-07"),
            "tenant_id": normalized_tenant_id,
            "sku": "SKU-CHAIR-07",
            "available_qty": 0,
            "reserved_qty": 20,
            "updated_at": now,
        },
    ]

    for order in orders:
        conn.execute(
            """
            INSERT INTO demo_orders (
              id, tenant_id, order_no, customer_name, sku, quantity, currency, amount, status, eta_date, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              customer_name=excluded.customer_name,
              sku=excluded.sku,
              quantity=excluded.quantity,
              currency=excluded.currency,
              amount=excluded.amount,
              status=excluded.status,
              eta_date=excluded.eta_date,
              updated_at=excluded.updated_at
            """,
            (
                order["id"],
                order["tenant_id"],
                order["order_no"],
                order["customer_name"],
                order["sku"],
                order["quantity"],
                order["currency"],
                order["amount"],
                order["status"],
                order["eta_date"],
                order["created_at"],
                order["updated_at"],
            ),
        )

    for item in inventory_items:
        conn.execute(
            """
            INSERT INTO demo_inventory (id, tenant_id, sku, available_qty, reserved_qty, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              available_qty=excluded.available_qty,
              reserved_qty=excluded.reserved_qty,
              updated_at=excluded.updated_at
            """,
            (
                item["id"],
                item["tenant_id"],
                item["sku"],
                item["available_qty"],
                item["reserved_qty"],
                item["updated_at"],
            ),
        )

    conn.commit()


def get_demo_order(conn: DBConnection, *, tenant_id: str, order_no: str) -> dict[str, Any] | None:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    row = conn.execute(
        """
        SELECT id, tenant_id, order_no, customer_name, sku, quantity, currency, amount, status, eta_date, created_at, updated_at
        FROM demo_orders
        WHERE id=? AND tenant_id=?
        """,
        (order_db_id(normalized_tenant_id, order_no), normalized_tenant_id),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_demo_inventory(conn: DBConnection, *, tenant_id: str, sku: str) -> dict[str, Any] | None:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    row = conn.execute(
        """
        SELECT id, tenant_id, sku, available_qty, reserved_qty, updated_at
        FROM demo_inventory
        WHERE id=? AND tenant_id=?
        """,
        (inventory_db_id(normalized_tenant_id, sku), normalized_tenant_id),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def create_demo_ticket(
    conn: DBConnection,
    *,
    tenant_id: str,
    owner_user_id: str | None,
    order_no: str | None,
    ticket_type: str,
    title: str,
    detail: str,
) -> dict[str, Any]:
    ticket_id = new_id("ticket")
    created_at = now_iso()
    conn.execute(
        """
        INSERT INTO demo_tickets (id, tenant_id, owner_user_id, order_no, ticket_type, title, detail, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """,
        (
            ticket_id,
            sanitize_tenant_id(tenant_id),
            owner_user_id,
            order_no,
            ticket_type,
            title,
            redact_sensitive_text(detail) or "",
            created_at,
        ),
    )
    conn.commit()
    return {
        "id": ticket_id,
        "tenant_id": sanitize_tenant_id(tenant_id),
        "owner_user_id": owner_user_id,
        "order_no": order_no,
        "ticket_type": ticket_type,
        "title": title,
        "detail": redact_sensitive_text(detail) or "",
        "status": "open",
        "created_at": created_at,
    }


def create_agent_task_run(
    conn: DBConnection,
    *,
    tenant_id: str,
    owner_user_id: str | None,
    session_id: str,
    task_type: str,
    user_request: str,
    outcome_status: str,
    final_message: str,
    tool_calls: list[dict[str, Any]],
    step_logs: list[dict[str, Any]],
    metrics: dict[str, Any],
    result_payload: dict[str, Any],
    failure_reason: str | None,
    created_ticket_id: str | None,
) -> str:
    run_id = new_id("agentrun")
    conn.execute(
        """
        INSERT INTO agent_task_runs (
          id,
          tenant_id,
          owner_user_id,
          session_id,
          task_type,
          user_request,
          outcome_status,
          final_message,
          tool_calls_json,
          step_logs_json,
          metrics_json,
          result_json,
          failure_reason,
          created_ticket_id,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            sanitize_tenant_id(tenant_id),
            owner_user_id,
            session_id,
            task_type,
            redact_sensitive_text(user_request) or "",
            outcome_status,
            redact_sensitive_text(final_message) or "",
            json.dumps(tool_calls, ensure_ascii=False),
            json.dumps(step_logs, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            json.dumps(result_payload, ensure_ascii=False),
            failure_reason,
            created_ticket_id,
            now_iso(),
        ),
    )
    conn.commit()
    return run_id


def serialize_agent_task_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["tool_calls"] = decode_result_json(item.pop("tool_calls_json", "[]")) or []
    item["step_logs"] = decode_result_json(item.pop("step_logs_json", "[]")) or []
    item["metrics"] = decode_result_json(item.pop("metrics_json", "{}")) or {}
    item["result"] = decode_result_json(item.pop("result_json", "{}")) or {}
    return item


def get_agent_task_run(conn: DBConnection, *, tenant_id: str, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, tenant_id, owner_user_id, session_id, task_type, user_request, outcome_status, final_message,
               tool_calls_json, step_logs_json, metrics_json, result_json, failure_reason, created_ticket_id, created_at
        FROM agent_task_runs
        WHERE id=? AND tenant_id=?
        """,
        (run_id, sanitize_tenant_id(tenant_id)),
    ).fetchone()
    return serialize_agent_task_run(row)


def list_agent_task_runs(conn: DBConnection, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, tenant_id, owner_user_id, session_id, task_type, user_request, outcome_status, final_message,
               tool_calls_json, step_logs_json, metrics_json, result_json, failure_reason, created_ticket_id, created_at
        FROM agent_task_runs
        WHERE tenant_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (sanitize_tenant_id(tenant_id), limit),
    ).fetchall()
    return [serialize_agent_task_run(dict(row)) or {} for row in rows]


def summarize_agent_task_runs(conn: DBConnection, *, tenant_id: str, limit: int = 200) -> dict[str, Any]:
    items = list_agent_task_runs(conn, tenant_id=tenant_id, limit=limit)
    total = len(items)
    if total == 0:
        return {
            "total_runs": 0,
            "task_success_rate": 0.0,
            "refusal_rate": 0.0,
            "handoff_rate": 0.0,
            "hallucination_rate": 0.0,
            "average_latency_ms": 0,
        }

    success_runs = sum(1 for item in items if str(item.get("outcome_status") or "") == "success")
    refusal_runs = sum(1 for item in items if str(item.get("outcome_status") or "") == "refused")
    handoff_runs = sum(1 for item in items if str(item.get("outcome_status") or "") == "handoff")
    hallucination_runs = sum(1 for item in items if bool((item.get("metrics") or {}).get("hallucination_detected")))
    latencies = [int((item.get("metrics") or {}).get("latency_ms") or 0) for item in items]

    return {
        "total_runs": total,
        "task_success_rate": round(success_runs / total, 4),
        "refusal_rate": round(refusal_runs / total, 4),
        "handoff_rate": round(handoff_runs / total, 4),
        "hallucination_rate": round(hallucination_runs / total, 4),
        "average_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
    }


def extract_order_no(user_request: str) -> str | None:
    match = ORDER_NO_PATTERN.search(user_request or "")
    if match is None:
        return None
    return match.group(0).upper()


def extract_sku(user_request: str) -> str | None:
    match = SKU_PATTERN.search(user_request or "")
    if match is None:
        return None
    return match.group(0).upper()


def analyze_task_request(user_request: str) -> dict[str, Any]:
    text = (user_request or "").strip()
    lower_text = text.lower()
    order_no = extract_order_no(text)
    sku = extract_sku(text)

    wants_order = bool(order_no) or any(hint in text for hint in ORDER_HINTS)
    wants_inventory = bool(sku) or any(hint in lower_text for hint in INVENTORY_HINTS)
    wants_ticket = any(hint in text for hint in TICKET_HINTS)
    high_risk = any(hint in text for hint in HIGH_RISK_HINTS)
    auto_ticket_on_shortage = any(hint in text for hint in AUTO_TICKET_HINTS)

    if high_risk:
        task_type = "high_risk_handoff"
    elif wants_order and (wants_inventory or auto_ticket_on_shortage) and (wants_ticket or auto_ticket_on_shortage):
        task_type = "order_inventory_ticket"
    elif wants_ticket and wants_order:
        task_type = "order_ticket"
    elif wants_inventory and wants_order:
        task_type = "order_inventory"
    elif wants_inventory:
        task_type = "inventory_lookup"
    elif wants_order:
        task_type = "order_lookup"
    else:
        task_type = "unsupported"

    return {
        "task_type": task_type,
        "order_no": order_no,
        "sku": sku,
        "wants_order": wants_order,
        "wants_inventory": wants_inventory,
        "wants_ticket": wants_ticket,
        "high_risk": high_risk,
        "auto_ticket_on_shortage": auto_ticket_on_shortage,
    }


def _record_step(step_logs: list[dict[str, Any]], *, name: str, status: str, message: str, data: dict[str, Any] | None = None) -> None:
    step_logs.append(
        {
            "name": name,
            "status": status,
            "message": message,
            "data": data or {},
            "created_at": now_iso(),
        }
    )


def _invoke_tool(
    tool_calls: list[dict[str, Any]],
    step_logs: list[dict[str, Any]],
    *,
    tool_name: str,
    input_payload: dict[str, Any],
    callback: Callable[[], dict[str, Any] | None],
    success_message: str,
) -> dict[str, Any] | None:
    started_at = time.perf_counter()
    try:
        output = callback()
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        tool_calls.append(
            {
                "tool_name": tool_name,
                "status": "success",
                "input": input_payload,
                "output": output,
                "latency_ms": latency_ms,
            }
        )
        _record_step(step_logs, name=tool_name, status="success", message=success_message, data={"latency_ms": latency_ms})
        return output
    except Exception as exc:  # pragma: no cover - defensive
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        tool_calls.append(
            {
                "tool_name": tool_name,
                "status": "error",
                "input": input_payload,
                "error": str(exc),
                "latency_ms": latency_ms,
            }
        )
        _record_step(step_logs, name=tool_name, status="error", message=str(exc), data={"latency_ms": latency_ms})
        raise


def run_demo_task_agent(
    conn: DBConnection,
    *,
    tenant_id: str,
    owner_user_id: str | None,
    session_id: str,
    user_request: str,
) -> dict[str, Any]:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    ensure_demo_agent_seed_data(conn, tenant_id=normalized_tenant_id)

    started_at = time.perf_counter()
    tool_calls: list[dict[str, Any]] = []
    step_logs: list[dict[str, Any]] = []
    analysis = analyze_task_request(user_request)
    _record_step(
        step_logs,
        name="plan",
        status="success",
        message=f"识别任务类型为 {analysis['task_type']}",
        data=analysis,
    )

    order: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None

    def finish(
        *,
        outcome_status: str,
        final_message: str,
        failure_reason: str | None = None,
        handoff_required: bool = False,
        next_action: str = "respond",
    ) -> dict[str, Any]:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        result_payload = {
            "status": outcome_status,
            "answer": final_message,
            "handoff_required": handoff_required or outcome_status == "handoff",
            "next_action": next_action,
            "order": order,
            "inventory": inventory,
            "ticket": ticket,
        }
        metrics = {
            "latency_ms": latency_ms,
            "tool_call_count": len(tool_calls),
            "task_completed": outcome_status in {"success", "handoff"} and any([order, inventory, ticket]),
            "refusal": outcome_status == "refused",
            "handoff_required": result_payload["handoff_required"],
            "hallucination_detected": False,
        }
        run_id = create_agent_task_run(
            conn,
            tenant_id=normalized_tenant_id,
            owner_user_id=owner_user_id,
            session_id=session_id,
            task_type=str(analysis["task_type"]),
            user_request=user_request,
            outcome_status=outcome_status,
            final_message=final_message,
            tool_calls=tool_calls,
            step_logs=step_logs,
            metrics=metrics,
            result_payload=result_payload,
            failure_reason=failure_reason,
            created_ticket_id=str((ticket or {}).get("id") or "") or None,
        )
        saved = get_agent_task_run(conn, tenant_id=normalized_tenant_id, run_id=run_id) or {}
        saved.update(result_payload)
        saved["metrics"] = metrics
        saved["tool_calls"] = tool_calls
        saved["step_logs"] = step_logs
        saved["failure_reason"] = failure_reason
        saved["task_type"] = str(analysis["task_type"])
        return saved

    if not str(user_request or "").strip():
        _record_step(step_logs, name="validate_request", status="error", message="任务请求为空")
        return finish(
            outcome_status="refused",
            final_message="任务请求不能为空。",
            failure_reason="empty_request",
            next_action="retry",
        )

    if str(analysis["task_type"]) == "unsupported":
        _record_step(step_logs, name="unsupported_task", status="warning", message="当前任务超出演示 Agent 支持范围")
        return finish(
            outcome_status="handoff",
            final_message="当前演示 Agent 只支持查订单、查库存和创建工单。更复杂的业务操作需要人工跟进。",
            failure_reason="unsupported_task",
            handoff_required=True,
            next_action="human_review",
        )

    if (analysis["wants_order"] or analysis["high_risk"]) and not analysis["order_no"]:
        _record_step(step_logs, name="missing_order_no", status="warning", message="缺少订单号，无法继续执行")
        return finish(
            outcome_status="handoff",
            final_message="请提供明确的订单号后再执行，当前演示 Agent 不会在缺少关键标识时继续猜测。",
            failure_reason="missing_order_no",
            handoff_required=True,
            next_action="request_order_no",
        )

    if analysis["order_no"]:
        order = _invoke_tool(
            tool_calls,
            step_logs,
            tool_name="lookup_order",
            input_payload={"tenant_id": normalized_tenant_id, "order_no": analysis["order_no"]},
            callback=lambda: get_demo_order(conn, tenant_id=normalized_tenant_id, order_no=str(analysis["order_no"])),
            success_message="已调用订单查询工具",
        )
        if order is None:
            _record_step(step_logs, name="lookup_order", status="warning", message="未查到订单，终止后续操作")
            return finish(
                outcome_status="refused",
                final_message=f"未查到订单 {analysis['order_no']}，因此没有继续调用库存或工单工具。",
                failure_reason="order_not_found",
                next_action="verify_order_no",
            )

    resolved_sku = str(analysis["sku"] or (order or {}).get("sku") or "").strip().upper() or None
    if analysis["wants_inventory"] or analysis["auto_ticket_on_shortage"]:
        if not resolved_sku:
            _record_step(step_logs, name="missing_sku", status="warning", message="没有 SKU，无法检查库存")
            return finish(
                outcome_status="handoff",
                final_message="没有识别到 SKU，无法继续检查库存，建议补充 SKU 或转人工处理。",
                failure_reason="missing_sku",
                handoff_required=True,
                next_action="request_sku",
            )
        inventory = _invoke_tool(
            tool_calls,
            step_logs,
            tool_name="lookup_inventory",
            input_payload={"tenant_id": normalized_tenant_id, "sku": resolved_sku},
            callback=lambda: get_demo_inventory(conn, tenant_id=normalized_tenant_id, sku=resolved_sku),
            success_message="已调用库存查询工具",
        )
        if inventory is None:
            _record_step(step_logs, name="lookup_inventory", status="warning", message="库存不存在")
            return finish(
                outcome_status="refused",
                final_message=f"没有查到 SKU {resolved_sku} 的库存记录，因此未继续执行。",
                failure_reason="inventory_not_found",
                next_action="verify_sku",
            )

    shortage_detected = bool(order and inventory and int(inventory.get("available_qty") or 0) < int(order.get("quantity") or 0))

    if analysis["high_risk"]:
        ticket = _invoke_tool(
            tool_calls,
            step_logs,
            tool_name="create_ticket",
            input_payload={"order_no": analysis["order_no"], "ticket_type": "human_handoff"},
            callback=lambda: create_demo_ticket(
                conn,
                tenant_id=normalized_tenant_id,
                owner_user_id=owner_user_id,
                order_no=str(analysis["order_no"]),
                ticket_type="human_handoff",
                title=f"高风险操作人工跟进 {analysis['order_no']}",
                detail=user_request,
            ),
            success_message="已创建人工跟进工单",
        )
        return finish(
            outcome_status="handoff",
            final_message=f"订单 {analysis['order_no']} 涉及高风险操作，我没有直接执行，已创建人工跟进工单 {ticket['id']}。",
            failure_reason="unsupported_or_high_risk",
            handoff_required=True,
            next_action="human_review",
        )

    if analysis["wants_ticket"] or analysis["auto_ticket_on_shortage"]:
        if not order:
            _record_step(step_logs, name="ticket_requires_order", status="warning", message="创建工单前必须先定位订单")
            return finish(
                outcome_status="handoff",
                final_message="创建工单前需要订单上下文，请先提供订单号。",
                failure_reason="missing_order_context",
                handoff_required=True,
                next_action="request_order_no",
            )
        if analysis["auto_ticket_on_shortage"] and not shortage_detected:
            _record_step(step_logs, name="skip_ticket", status="success", message="库存未短缺，无需自动建工单")
            return finish(
                outcome_status="success",
                final_message=(
                    f"订单 {order['order_no']} 当前状态为 {order['status']}，SKU {order['sku']} 可用库存 {inventory['available_qty']}，"
                    "库存未出现短缺，因此没有创建跟进工单。"
                ),
                next_action="respond",
            )

        ticket_type = "inventory_follow_up" if shortage_detected else "customer_follow_up"
        ticket = _invoke_tool(
            tool_calls,
            step_logs,
            tool_name="create_ticket",
            input_payload={"order_no": order["order_no"], "ticket_type": ticket_type},
            callback=lambda: create_demo_ticket(
                conn,
                tenant_id=normalized_tenant_id,
                owner_user_id=owner_user_id,
                order_no=str(order["order_no"]),
                ticket_type=ticket_type,
                title=f"订单跟进 {order['order_no']}",
                detail=user_request,
            ),
            success_message="已创建工单",
        )
        if shortage_detected:
            return finish(
                outcome_status="success",
                final_message=(
                    f"订单 {order['order_no']} 当前状态为 {order['status']}，SKU {order['sku']} 可用库存 {inventory['available_qty']}，"
                    f"低于订单数量 {order['quantity']}，已自动创建跟进工单 {ticket['id']}。"
                ),
                next_action="monitor_ticket",
            )
        return finish(
            outcome_status="success",
            final_message=f"已为订单 {order['order_no']} 创建跟进工单 {ticket['id']}，可继续由人工或后续流程处理。",
            next_action="monitor_ticket",
        )

    if inventory and order:
        return finish(
            outcome_status="success",
            final_message=(
                f"订单 {order['order_no']} 当前状态为 {order['status']}，SKU {order['sku']} 可用库存 {inventory['available_qty']}，"
                f"预留库存 {inventory['reserved_qty']}。"
            ),
            next_action="respond",
        )

    if inventory and not order:
        return finish(
            outcome_status="success",
            final_message=f"SKU {inventory['sku']} 当前可用库存 {inventory['available_qty']}，预留库存 {inventory['reserved_qty']}。",
            next_action="respond",
        )

    if order:
        return finish(
            outcome_status="success",
            final_message=(
                f"已查到订单 {order['order_no']}，客户 {order['customer_name']}，状态 {order['status']}，"
                f"SKU {order['sku']}，数量 {order['quantity']}，预计日期 {order['eta_date']}。"
            ),
            next_action="respond",
        )

    _record_step(step_logs, name="fallback", status="warning", message="没有可执行结果，转人工")
    return finish(
        outcome_status="handoff",
        final_message="当前请求没有匹配到可执行的任务模板，建议转人工跟进。",
        failure_reason="no_matching_action",
        handoff_required=True,
        next_action="human_review",
    )
