# amazon-spapi-gateway-gateway-first-pack

这是从当前项目里整理出来的可复用资产包，先保留最通用的 n8n workflow 和配套工具，方便后续做 Amazon SP-API 版本时直接复用。

## Workflows

- `workflows/01_外贸客服问答_最小可用版.json`
- `workflows/02_外贸知识入库_最小可用版.json`
- `workflows/03_后端知识上传_最小可用版.json`
- `workflows/导入说明.md`

## Tools

- `tools/生成_n8n最终工作流.py`
- `tools/run_kb_prepare.py`
- `tools/run_kb_ingest.py`
- `tools/启动_gateway_runner.py`
- `tools/启动_backend.py`
- `tools/自测_gateway_runner.py`
- `tools/自测_backend.py`
- `tools/初始化_qmd_索引.py`

