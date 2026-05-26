from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TENANT_KB_ROOT = ROOT / "tenant_kb"
LEGACY_KB_ROOT = ROOT / "知识库"
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "foreign_trade_demo").strip() or "foreign_trade_demo"


@dataclass(frozen=True)
class TenantWorkspace:
    tenant_id: str
    tenant_slug: str
    root: Path
    raw_dir: Path
    docs_dir: Path
    auto_docs_dir: Path
    prepare_output_dir: Path
    prepare_report_file: Path
    prepare_preview_file: Path
    ingest_output_dir: Path
    chunks_file: Path
    ingest_report_file: Path
    ingest_preview_file: Path
    collection_name: str


def sanitize_tenant_id(tenant_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", tenant_id.strip())
    return cleaned[:64].strip("_") or "default"


def build_collection_name(base_collection: str, tenant_id: str) -> str:
    return f"{base_collection}__{sanitize_tenant_id(tenant_id)}"


def get_tenant_workspace(tenant_id: str, *, collection_base: str) -> TenantWorkspace:
    tenant_slug = sanitize_tenant_id(tenant_id)
    root = TENANT_KB_ROOT / tenant_slug
    raw_dir = root / "raw"
    docs_dir = root / "docs"
    auto_docs_dir = docs_dir / "auto"
    prepare_output_dir = root / "prepare_output"
    ingest_output_dir = root / "ingest_output"
    return TenantWorkspace(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        root=root,
        raw_dir=raw_dir,
        docs_dir=docs_dir,
        auto_docs_dir=auto_docs_dir,
        prepare_output_dir=prepare_output_dir,
        prepare_report_file=prepare_output_dir / "knowledge_prepare_report.json",
        prepare_preview_file=prepare_output_dir / "knowledge_prepare_preview.md",
        ingest_output_dir=ingest_output_dir,
        chunks_file=ingest_output_dir / "chunks.jsonl",
        ingest_report_file=ingest_output_dir / "knowledge_ingest_report.json",
        ingest_preview_file=ingest_output_dir / "chunk_preview.md",
        collection_name=build_collection_name(collection_base, tenant_id),
    )


def ensure_workspace_bootstrap(workspace: TenantWorkspace) -> None:
    workspace.root.mkdir(parents=True, exist_ok=True)
    if workspace.tenant_id != DEFAULT_TENANT_ID:
        return
    if any(workspace.root.iterdir()):
        return
    if not LEGACY_KB_ROOT.exists():
        return

    legacy_mapping = {
        LEGACY_KB_ROOT / "原始资料": workspace.raw_dir,
        LEGACY_KB_ROOT / "已整理知识": workspace.docs_dir,
        LEGACY_KB_ROOT / "整理结果": workspace.prepare_output_dir,
        LEGACY_KB_ROOT / "切片结果": workspace.ingest_output_dir,
    }
    for source, destination in legacy_mapping.items():
        if source.exists():
            shutil.copytree(source, destination, dirs_exist_ok=True)


def count_workspace_chunks(collection_base: str) -> int:
    total = 0
    if not TENANT_KB_ROOT.exists():
        return total
    for tenant_dir in TENANT_KB_ROOT.iterdir():
        if not tenant_dir.is_dir():
            continue
        workspace = get_tenant_workspace(tenant_dir.name, collection_base=collection_base)
        if not workspace.chunks_file.exists():
            continue
        with workspace.chunks_file.open("r", encoding="utf-8") as file:
            total += sum(1 for _ in file)
    return total
