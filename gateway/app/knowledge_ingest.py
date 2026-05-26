from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .knowledge_prepare import run_knowledge_prepare
from .rag_clients import HttpJsonError, QmdClient
from .tenant_paths import DEFAULT_TENANT_ID, TenantWorkspace, ensure_workspace_bootstrap, get_tenant_workspace
from shared.tenant_profile import DEFAULT_TENANT_PROFILE, TenantProfile, load_tenant_profile


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = ROOT / "知识库"
DOCS_DIR = KNOWLEDGE_ROOT / "已整理知识"
OUTPUT_DIR = KNOWLEDGE_ROOT / "切片结果"
CHUNKS_FILE = OUTPUT_DIR / "chunks.jsonl"
PREVIEW_FILE = OUTPUT_DIR / "切片预览.md"
REPORT_FILE = OUTPUT_DIR / "知识入库报告.json"
LEGACY_AUTO_DIR_NAMES = {"自动整理"}

REQUIRED_META_FIELDS = ("kb_id", "title", "category", "status", "version", "visibility", "source")
ALLOWED_CATEGORIES = {"faq", "policy", "product"}
ALLOWED_STATUSES = {"active", "inactive", "draft"}
ALLOWED_VISIBILITIES = {"external", "internal"}
FAQ_HEADING_RE = re.compile(r"^##\s*(问|Q)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class KnowledgeDoc:
    file_name: str
    path: Path
    meta: dict[str, str]
    body: str


@dataclass
class KnowledgeChunk:
    tenant_id: str
    chunk_id: str
    kb_id: str
    title: str
    category: str
    status: str
    visibility: str
    source_file: str
    section_title: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class KnowledgeIngestResult:
    status: str
    message: str
    validate_only: bool
    refresh_index: bool
    prepare_raw: bool
    docs_total: int
    chunks_total: int
    index_status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    docs: list[dict[str, Any]] = field(default_factory=list)
    prepare_result: dict[str, Any] | None = None
    report_file: str | None = None
    chunk_file: str | None = None
    preview_file: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_knowledge_ingest(
    *,
    validate_only: bool = False,
    refresh_index: bool = True,
    prepare_raw: bool = False,
    publish_status: str = "draft",
    prepare_use_llm: bool = False,
    settings: Settings | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    target_file_path: str | None = None,
) -> KnowledgeIngestResult:
    started_at = _iso_now()
    active_settings = settings or load_settings()
    workspace = get_tenant_workspace(tenant_id, collection_base=active_settings.qmd_collection)
    ensure_workspace_bootstrap(workspace)
    prepare_result_payload: dict[str, Any] | None = None
    prepare_warnings: list[str] = []

    if prepare_raw and validate_only:
        result = KnowledgeIngestResult(
            status="failed",
            message="prepare_raw 不能和 validate_only 一起使用",
            validate_only=validate_only,
            refresh_index=refresh_index,
            prepare_raw=prepare_raw,
            docs_total=0,
            chunks_total=0,
            index_status="skipped",
            errors=["prepare_raw 不能和 validate_only 一起使用"],
            warnings=[],
            docs=[],
            prepare_result=None,
            report_file=str(workspace.ingest_report_file),
            chunk_file=str(workspace.chunks_file),
            preview_file=str(workspace.ingest_preview_file),
            started_at=started_at,
            finished_at=_iso_now(),
        )
        write_report(result, workspace=workspace)
        return result

    if prepare_raw:
        prepare_result = run_knowledge_prepare(
            validate_only=False,
            publish_status=publish_status,
            use_llm=prepare_use_llm,
            settings=active_settings,
            tenant_id=tenant_id,
            target_file_path=target_file_path,
        )
        prepare_result_payload = prepare_result.to_dict()
        prepare_warnings.extend(prepare_result.warnings)
        if prepare_result.status != "success":
            result = KnowledgeIngestResult(
                status="failed",
                message="原始资料整理失败",
                validate_only=validate_only,
                refresh_index=refresh_index,
                prepare_raw=prepare_raw,
                docs_total=0,
                chunks_total=0,
                index_status="skipped",
                errors=list(prepare_result.errors),
                warnings=list(prepare_result.warnings),
                docs=[],
                prepare_result=prepare_result_payload,
                report_file=str(workspace.ingest_report_file),
                chunk_file=str(workspace.chunks_file),
                preview_file=str(workspace.ingest_preview_file),
                started_at=started_at,
                finished_at=_iso_now(),
            )
            write_report(result, workspace=workspace)
            return result

    docs, errors, warnings = load_and_validate_docs(docs_dir=workspace.docs_dir)
    warnings.extend(prepare_warnings)
    chunks: list[KnowledgeChunk] = []
    docs_payload: list[dict[str, Any]] = []

    if not errors:
        chunks = build_chunks(docs, errors, tenant_id=tenant_id)
        docs_payload = build_docs_payload(docs, chunks, tenant_id=tenant_id)

    result = KnowledgeIngestResult(
        status="failed" if errors else "success",
        message="知识文档校验通过" if not errors else "知识文档校验失败",
        validate_only=validate_only,
        refresh_index=refresh_index,
        prepare_raw=prepare_raw,
        docs_total=len(docs),
        chunks_total=len(chunks),
        index_status="skipped" if validate_only or errors or not refresh_index else "pending",
        errors=errors,
        warnings=warnings,
        docs=docs_payload,
        prepare_result=prepare_result_payload,
        report_file=str(workspace.ingest_report_file),
        chunk_file=str(workspace.chunks_file),
        preview_file=str(workspace.ingest_preview_file),
        started_at=started_at,
    )

    if not errors and not validate_only:
        write_chunk_outputs(chunks, workspace=workspace)
        result.message = "知识切片已生成"
        if refresh_index:
            index_status, index_message = refresh_qmd_index(active_settings, workspace=workspace)
            result.index_status = index_status
            if index_status != "updated":
                result.status = "failed"
                result.message = index_message
                result.errors.append(index_message)
            else:
                result.message = "知识入库完成，qmd 索引已刷新"
                if prepare_raw:
                    result.message = "原始资料整理完成，知识入库完成，qmd 索引已刷新"
        else:
            result.index_status = "skipped"
            result.message = "知识切片已生成，未刷新 qmd 索引"
            if prepare_raw:
                result.message = "原始资料整理完成，知识切片已生成，未刷新 qmd 索引"

    result.finished_at = _iso_now()
    write_report(result, workspace=workspace)
    return result


def load_and_validate_docs(*, docs_dir: Path) -> tuple[list[KnowledgeDoc], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not docs_dir.exists():
        return [], [f"未找到知识目录：{docs_dir}"], warnings

    doc_paths = sorted(iter_doc_paths(docs_dir))
    if not doc_paths:
        return [], [f"知识目录里没有 Markdown 文档：{docs_dir}"], warnings

    docs: list[KnowledgeDoc] = []
    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter_and_body(text)
        docs.append(
            KnowledgeDoc(
                file_name=path.name,
                path=path,
                meta=meta,
                body=body,
            )
        )

    validate_docs(docs, errors, warnings)
    return docs, errors, warnings


def iter_doc_paths(docs_dir: Path) -> list[Path]:
    if not docs_dir.exists():
        return []

    auto_dir = docs_dir / "auto"
    skip_dirs: set[Path] = set()
    if auto_dir.exists() and any(auto_dir.rglob("*.md")):
        for child in docs_dir.iterdir():
            if child.is_dir() and child.name in LEGACY_AUTO_DIR_NAMES:
                skip_dirs.add(child.resolve())

    paths: list[Path] = []
    for path in docs_dir.rglob("*.md"):
        resolved = path.resolve()
        if any(skip_dir in resolved.parents for skip_dir in skip_dirs):
            continue
        paths.append(path)
    return paths


def validate_docs(docs: list[KnowledgeDoc], errors: list[str], warnings: list[str]) -> None:
    kb_ids: dict[str, str] = {}

    for doc in docs:
        if not doc.meta:
            errors.append(f"{doc.file_name} 缺少 frontmatter")
            continue

        for field_name in REQUIRED_META_FIELDS:
            if not doc.meta.get(field_name, "").strip():
                errors.append(f"{doc.file_name} 缺少字段：{field_name}")

        kb_id = doc.meta.get("kb_id", "").strip()
        if kb_id:
            if kb_id in kb_ids:
                errors.append(f"{doc.file_name} 的 kb_id 和 {kb_ids[kb_id]} 重复：{kb_id}")
            else:
                kb_ids[kb_id] = doc.file_name

        category = doc.meta.get("category", "").strip()
        if category and category not in ALLOWED_CATEGORIES:
            errors.append(f"{doc.file_name} 的 category 不支持：{category}")

        status = doc.meta.get("status", "").strip()
        if status and status not in ALLOWED_STATUSES:
            errors.append(f"{doc.file_name} 的 status 不支持：{status}")

        visibility = doc.meta.get("visibility", "").strip()
        if visibility and visibility not in ALLOWED_VISIBILITIES:
            errors.append(f"{doc.file_name} 的 visibility 不支持：{visibility}")

        version = doc.meta.get("version", "").strip()
        if version and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
            warnings.append(f"{doc.file_name} 的 version 建议用 YYYY-MM-DD：{version}")

        if not doc.body.strip():
            errors.append(f"{doc.file_name} 正文为空")
            continue

        category = doc.meta.get("category", "").strip()
        if category == "faq":
            faq_sections = split_faq_chunks(doc.body)
            if not faq_sections:
                errors.append(f"{doc.file_name} 是 faq，但没有识别到“## 问：”结构")
        else:
            heading_sections = split_heading_chunks(doc.body)
            if not heading_sections:
                warnings.append(f"{doc.file_name} 没有二级标题，将按整篇文档入一个切片")

        if doc.meta.get("visibility") == "internal":
            warnings.append(f"{doc.file_name} 是 internal，只能给内部链路用")


def parse_frontmatter_and_body(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    raw_meta = parts[1]
    body = parts[2].lstrip()
    meta: dict[str, str] = {}
    for raw_line in raw_meta.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body


def split_faq_chunks(body: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_question = ""
    current_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        matched = FAQ_HEADING_RE.match(line)
        if matched:
            if current_question:
                chunks.append((current_question, clean_text("\n".join(current_lines))))
            current_question = matched.group(2).strip()
            current_lines = []
            continue
        if current_question:
            current_lines.append(line)

    if current_question:
        chunks.append((current_question, clean_text("\n".join(current_lines))))
    return [(question, answer) for question, answer in chunks if question and answer]


def split_heading_chunks(body: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_title:
                chunks.append((current_title, clean_text("\n".join(current_lines))))
            current_title = line.removeprefix("## ").strip()
            current_lines = []
            continue
        if line.startswith("# "):
            continue
        if current_title:
            current_lines.append(line)

    if current_title:
        chunks.append((current_title, clean_text("\n".join(current_lines))))

    if chunks:
        return [(section_title, text) for section_title, text in chunks if section_title and text]

    fallback_text = clean_text(body)
    if fallback_text:
        return [("正文", fallback_text)]
    return []


def build_chunks(docs: list[KnowledgeDoc], errors: list[str], *, tenant_id: str) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []

    for doc in docs:
        if not doc.meta:
            continue

        category = doc.meta["category"]
        title = doc.meta["title"]
        kb_id = doc.meta["kb_id"]
        status = doc.meta["status"]
        visibility = doc.meta["visibility"]

        if category == "faq":
            sections = split_faq_chunks(doc.body)
            for index, (question, answer) in enumerate(sections, start=1):
                chunks.append(
                    KnowledgeChunk(
                        tenant_id=tenant_id,
                        chunk_id=f"{kb_id}_{index:03d}",
                        kb_id=kb_id,
                        title=title,
                        category=category,
                        status=status,
                        visibility=visibility,
                        source_file=doc.file_name,
                        section_title=f"问答{index}",
                        text=clean_text(f"问题：{question}\n{answer}"),
                    )
                )
            continue

        sections = split_heading_chunks(doc.body)
        for index, (section_title, section_text) in enumerate(sections, start=1):
            chunks.append(
                KnowledgeChunk(
                    tenant_id=tenant_id,
                    chunk_id=f"{kb_id}_{index:03d}",
                    kb_id=kb_id,
                    title=title,
                    category=category,
                    status=status,
                    visibility=visibility,
                    source_file=doc.file_name,
                    section_title=section_title,
                    text=section_text,
                )
            )

    if not chunks and not errors:
        errors.append("没有生成任何知识切片")
    return chunks


def clean_text(text: str) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text.strip())
    return "\n".join(line.rstrip() for line in compact.splitlines()).strip()


def build_docs_payload(docs: list[KnowledgeDoc], chunks: list[KnowledgeChunk], *, tenant_id: str) -> list[dict[str, Any]]:
    chunk_count_by_file: dict[str, int] = {}
    for chunk in chunks:
        chunk_count_by_file[chunk.source_file] = chunk_count_by_file.get(chunk.source_file, 0) + 1

    payload: list[dict[str, Any]] = []
    for doc in docs:
        meta = doc.meta
        payload.append(
            {
                "tenant_id": tenant_id,
                "file_name": doc.file_name,
                "kb_id": meta.get("kb_id"),
                "title": meta.get("title"),
                "category": meta.get("category"),
                "status": meta.get("status"),
                "visibility": meta.get("visibility"),
                "version": meta.get("version"),
                "chunk_count": chunk_count_by_file.get(doc.file_name, 0),
            }
        )
    return payload


def write_chunk_outputs(chunks: list[KnowledgeChunk], *, workspace: TenantWorkspace) -> None:
    workspace.ingest_output_dir.mkdir(parents=True, exist_ok=True)

    with workspace.chunks_file.open("w", encoding="utf-8") as chunks_file:
        for chunk in chunks:
            chunks_file.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

    preview_lines = ["# 切片预览", ""]
    for chunk in chunks:
        preview_lines.extend(
            [
                f"## {chunk.chunk_id}",
                f"- 文档标题：{chunk.title}",
                f"- 分类：{chunk.category}",
                f"- 小节：{chunk.section_title}",
                f"- 来源文件：{chunk.source_file}",
                "",
                chunk.text,
                "",
            ]
        )

    workspace.ingest_preview_file.write_text("\n".join(preview_lines), encoding="utf-8")


def refresh_qmd_index(settings: Settings, *, workspace: TenantWorkspace) -> tuple[str, str]:
    client = QmdClient(settings)
    if not client.is_configured():
        return "failed", "未找到 qmd 配置，请先检查 QMD_CLI_PATH 或 QMD_COMMAND"

    index_dir = ROOT / ".qmd"
    if not index_dir.exists():
        client.init_index()

    try:
        exists = client.collection_exists(workspace.collection_name)
    except HttpJsonError as exc:
        return "failed", f"检查 qmd collection 失败：{exc}"

    if not exists:
        try:
            client.add_collection(str(workspace.docs_dir), workspace.collection_name)
        except HttpJsonError as exc:
            return "failed", f"创建 qmd collection 失败：{exc}"

    try:
        client.update()
    except HttpJsonError as exc:
        return "failed", f"刷新 qmd 索引失败：{exc}"
    return "updated", "qmd 索引刷新完成"


def write_report(result: KnowledgeIngestResult, *, workspace: TenantWorkspace) -> None:
    workspace.ingest_output_dir.mkdir(parents=True, exist_ok=True)
    workspace.ingest_report_file.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_knowledge_ingest(
    *,
    validate_only: bool = False,
    refresh_index: bool = True,
    prepare_raw: bool = False,
    publish_status: str = "draft",
    prepare_use_llm: bool = False,
    settings: Settings | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    target_file_path: str | None = None,
) -> KnowledgeIngestResult:
    started_at = _iso_now()
    active_settings = settings or load_settings()
    profile = load_tenant_profile(tenant_id)
    workspace = get_tenant_workspace(tenant_id, collection_base=active_settings.qmd_collection)
    ensure_workspace_bootstrap(workspace)
    prepare_result_payload: dict[str, Any] | None = None
    prepare_warnings: list[str] = []

    if prepare_raw and validate_only:
        result = KnowledgeIngestResult(
            status="failed",
            message="prepare_raw 不能和 validate_only 一起使用",
            validate_only=validate_only,
            refresh_index=refresh_index,
            prepare_raw=prepare_raw,
            docs_total=0,
            chunks_total=0,
            index_status="skipped",
            errors=["prepare_raw 不能和 validate_only 一起使用"],
            warnings=[],
            docs=[],
            prepare_result=None,
            report_file=str(workspace.ingest_report_file),
            chunk_file=str(workspace.chunks_file),
            preview_file=str(workspace.ingest_preview_file),
            started_at=started_at,
            finished_at=_iso_now(),
        )
        write_report(result, workspace=workspace)
        return result

    if prepare_raw:
        prepare_result = run_knowledge_prepare(
            validate_only=False,
            publish_status=publish_status,
            use_llm=prepare_use_llm,
            settings=active_settings,
            tenant_id=tenant_id,
            target_file_path=target_file_path,
        )
        prepare_result_payload = prepare_result.to_dict()
        prepare_warnings.extend(prepare_result.warnings)
        if prepare_result.status != "success":
            result = KnowledgeIngestResult(
                status="failed",
                message="原始材料整理失败",
                validate_only=validate_only,
                refresh_index=refresh_index,
                prepare_raw=prepare_raw,
                docs_total=0,
                chunks_total=0,
                index_status="skipped",
                errors=list(prepare_result.errors),
                warnings=list(prepare_result.warnings),
                docs=[],
                prepare_result=prepare_result_payload,
                report_file=str(workspace.ingest_report_file),
                chunk_file=str(workspace.chunks_file),
                preview_file=str(workspace.ingest_preview_file),
                started_at=started_at,
                finished_at=_iso_now(),
            )
            write_report(result, workspace=workspace)
            return result

    docs, errors, warnings = load_and_validate_docs(docs_dir=workspace.docs_dir, profile=profile)
    warnings.extend(prepare_warnings)
    chunks: list[KnowledgeChunk] = []
    docs_payload: list[dict[str, Any]] = []

    if not errors:
        chunks = build_chunks(docs, errors, tenant_id=tenant_id, profile=profile)
        docs_payload = build_docs_payload(docs, chunks, tenant_id=tenant_id)

    result = KnowledgeIngestResult(
        status="failed" if errors else "success",
        message="知识文档校验通过" if not errors else "知识文档校验失败",
        validate_only=validate_only,
        refresh_index=refresh_index,
        prepare_raw=prepare_raw,
        docs_total=len(docs),
        chunks_total=len(chunks),
        index_status="skipped" if validate_only or errors or not refresh_index else "pending",
        errors=errors,
        warnings=warnings,
        docs=docs_payload,
        prepare_result=prepare_result_payload,
        report_file=str(workspace.ingest_report_file),
        chunk_file=str(workspace.chunks_file),
        preview_file=str(workspace.ingest_preview_file),
        started_at=started_at,
    )

    if not errors and not validate_only:
        write_chunk_outputs(chunks, workspace=workspace)
        result.message = "知识切片已生成"
        if refresh_index:
            index_status, index_message = refresh_qmd_index(active_settings, workspace=workspace)
            result.index_status = index_status
            if index_status != "updated":
                result.status = "failed"
                result.message = index_message
                result.errors.append(index_message)
            else:
                result.message = "知识入库完成，qmd 索引已刷新"
                if prepare_raw:
                    result.message = "原始材料整理完成，知识入库完成，qmd 索引已刷新"
        else:
            result.index_status = "skipped"
            result.message = "知识切片已生成，未刷新 qmd 索引"
            if prepare_raw:
                result.message = "原始材料整理完成，知识切片已生成，未刷新 qmd 索引"

    result.finished_at = _iso_now()
    write_report(result, workspace=workspace)
    return result


def load_and_validate_docs(
    *,
    docs_dir: Path,
    profile: TenantProfile | None = None,
) -> tuple[list[KnowledgeDoc], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not docs_dir.exists():
        return [], [f"未找到知识目录：{docs_dir}"], warnings

    doc_paths = sorted(iter_doc_paths(docs_dir))
    if not doc_paths:
        return [], [f"知识目录里没有 Markdown 文档：{docs_dir}"], warnings

    docs: list[KnowledgeDoc] = []
    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter_and_body(text)
        docs.append(
            KnowledgeDoc(
                file_name=path.name,
                path=path,
                meta=meta,
                body=body,
            )
        )

    validate_docs(docs, errors, warnings, profile=profile)
    return docs, errors, warnings


def validate_docs(
    docs: list[KnowledgeDoc],
    errors: list[str],
    warnings: list[str],
    *,
    profile: TenantProfile | None = None,
) -> None:
    active_profile = profile or DEFAULT_TENANT_PROFILE
    kb_ids: dict[str, str] = {}

    for doc in docs:
        if not doc.meta:
            errors.append(f"{doc.file_name} 缺少 frontmatter")
            continue

        for field_name in REQUIRED_META_FIELDS:
            if not doc.meta.get(field_name, "").strip():
                errors.append(f"{doc.file_name} 缺少字段：{field_name}")

        kb_id = doc.meta.get("kb_id", "").strip()
        if kb_id:
            if kb_id in kb_ids:
                errors.append(f"{doc.file_name} 的 kb_id 和 {kb_ids[kb_id]} 重复：{kb_id}")
            else:
                kb_ids[kb_id] = doc.file_name

        category = doc.meta.get("category", "").strip()
        if category and category not in active_profile.allowed_kb_scopes:
            errors.append(f"{doc.file_name} 的 category 不支持：{category}")

        status = doc.meta.get("status", "").strip()
        if status and status not in ALLOWED_STATUSES:
            errors.append(f"{doc.file_name} 的 status 不支持：{status}")

        visibility = doc.meta.get("visibility", "").strip()
        if visibility and visibility not in ALLOWED_VISIBILITIES:
            errors.append(f"{doc.file_name} 的 visibility 不支持：{visibility}")

        version = doc.meta.get("version", "").strip()
        if version and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
            warnings.append(f"{doc.file_name} 的 version 建议写成 YYYY-MM-DD：{version}")

        if not doc.body.strip():
            errors.append(f"{doc.file_name} 正文为空")
            continue

        category = doc.meta.get("category", "").strip()
        if category == active_profile.faq_category:
            faq_sections = split_faq_chunks(doc.body)
            if not faq_sections:
                errors.append(f"{doc.file_name} 是 FAQ，但没有识别到 '# 问：' 结构")
        else:
            heading_sections = split_heading_chunks(doc.body)
            if not heading_sections:
                warnings.append(f"{doc.file_name} 没有二级标题，将按整篇文档切片。")

        if doc.meta.get("visibility") == "internal":
            warnings.append(f"{doc.file_name} 是 internal，只能给内部链路用。")


def build_chunks(
    docs: list[KnowledgeDoc],
    errors: list[str],
    *,
    tenant_id: str,
    profile: TenantProfile | None = None,
) -> list[KnowledgeChunk]:
    active_profile = profile or DEFAULT_TENANT_PROFILE
    chunks: list[KnowledgeChunk] = []

    for doc in docs:
        if not doc.meta:
            continue

        category = doc.meta["category"]
        title = doc.meta["title"]
        kb_id = doc.meta["kb_id"]
        status = doc.meta["status"]
        visibility = doc.meta["visibility"]

        if category == active_profile.faq_category:
            sections = split_faq_chunks(doc.body)
            for index, (question, answer) in enumerate(sections, start=1):
                chunks.append(
                    KnowledgeChunk(
                        tenant_id=tenant_id,
                        chunk_id=f"{kb_id}_{index:03d}",
                        kb_id=kb_id,
                        title=title,
                        category=category,
                        status=status,
                        visibility=visibility,
                        source_file=doc.file_name,
                        section_title=f"问答{index}",
                        text=clean_text(f"问题：{question}\n{answer}"),
                    )
                )
            continue

        sections = split_heading_chunks(doc.body)
        for index, (section_title, section_text) in enumerate(sections, start=1):
            chunks.append(
                KnowledgeChunk(
                    tenant_id=tenant_id,
                    chunk_id=f"{kb_id}_{index:03d}",
                    kb_id=kb_id,
                    title=title,
                    category=category,
                    status=status,
                    visibility=visibility,
                    source_file=doc.file_name,
                    section_title=section_title,
                    text=section_text,
                )
            )

    if not chunks and not errors:
        errors.append("没有生成任何知识切片")
    return chunks
