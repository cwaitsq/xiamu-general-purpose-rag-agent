# 通用型 RAG Agent

`General-purpose-RAG-Agent` 是一个面向企业知识问答与任务协同场景的通用型 Agent 工程仓库。

这个项目的目标不是只做一个“聊天页面”，而是提供一套可以持续扩展的基础能力，包括：

- 多租户知识库管理
- 原始资料整理、切片、入库与索引刷新
- 检索增强问答（RAG）
- 后端管理接口与操作日志
- 前端控制台
- n8n 工作流编排
- 任务型 Agent 闭环能力

当前仓库内置的默认示例租户是 `foreign_trade_demo`，但整体结构已经按“可替换租户、可替换行业、可替换知识底座”的方式组织，不再只绑定单一外贸客服场景。

## 1. 项目解决什么问题

这个项目主要解决三类问题：

1. 企业知识分散在文档、表格、附件和历史资料中，人工查询成本高，回答不稳定。
2. 单纯的问答机器人无法覆盖“查资料、给结论、记录过程、转人工、执行任务”的完整链路。
3. 多个客户或多个业务线共用一套系统时，知识、配置、权限和回答边界需要隔离。

因此，这个仓库把系统拆成了几个明确的层次：

- `tenant_kb/` 负责租户级知识资产与配置
- `gateway/` 负责知识整理、检索、问答编排与索引对接
- `backend_service/` 负责管理接口、登录鉴权、知识任务与日志管理
- `frontend/` 负责控制台界面
- `n8n工作流/` 负责流程自动化接入

## 2. 核心能力概览

### 2.1 知识处理能力

- 支持按租户组织原始资料、整理结果、切片结果和入库产物
- 支持原始资料整理、知识切片生成、索引刷新
- 支持单文件处理与全量重建
- 支持问答证据来源回溯

### 2.2 RAG 问答能力

- 基于租户配置加载不同的回答角色、知识范围和风险约束
- 支持检索结果拼装、上下文构建和大模型回答
- 支持高风险问题识别、证据不足拒答和转人工建议
- 支持问答请求日志与审计记录

### 2.3 任务型 Agent 能力

- 支持任务型流程演示与闭环任务运行
- 支持步骤记录、工具调用、失败原因与运行摘要
- 支持为订单、库存、工单等场景扩展任务执行逻辑

### 2.4 管理与交付能力

- 提供后端管理接口
- 提供前端控制台
- 提供工作流导入资产
- 提供部署、迁移、能力说明与实施文档

## 3. 系统结构

当前仓库可以理解为一套“知识底座 + 检索问答 + 管理后台 + 工作流编排”的组合系统。

典型链路如下：

```text
原始业务资料
-> tenant_kb/<tenant_id>/raw
-> gateway 知识整理与切片
-> qmd / 检索索引
-> gateway 问答编排
-> backend_service 管理接口与日志
-> frontend 控制台展示与操作
-> n8n 工作流接入业务流程
```

在运行模式上，仓库默认采用以下分层：

- 前端控制台：负责用户交互与运维视图
- 后端服务：负责用户、会话、知识任务、日志与管理能力
- Gateway Runner：负责对外暴露 RAG 网关能力
- 检索与模型层：负责知识召回与模型生成

## 4. 目录说明

下面是仓库顶层目录和主要文件的职责说明。

