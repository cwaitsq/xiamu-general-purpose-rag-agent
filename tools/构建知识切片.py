from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from app.knowledge_ingest import run_knowledge_ingest  # noqa: E402
from app.tenant_paths import DEFAULT_TENANT_ID  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成指定租户的知识切片。")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help=f"租户 ID，默认 {DEFAULT_TENANT_ID}。")
    parser.add_argument("--validate-only", action="store_true", help="只校验知识文档，不生成切片。")
    parser.add_argument("--refresh-index", action="store_true", help="切片完成后顺手刷新 qmd。")
    parser.add_argument("--prepare-raw", action="store_true", help="切片前先整理 raw 资料。")
    parser.add_argument(
        "--publish-status",
        choices=["active", "draft", "inactive"],
        default="draft",
        help="自动整理文档的状态，默认 draft。",
    )
    parser.add_argument("--prepare-use-llm", action="store_true", help="整理 raw 资料时调用大模型辅助结构化。")
    parser.add_argument("--target-file-path", help="只处理一个 raw 文件时传这个绝对路径。")
    args = parser.parse_args()

    if args.target_file_path and not args.prepare_raw:
        parser.error("--target-file-path 只能和 --prepare-raw 一起用。")

    result = run_knowledge_ingest(
        validate_only=args.validate_only,
        refresh_index=args.refresh_index,
        prepare_raw=args.prepare_raw,
        publish_status=args.publish_status,
        prepare_use_llm=args.prepare_use_llm,
        tenant_id=args.tenant_id,
        target_file_path=args.target_file_path,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
