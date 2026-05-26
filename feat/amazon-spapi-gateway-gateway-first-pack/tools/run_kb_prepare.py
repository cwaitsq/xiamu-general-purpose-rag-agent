from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from app.knowledge_prepare import run_knowledge_prepare  # noqa: E402
from app.tenant_paths import DEFAULT_TENANT_ID  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="整理原始资料，生成标准知识文档。")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help=f"租户 ID，默认 {DEFAULT_TENANT_ID}。")
    parser.add_argument("--validate-only", action="store_true", help="只校验，不写入文档。")
    parser.add_argument(
        "--publish-status",
        choices=["active", "draft", "inactive"],
        default="draft",
        help="自动整理文档的状态，默认 draft。",
    )
    parser.add_argument("--use-llm", action="store_true", help="整理时调用大模型辅助结构化。")
    parser.add_argument("--target-file-path", help="只整理一个文件时传这个绝对路径。")
    args = parser.parse_args()

    result = run_knowledge_prepare(
        validate_only=args.validate_only,
        publish_status=args.publish_status,
        use_llm=args.use_llm,
        tenant_id=args.tenant_id,
        target_file_path=args.target_file_path,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