| 路径 | 作用 |
|---|---|
| `backend_service/` | 后端管理服务，负责登录鉴权、知识上传、知识任务、问答日志、用户管理、任务型 Agent 接口等能力 |
| `feat/` | 特定功能包或阶段性打包资产，目前保留了 Amazon SP-API 相关工作流打包内容 |
| `frontend/` | 前端控制台，基于 Next.js，提供聊天、知识管理、任务查看和后台操作界面 |
| `gateway/` | RAG Gateway 核心目录，负责知识整理、切片、检索问答、媒体预处理、租户路径管理等逻辑 |
| `n8n工作流/` | 可导入的 n8n 工作流文件，覆盖问答、知识入库、任务型 Agent 等流程 |
| `project_docs/` | 项目级文档目录，存放部署说明、开发环境说明、迁移说明、能力说明等正式资料 |
| `shared/` | 跨模块共享模型与通用逻辑，目前主要放租户配置模型 |
| `tenant_kb/` | 多租户知识库目录，按租户存放原始资料、整理结果、切片结果和租户配置 |
| `tools/` | 启动脚本、自测脚本、知识处理脚本、n8n 生成脚本与辅助工具集合 |
| `.env.example` | 根目录环境变量模板 |
| `requirements.txt` | Python 依赖入口，内部引用 `gateway/` 与 `backend_service/` 的依赖清单 |
| `gateway_audit.jsonl` | Gateway 问答审计日志样例或运行输出 |

### 4.1 `backend_service/` 目录做什么

这个目录是系统的管理后端，核心职责包括：

- 提供登录、鉴权、会话和用户管理
- 负责知识上传、知识任务和入库记录管理
- 调用 Gateway 完成问答
- 保存消息、附件、日志和系统概览
- 承载任务型 Agent 的接口与运行记录

主要文件：

| 路径 | 作用 |
|---|---|
| `server.py` | 后端服务入口 |
| `config.py` | 后端配置加载 |
| `database.py` | 数据库连接与初始化 |
| `services.py` | 业务服务层 |
| `agent_tasks.py` | 任务型 Agent 相关逻辑 |
| `static/` | 后端静态页面资源 |
| `tests/` | 后端测试 |
| `data/app.db` | 本地 SQLite 数据文件 |

### 4.2 `gateway/` 目录做什么

这个目录是知识处理与 RAG 问答核心层，主要负责：

- 知识整理与清洗
- 文档切片与入库准备
- 检索索引对接
- 问答请求编排
- 租户隔离与知识边界控制
- 多模态预处理

主要文件：

| 路径 | 作用 |
|---|---|
| `app/main.py` | Gateway HTTP 服务入口 |
| `app/service.py` | 问答编排与检索核心逻辑 |
| `app/rag_clients.py` | 检索与模型客户端封装 |
| `app/knowledge_prepare.py` | 原始资料整理 |
| `app/knowledge_ingest.py` | 知识入库处理 |
| `app/media_preprocess.py` | 图片、音频、视频等预处理 |
| `app/tenant_paths.py` | 租户路径与工作区管理 |
| `app/schemas.py` | 请求响应结构定义 |
| `tests/` | Gateway 测试 |

### 4.3 `frontend/` 目录做什么

这个目录是系统控制台，主要面向运营、测试、实施或管理人员。

主要能力包括：

- 访问问答界面
- 查看会话记录
- 上传资料并发起知识入库
- 查看任务状态
- 查看知识列表与日志
- 配合后端完成系统联调

### 4.4 `tenant_kb/` 目录做什么

这是多租户知识资产根目录。

推荐把它理解为“每个租户自己的知识工作区”。当前默认示例是：

```text
tenant_kb/foreign_trade_demo/
```

租户目录内部通常包含：

| 路径 | 作用 |
|---|---|
| `raw/` | 原始资料输入 |
| `docs/` | 整理后的知识文档 |
| `prepare_output/` | 整理阶段输出 |
| `ingest_output/` | 切片、入库和索引相关输出 |
| `tenant_config.json` | 租户级角色、术语、知识范围和回复边界配置 |

### 4.5 `tools/` 目录做什么

这个目录存放所有便于本地开发、联调与维护的辅助脚本。

常见用途包括：

- 启动后端
- 启动 Gateway Runner
- 运行知识整理
- 运行知识入库
- 运行 Agent 评测
- 生成 n8n 工作流资产

### 4.6 `project_docs/` 目录做什么

这个目录存放正式项目资料，不是临时草稿区。

其中包括：

- 部署说明
- 开发环境搭建说明
- 仓库迁移与升级说明
- 任务型 Agent 能力说明
- 项目收口说明

如果需要向客户、实施同事或后续维护人员解释项目，这个目录是主要文档入口。

