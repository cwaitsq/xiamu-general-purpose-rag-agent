# Gateway 说明

`gateway/` 是本仓库中负责知识处理、检索问答与对外问答入口编排的核心模块。

它位于“知识资产”和“应用层接口”之间，主要承担以下职责：

- 组织租户知识工作区
- 整理原始资料
- 生成切片与入库产物
- 对接检索底座
- 调用模型完成问答
- 输出可审计的问答结果

## 1. 模块定位

当前系统中的典型调用关系如下：

```text
前端 / 后端 / n8n
-> Gateway Runner
-> gateway 核心逻辑
-> 检索层 / 模型层
-> 返回回答与证据
```

当前仓库默认以 `qmd` 作为主检索方案，同时保留了兼容性代码，便于后续扩展。

## 2. 目录结构

| 路径 | 作用 |
|---|---|
| `app/main.py` | Gateway 最小 HTTP 服务入口 |
| `app/service.py` | 问答主流程、上下文构建、检索结果处理 |
| `app/rag_clients.py` | 检索与模型客户端封装 |
| `app/knowledge_prepare.py` | 原始资料整理逻辑 |
| `app/knowledge_ingest.py` | 知识入库处理逻辑 |
| `app/media_preprocess.py` | 图片、音频、视频等多模态预处理 |
| `app/tenant_paths.py` | 租户工作区路径管理 |
| `app/schemas.py` | 请求与响应结构定义 |
| `app/config.py` | Gateway 配置加载 |
| `app/runner_cli.py` | 本地命令行入口 |
| `tests/` | Gateway 测试 |

## 3. 配置读取方式

Gateway 默认按以下顺序读取配置：

1. 根目录 `.env`
2. `gateway/.env`

建议做法：

- 日常开发优先维护根目录 `.env`
- 只有在需要对 Gateway 做局部覆盖时，再使用 `gateway/.env`

## 4. 租户知识目录约定

知识资产按租户组织，目录结构如下：

```text
tenant_kb/<tenant_id>/
  raw/                原始资料
  docs/               整理后的知识文档
  docs/auto/          自动整理后的知识
  prepare_output/     整理报告与中间产物
  ingest_output/      切片、入库与索引相关产物
  tenant_config.json  租户配置
```

当前默认示例租户为：

```text
foreign_trade_demo
```

## 5. 常用命令

安装依赖：

```powershell
python -m pip install -r gateway\requirements.txt
```

启动 Gateway Runner：

```powershell
python tools\启动_gateway_runner.py
```

本地执行单次问答：

```powershell
python gateway\app\runner_cli.py query
```

整理原始资料：

```powershell
python gateway\app\runner_cli.py prepare_raw
```

重建知识切片并刷新索引：

```powershell
python gateway\app\runner_cli.py ingest_rebuild
```

## 6. 典型接口

健康检查：

```text
GET http://127.0.0.1:8765/gateways/rag_kefu_gateway/health
```

问答接口：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/query
```

知识重建接口：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/ingest/rebuild
```

知识整理接口：

```text
POST http://127.0.0.1:8765/gateways/rag_kefu_gateway/ingest/prepare
```

如果开启了网关鉴权，请求头中需要带：

```text
x-api-key: RAG_KEFU_GATEWAY_API_KEY
```

## 7. 问答请求示例

```json
{
  "tenant_id": "foreign_trade_demo",
  "session_id": "demo-001",
  "question": "最小起订量是多少？",
  "history": [],
  "top_k": 3
}
```

## 8. 入库请求示例

全量重建：

```json
{
  "tenant_id": "foreign_trade_demo",
  "prepare_raw": true,
  "refresh_index": true,
  "publish_status": "active"
}
```

指定单文件处理：

```json
{
  "tenant_id": "foreign_trade_demo",
  "prepare_raw": true,
  "refresh_index": true,
  "publish_status": "active",
  "target_file_path": "tenant_kb/foreign_trade_demo/raw/外贸客服样例/客户常见问题_原稿.txt"
}
```

## 9. 当前能力边界

当前 Gateway 已覆盖的能力包括：

- 租户隔离
- 原始资料整理
- 知识切片生成
- 检索问答
- 单文件增量处理
- 多模态预处理
- 问答审计日志

但它不是完整的业务管理后台，也不负责前端交互展示。

## 10. 使用建议

- 如果要处理知识整理、切片、检索与问答逻辑，优先在 `gateway/` 中扩展。
- 如果要处理用户、权限、知识任务管理或后台接口，优先查看 `backend_service/`。
- 如果要切换行业或客户，优先修改 `tenant_kb/<tenant_id>/tenant_config.json` 与租户资料目录，而不是直接改代码常量。
