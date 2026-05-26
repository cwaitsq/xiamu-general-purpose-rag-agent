from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from app.config import load_settings  # noqa: E402
from app.rag_clients import HttpJsonError, QmdClient  # noqa: E402
from app.tenant_paths import DEFAULT_TENANT_ID, ensure_workspace_bootstrap, get_tenant_workspace  # noqa: E402


def count_docs(docs_dir: Path) -> int:
    if not docs_dir.exists():
        return 0
    return sum(1 for _ in docs_dir.rglob("*.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化指定租户的 qmd collection。")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help=f"租户 ID，默认 {DEFAULT_TENANT_ID}。")
    args = parser.parse_args()

    settings = load_settings()
    workspace = get_tenant_workspace(args.tenant_id, collection_base=settings.qmd_collection)
    ensure_workspace_bootstrap(workspace)
    client = QmdClient(settings)

    if not client.is_configured():
        print("未找到 qmd 配置，请先检查 QMD_CLI_PATH 或 QMD_COMMAND。")
        return 1

    doc_count = count_docs(workspace.docs_dir)
    if doc_count <= 0:
        print(f"未找到可索引的知识文档：{workspace.docs_dir}")
        return 1

    index_dir = ROOT / ".qmd"
    if not index_dir.exists():
        client.init_index()

    try:
        exists = client.collection_exists(workspace.collection_name)
        if not exists:
            client.add_collection(str(workspace.docs_dir), workspace.collection_name)
        client.update()
    except HttpJsonError as exc:
        print(f"qmd 初始化失败：{exc}")
        return 1

    print(
        json.dumps(
            {
                "status": "success",
                "tenant_id": args.tenant_id,
                "collection_name": workspace.collection_name,
                "docs_dir": str(workspace.docs_dir),
                "docs_total": doc_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
