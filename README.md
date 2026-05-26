# 通用型 RAG Agent（General-purpose-RAG-Agent）

这个仓库是当前项目的后续主维护仓，用于继续做通用化、能力拆分、工作流沉淀和功能升级。

当前默认内置的示例租户仍然是 `foreign_trade_demo`，但代码结构已经不再只绑定外贸客服场景。只要替换租户配置、知识库内容和工作流编排，就可以迁移到其他行业客服、内部知识问答、售前支持或 SOP 助手场景。

## 仓库定位

- 后续升级主仓：后续优化、重构、新能力接入默认都在这个仓库继续推进。
- 通用 RAG Agent 基线：保留前端、后端、Gateway、知识整理/入库链路和 n8n 工作流的完整闭环。
- 多租户扩展入口：通过 `tenant_kb/<tenant_id>/` 和 `tenant_config.json` 扩展不同业务租户。

## 当前已具备的通用能力

- 租户级客服配置：支持按租户定义品牌、语气、知识分类、检索约束和回复边界。
- 知识整理链路：支持原始文档整理、预览、报告输出和知识切片准备。
- 知识入库链路：支持切片产出、入库报告和后续向量检索对接。
- Gateway 检索问答：承接检索、上下文拼装和问答服务。
- 后端管理接口：提供知识上传、列表、日志、系统概览和用户管理接口。
- 任务型 Agent 闭环：支持订单查询、库存核验、自动建工单、人工转交。
- Agent 可观测性：保留工具调用日志、步骤日志、失败原因和运行指标。
- Agent 评测脚本：可跑固定基准集，输出准确率、拒答率、幻觉率、转人工率和平均耗时。
- 前端控制台：包含登录、聊天、知识管理、管理后台等页面。
- n8n 工作流资产：包含最小可用工作流和 `feat/amazon-spapi-gateway-gateway-first-pack/` 打包资产。

## 目录说明

- `frontend/`：Next.js 前端控制台。
- `backend_service/`：APIFlask 后端服务。
- `gateway/`：RAG Gateway 与知识处理逻辑。
- `shared/`：跨模块共享的租户配置模型。
- `tenant_kb/`：租户知识库、原始资料、整理结果和入库结果。
- `tools/`：启动脚本、自测脚本、知识处理脚本和辅助工具。
- `n8n工作流/`：可直接导入的工作流文件。
- `feat/amazon-spapi-gateway-gateway-first-pack/`：复用工作流与打包资产。
- `project_docs/`：项目说明、部署、迁移和维护文档。

## 快速开始

1. 复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

2. 安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

3. 安装前端依赖：

```powershell
cd frontend
pnpm install
```

4. 配置 qmd。

如果本地存在 `qmd_repo/dist/cli/qmd.js`，Gateway 会自动识别；如果没有，请在 `.env` 中配置 `QMD_CLI_PATH` 或 `QMD_COMMAND`。

5. 启动服务：

```powershell
python tools\启动_gateway_runner.py
python tools\启动_backend.py
cd frontend
pnpm dev --hostname 127.0.0.1 --port 3001
```

## 默认本地地址

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8877`
- Gateway Runner：`http://127.0.0.1:8765`
- n8n：`http://127.0.0.1:5678`

## 如何切换到新的行业或客户场景

1. 复制一个新的租户目录，例如 `tenant_kb/<new_tenant_id>/`。
2. 修改该租户下的 `tenant_config.json`，定义品牌、角色、知识分类和回复约束。
3. 替换 `raw/` 和 `docs/` 中的行业资料或客户资料。
4. 重新执行知识整理与入库脚本。
5. 让 Gateway / 后端指向新的租户配置进行联调。

当前仓库默认示例仍是外贸客服，但通用化方向已经从“单场景项目”切到了“可替换知识底座和租户配置的 Agent 基线”。

## 重要文档

- [project_docs/仓库迁移与升级说明.md](./project_docs/仓库迁移与升级说明.md)
- [project_docs/任务型Agent实施提示词.md](./project_docs/任务型Agent实施提示词.md)
- [project_docs/任务型Agent能力说明.md](./project_docs/任务型Agent能力说明.md)
- [project_docs/README.md](./project_docs/README.md)
- [project_docs/项目收口说明.md](./project_docs/项目收口说明.md)
- [project_docs/部署文档_v1.md](./project_docs/部署文档_v1.md)
- [project_docs/开发环境搭建文档_v1.md](./project_docs/开发环境搭建文档_v1.md)
- [project_docs/后端服务使用说明.md](./project_docs/后端服务使用说明.md)
- [n8n工作流/导入说明.md](./n8n工作流/导入说明.md)

## 维护约定

- 这个仓库是后续升级和优化的主仓。
- 默认基于 `main` 持续集成，较大改动建议走独立功能分支。
- 本地运行日志、缓存、数据库和构建产物不提交到版本库。
- 若继续推进“通用型客服 / 通用型知识助手”方向，优先抽象租户配置、知识处理链路和工作流组件，而不是继续写死外贸场景。
- 若以“企业级 Agent 项目”对外展示，优先展示任务闭环、评测结果、日志可观测性和人机协同边界，而不是只展示聊天页面。