## 5. 运行依赖

### 5.1 Python 依赖

根目录 `requirements.txt` 会同时安装后端与 Gateway 依赖：

- `backend_service/requirements.txt`
- `gateway/requirements.txt`

其中主要依赖包括：

- APIFlask
- psycopg
- pypdf
- openpyxl
- python-pptx

### 5.2 前端依赖

前端目录使用：

- Next.js
- React
- TypeScript
- Tailwind CSS

### 5.3 外部能力依赖

根据当前 `.env.example`，项目默认还依赖：

- 大模型接口
- qmd 检索服务或 CLI
- 多模态处理能力
- 可选的 n8n 运行环境

## 6. 快速开始

### 6.1 准备环境变量

先复制一份环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后按实际环境填写关键配置，例如：

- `RAG_KEFU_GATEWAY_API_KEY`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `QMD_CLI_PATH`
- `DEFAULT_TENANT_ID`

### 6.2 安装 Python 依赖

```powershell
python -m pip install -r requirements.txt
```

### 6.3 安装前端依赖

```powershell
cd frontend
pnpm install
```

### 6.4 启动服务

根目录下推荐分别启动：

```powershell
python tools\启动_gateway_runner.py
python tools\启动_backend.py
cd frontend
pnpm dev --hostname 127.0.0.1 --port 3001
```

## 7. 默认本地地址

默认本地联调地址如下：

- 前端控制台：`http://127.0.0.1:3001`
- 后端服务：`http://127.0.0.1:8877`
- Gateway Runner：`http://127.0.0.1:8765`

注意：

- 后端默认会调用 `BACKEND_GATEWAY_BASE_URL`
- 根目录 `.env.example` 中默认的 Gateway 路径带有 `/gateways/rag_kefu_gateway`
- `gateway/app/main.py` 中的最小服务入口是另一路本地 HTTP 入口，和 Runner 模式职责不同

## 8. 如何扩展到新的客户或行业

如果要从当前默认示例切换到新的客户、行业或部门，建议按下面步骤做：

1. 在 `tenant_kb/` 下创建新的租户目录。
2. 新建或复制对应的 `tenant_config.json`。
3. 把该客户的原始资料放入 `raw/`。
4. 执行知识整理与入库脚本。
5. 切换后端和 Gateway 使用的新租户配置。
6. 在前端与工作流中完成联调。

这种方式的好处是：

- 代码层保持稳定
- 知识资产可隔离
- 回复边界可配置
- 不同行业可以共用一套基础工程

## 9. 重点文档

推荐优先阅读以下文档：

- [project_docs/README.md](./project_docs/README.md)
- [project_docs/仓库迁移与升级说明.md](./project_docs/仓库迁移与升级说明.md)
- [project_docs/任务型Agent能力说明.md](./project_docs/任务型Agent能力说明.md)
- [project_docs/部署文档_v1.md](./project_docs/部署文档_v1.md)
- [project_docs/开发环境搭建文档_v1.md](./project_docs/开发环境搭建文档_v1.md)
- [gateway/README.md](./gateway/README.md)
- [frontend/README.md](./frontend/README.md)
- [n8n工作流/导入说明.md](./n8n工作流/导入说明.md)

## 10. 当前仓库的使用建议

- 如果你要理解项目全貌，先看本文件和 `project_docs/README.md`
- 如果你要跑知识问答链路，优先看 `gateway/README.md`
- 如果你要看控制台和前端联调，优先看 `frontend/README.md`
- 如果你要接新租户，优先看 `tenant_kb/` 结构和租户配置模型
- 如果你要做任务型 Agent 扩展，优先看 `backend_service/agent_tasks.py` 与 `project_docs/任务型Agent能力说明.md`

## 11. 维护原则

- 所有说明文档优先使用中文维护
- 知识、配置、工作流与代码边界要清晰
- 新能力优先沉淀为可复用模块，而不是写死在单一示例里
- 对外介绍项目时，应强调知识治理、检索问答、任务闭环和可观测性，而不只是聊天能力
