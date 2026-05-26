from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TENANT_KB_ROOT = ROOT / "tenant_kb"
TENANT_CONFIG_FILE_NAME = "tenant_config.json"


def sanitize_tenant_id(tenant_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", tenant_id.strip())
    return cleaned[:64].strip("_") or "default"


def tenant_config_path(tenant_id: str, *, base_dir: Path | None = None) -> Path:
    root = base_dir or TENANT_KB_ROOT
    return root / sanitize_tenant_id(tenant_id) / TENANT_CONFIG_FILE_NAME


def _as_tuple(value: object, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return tuple(items) if items else default
    if isinstance(value, str):
        item = value.strip()
        return (item,) if item else default
    return default


def _as_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_category_keywords(
    value: object,
    *,
    default: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    normalized = {key: tuple(items) for key, items in default.items()}
    if not isinstance(value, dict):
        return normalized

    for key, raw_items in value.items():
        category = str(key).strip()
        if not category:
            continue
        items = _as_tuple(raw_items, default=())
        if items:
            normalized[category] = items
    return normalized


def _format_template(template: str, profile: "TenantProfile") -> str:
    try:
        return template.format(
            assistant_name=profile.assistant_name,
            assistant_role=profile.assistant_role,
            faq_category=profile.faq_category,
            allowed_kb_scopes=", ".join(profile.allowed_kb_scopes),
        )
    except (KeyError, AttributeError, ValueError):
        return template


@dataclass(frozen=True)
class TenantProfile:
    assistant_name: str = "小助手"
    assistant_role: str = "通用客服助手"
    identity_aliases: tuple[str, ...] = ("小助手", "客服助手", "通用客服助手")
    allowed_kb_scopes: tuple[str, ...] = ("faq", "policy", "product")
    default_kb_scope: tuple[str, ...] = ("faq", "policy", "product")
    default_top_k: int = 5
    high_risk_terms: tuple[str, ...] = (
        "赔付",
        "索赔",
        "合同",
        "账期",
        "账户变更",
        "清关责任",
        "争议",
        "投诉",
        "责任归属",
    )
    common_terms: tuple[str, ...] = (
        "报价",
        "付款",
        "样品",
        "打样",
        "起订量",
        "moq",
        "定制",
        "交期",
        "物流",
        "清关",
        "发票",
        "订单",
        "包装",
        "质检",
        "售后",
        "合同",
        "退款",
        "退货",
        "运费",
    )
    faq_keywords: tuple[str, ...] = ("faq", "常见问题", "高频问题", "问答", "q&a", "qa")
    faq_category: str = "faq"
    category_keywords: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "faq": ("faq", "常见问题", "高频问题", "问答", "q&a", "qa"),
            "product": ("产品", "规格", "材质", "包装", "logo", "定制", "打样", "样品", "moq", "起订量"),
            "policy": ("规则", "流程", "要求", "政策", "付款", "报价", "订单", "物流", "交期", "发票", "售后", "退换", "退款", "保修", "清关", "合同"),
        }
    )
    blocked_answer: str = "这类问题不按业务问答处理，请直接提出业务问题。"
    identity_answer: str = "我是{assistant_name}，是这套系统里的{assistant_role}，主要负责先接待客户、回答标准问题、整理需求，并在证据不足或风险较高时建议转人工继续处理。"
    handoff_answer: str = "这个问题需要人工客服进一步处理。"
    fallback_answer: str = "当前知识库里没有足够信息回答这个问题，建议换个问法再试，或者转人工处理。"
    llm_system_prompt: str = (
        "你是{assistant_name}，是{assistant_role}。"
        "你只能基于给定证据回答，不能编造报价、账期、赔付、责任归属、合同条款、绝对交期等内容。"
        "如果证据不足，明确说明当前资料不足，并建议补充信息或转人工。"
        "回答尽量先给结论，再补充说明。"
        "语气自然、礼貌、专业，优先中文。"
    )

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None) -> "TenantProfile":
        defaults = cls()
        data = mapping or {}

        assistant_name = str(data.get("assistant_name", defaults.assistant_name)).strip() or defaults.assistant_name
        assistant_role = str(data.get("assistant_role", defaults.assistant_role)).strip() or defaults.assistant_role
        identity_aliases = _as_tuple(data.get("identity_aliases"), default=defaults.identity_aliases)
        if assistant_name not in identity_aliases:
            identity_aliases = (*identity_aliases, assistant_name)
        if assistant_role not in identity_aliases:
            identity_aliases = (*identity_aliases, assistant_role)

        allowed_kb_scopes = _as_tuple(data.get("allowed_kb_scopes"), default=defaults.allowed_kb_scopes)
        default_kb_scope = _as_tuple(data.get("default_kb_scope"), default=defaults.default_kb_scope)
        default_kb_scope = tuple(scope for scope in default_kb_scope if scope in allowed_kb_scopes) or allowed_kb_scopes

        category_keywords = _normalize_category_keywords(
            data.get("category_keywords"),
            default=defaults.category_keywords,
        )
        faq_keywords = _as_tuple(data.get("faq_keywords"), default=defaults.faq_keywords)

        return cls(
            assistant_name=assistant_name,
            assistant_role=assistant_role,
            identity_aliases=identity_aliases,
            allowed_kb_scopes=allowed_kb_scopes,
            default_kb_scope=default_kb_scope,
            default_top_k=_as_int(data.get("default_top_k"), defaults.default_top_k),
            high_risk_terms=_as_tuple(data.get("high_risk_terms"), default=defaults.high_risk_terms),
            common_terms=_as_tuple(data.get("common_terms"), default=defaults.common_terms),
            faq_keywords=faq_keywords,
            faq_category=str(data.get("faq_category", defaults.faq_category)).strip() or defaults.faq_category,
            category_keywords=category_keywords,
            blocked_answer=str(data.get("blocked_answer", defaults.blocked_answer)).strip() or defaults.blocked_answer,
            identity_answer=str(data.get("identity_answer", defaults.identity_answer)).strip() or defaults.identity_answer,
            handoff_answer=str(data.get("handoff_answer", defaults.handoff_answer)).strip() or defaults.handoff_answer,
            fallback_answer=str(data.get("fallback_answer", defaults.fallback_answer)).strip() or defaults.fallback_answer,
            llm_system_prompt=str(data.get("llm_system_prompt", defaults.llm_system_prompt)).strip() or defaults.llm_system_prompt,
        )

    @property
    def identity_keywords(self) -> tuple[str, ...]:
        keywords = [item.strip() for item in (*self.identity_aliases, self.assistant_name, self.assistant_role) if str(item).strip()]
        unique: list[str] = []
        for item in keywords:
            if item not in unique:
                unique.append(item)
        return tuple(unique)

    @property
    def non_faq_categories(self) -> tuple[str, ...]:
        return tuple(category for category in self.allowed_kb_scopes if category and category != self.faq_category)

    @property
    def default_content_category(self) -> str:
        if self.faq_category in self.allowed_kb_scopes:
            return self.faq_category
        return self.non_faq_categories[0] if self.non_faq_categories else self.faq_category

    def category_terms(self, category: str) -> tuple[str, ...]:
        return self.category_keywords.get(category, ())

    def render(self, template: str) -> str:
        return _format_template(template, self)

    def normalize_scopes(self, scopes: list[str] | tuple[str, ...] | None) -> list[str]:
        if scopes:
            normalized = [str(scope).strip() for scope in scopes if str(scope).strip() in self.allowed_kb_scopes]
        else:
            normalized = [scope for scope in self.default_kb_scope if scope in self.allowed_kb_scopes]
        return normalized or list(self.default_kb_scope or self.allowed_kb_scopes)


DEFAULT_TENANT_PROFILE = TenantProfile()


def load_tenant_profile(tenant_id: str, *, base_dir: Path | None = None) -> TenantProfile:
    config_file = tenant_config_path(tenant_id, base_dir=base_dir)
    if not config_file.exists():
        return DEFAULT_TENANT_PROFILE

    raw_text = config_file.read_text(encoding="utf-8").strip()
    if not raw_text:
        return DEFAULT_TENANT_PROFILE

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid tenant profile JSON: {config_file}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"tenant profile must be a JSON object: {config_file}")
    return TenantProfile.from_mapping(payload)

