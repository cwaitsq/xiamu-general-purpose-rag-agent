from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .tenant_paths import DEFAULT_TENANT_ID
from shared.tenant_profile import TenantProfile, load_tenant_profile


MAX_SESSION_ID_CHARS = 64
MAX_QUESTION_CHARS = 2000
MAX_HISTORY_ITEMS = 8
MAX_HISTORY_TOTAL_CHARS = 4000


@dataclass
class HistoryItem:
    role: str
    content: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "HistoryItem":
        role = str(data.get("role", "")).strip()
        content = str(data.get("content", "")).strip()
        if role not in {"user", "assistant"}:
            raise ValueError("history.role 只允许是 user 或 assistant")
        if not content:
            raise ValueError("history.content 不能为空")
        return cls(role=role, content=content)


@dataclass
class QueryRequest:
    tenant_id: str
    session_id: str
    question: str
    history: list[HistoryItem] = field(default_factory=list)
    kb_scope: list[str] = field(default_factory=list)
    mode: str = "qa"
    top_k: int = 5

    @classmethod
    def from_dict(cls, data: dict[str, object], *, profile: TenantProfile | None = None) -> "QueryRequest":
        session_id = str(data.get("session_id", "")).strip()
        question = str(data.get("question", "")).strip()
        if not session_id:
            raise ValueError("session_id 不能为空")
        if not question:
            raise ValueError("question 不能为空")
        if len(session_id) > MAX_SESSION_ID_CHARS:
            raise ValueError(f"session_id 不能超过 {MAX_SESSION_ID_CHARS} 个字符")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(f"question 不能超过 {MAX_QUESTION_CHARS} 个字符")

        raw_history = data.get("history", [])
        history: list[HistoryItem] = []
        if isinstance(raw_history, list):
            history = [HistoryItem.from_dict(item) for item in raw_history if isinstance(item, dict)]
        if len(history) > MAX_HISTORY_ITEMS:
            history = history[-MAX_HISTORY_ITEMS:]
        if sum(len(item.content) for item in history) > MAX_HISTORY_TOTAL_CHARS:
            raise ValueError(f"history 内容过长，总长度不能超过 {MAX_HISTORY_TOTAL_CHARS} 个字符")

        tenant_id = str(data.get("tenant_id", DEFAULT_TENANT_ID)).strip() or DEFAULT_TENANT_ID
        active_profile = profile or load_tenant_profile(tenant_id)

        raw_scope = data.get("kb_scope", list(active_profile.default_kb_scope))
        kb_scope = active_profile.normalize_scopes(raw_scope if isinstance(raw_scope, list) else None)

        raw_top_k = data.get("top_k", active_profile.default_top_k)
        try:
            top_k = int(raw_top_k)
        except (TypeError, ValueError):
            top_k = active_profile.default_top_k
        top_k = max(1, min(top_k or active_profile.default_top_k, 10))

        return cls(
            tenant_id=tenant_id,
            session_id=session_id,
            question=question,
            history=history,
            kb_scope=kb_scope,
            mode=str(data.get("mode", "qa")).strip() or "qa",
            top_k=top_k,
        )


@dataclass
class SourceItem:
    doc_id: str
    title: str
    chunk_id: str


@dataclass
class QueryResponse:
    status: str
    answer: str
    sources: list[SourceItem] = field(default_factory=list)
    confidence: str = "low"
    handoff_required: bool = False
    reason: str | None = None
    answer_mode: str = "rule"
    llm_model: str | None = None
    retrieval_backend: str | None = None
    used_llm: bool = False
    next_action: str = "respond"
    timings: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

