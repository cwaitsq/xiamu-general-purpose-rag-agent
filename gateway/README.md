# Gateway 运行说明

## 1. 现在这层是怎么走的

当前正式链路是：

```text
前端 / n8n / 后端
-> gateway-runner(8765)
-> gateway/app/runner_cli.py
-> qmd 检索
-> DeepSeek 大模型生成
-> 返回答案
```

第一版默认走 `qmd`，不再把 `Qdrant` 当成主链路。
仓库里还保留了 `Qdrant` 兼容代码，但当前不是默认方案。

## 2. 配置文件怎么读

Gateway 现在会按这个顺序读配置：

1. 根目录 `.env`
2. `gateway/.env`

实际建议：

- 平时只维护根目录 `.env`
- `gateway/.env` 只在你想单独覆盖 Gateway 配置时再用

## 3. 租户目录长什么样

现在知识库已经改成按租户分目录：

```text
tenant_kb/<tenant_id>/
  raw/                原始资料
  docs/               已整理知识
  docs/auto/          自动整理后的知识
  prepare_output/     整理报告和预览
  ingest_output/      chunks、入库报告、切片预览
```

默认演示租户是：

```text
foreign_trade_demo
```

## 4. 常用命令

先装 Python 依赖：

```powershell
python -m pip install -r gateway\requirements.txt
```

启动正式 Gateway：

```powershell
python tools\启动_gateway_runner.py
```

本地直跑单次问答：

```powershell
python gateway\app\runner_cli.py query
```

整理原始资料：

```powershell
python gateway\app\runner_cli.py prepare_raw
```

重建知识切片并刷新 qmd：

```powershell
python gateway\app\runner_cli.py ingest_rebuild
```

## 5. 接口地址

健康检查：

```text
GET http://127.0.0.1:8765/gateways/rag_kefu_gateway/health
```

问答：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/query
```

重建入库：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/ingest/rebuild
```

整理原始资料：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/ingest/prepare
```

请求头必须带：

```text
x-api-key: RAG_KEFU_GATEWAY_API_KEY
```

## 6. 问答请求示例

```json
{
  "tenant_id": "foreign_trade_demo",
  "session_id": "demo-001",
  "question": "最小起订量是多少？",
  "history": [],
  "top_k": 3
}
```

## 7. 入库请求示例

全量重建：

```json
{
  "tenant_id": "foreign_trade_demo",
  "prepare_raw": true,
  "refresh_index": true,
  "publish_status": "active"
}
```

只处理一个文件：

```json
{
  "tenant_id": "foreign_trade_demo",
  "prepare_raw": true,
  "refresh_index": true,
  "publish_status": "active",
  "target_file_path": "tenant_kb/foreign_trade_demo/raw/外贸客服样例/客户常见问题_原稿.txt"
}
```

## 8. 现在已经做好的点

- 已支持租户隔离
- 已支持原始资料 -> 自动整理 -> 切片 -> qmd 刷新
- 已支持 txt、md、docx、csv、json、pptx、xlsx、pdf、srt、vtt
- 已支持图片 OCR、音频转写、视频转写、扫描 PDF OCR
- 已支持内部知识和外部知识隔离
- 已支持单文件增量入库
- 已支持问答审计日志

## 9. 注意事项

- 自动整理资料默认写到 `docs/auto`
- 内部资料会入库，但外部问答默认不会召回
- 资料改完后必须重新刷新 qmd，不然新内容不会立刻生效
- `top_k` 太小会影响命中稳定性，实际联调建议用 `5`
