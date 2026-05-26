from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from app.config import load_settings  # noqa: E402
from app.knowledge_ingest import run_knowledge_ingest  # noqa: E402
from app.rag_clients import EmbeddingClient, HttpJsonError, QdrantClient  # noqa: E402
from app.rag_helpers import chunk_payload_to_text, point_id_for_chunk_id  # noqa: E402
from app.tenant_paths import DEFAULT_TENANT_ID, build_collection_name, get_tenant_workspace  # noqa: E402


def load_chunk_payloads(chunks_file: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    with chunks_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payloads.append(json.loads(line))
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="把指定租户的切片同步到 Qdrant。")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help=f"租户 ID，默认 {DEFAULT_TENANT_ID}。")
    parser.add_argument("--build-if-missing", action="store_true", help="如果没有 chunks.jsonl，就先本地生成一份。")
    args = parser.parse_args()

    settings = load_settings()
    workspace = get_tenant_workspace(args.tenant_id, collection_base=settings.qmd_collection)

    if args.build_if_missing and not workspace.chunks_file.exists():
        ingest_result = run_knowledge_ingest(
            validate_only=False,
            refresh_index=False,
            prepare_raw=False,
            tenant_id=args.tenant_id,
            settings=settings,
        )
        if ingest_result.status != "success":
            print(json.dumps(ingest_result.to_dict(), ensure_ascii=False, indent=2))
            return 1

    if not workspace.chunks_file.exists():
        print(f"未找到切片文件：{workspace.chunks_file}")
        print("请先执行：python tools\\构建知识切片.py --tenant-id " + args.tenant_id)
        return 1

    qdrant_settings = replace(
        settings,
        qdrant_collection=build_collection_name(settings.qdrant_collection, args.tenant_id),
    )
    embedding_client = EmbeddingClient(qdrant_settings)
    qdrant_client = QdrantClient(qdrant_settings)

    if not embedding_client.is_configured():
        print("未配置 EMBEDDING_API_KEY，无法写入 Qdrant。")
        return 1
    if not qdrant_settings.qdrant_url:
        print("未配置 QDRANT_URL，无法写入 Qdrant。")
        return 1

    payloads = load_chunk_payloads(workspace.chunks_file)
    if not payloads:
        print("切片文件是空的，无法同步到 Qdrant。")
        return 1

    batch_size = 10
    vector_size: int | None = None

    for start in range(0, len(payloads), batch_size):
        batch = payloads[start : start + batch_size]
        texts = [chunk_payload_to_text(payload) for payload in batch]
        try:
            embeddings = embedding_client.embed_texts(texts)
        except HttpJsonError as exc:
            print(f"Embedding 调用失败：{exc}")
            return 1

        if not embeddings:
            print("Embedding 没有返回向量。")
            return 1

        if vector_size is None:
            vector_size = len(embeddings[0])
            try:
                qdrant_client.ensure_collection(vector_size)
            except HttpJsonError as exc:
                print(f"Qdrant collection 初始化失败：{exc}")
                return 1

        points = []
        for payload, embedding in zip(batch, embeddings):
            chunk_id = str(payload.get("chunk_id", ""))
            points.append(
                {
                    "id": point_id_for_chunk_id(chunk_id),
                    "vector": embedding,
                    "payload": payload,
                }
            )

        try:
            qdrant_client.upsert_points(points)
        except HttpJsonError as exc:
            print(f"Qdrant 写入失败：{exc}")
            return 1

    print(
        json.dumps(
            {
                "status": "success",
                "tenant_id": args.tenant_id,
                "qdrant_collection": qdrant_settings.qdrant_collection,
                "chunks_total": len(payloads),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
