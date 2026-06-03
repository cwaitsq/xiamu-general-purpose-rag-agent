# 前端控制台说明

`frontend/` 是本项目的前端控制台目录，基于 Next.js 构建。

它的职责不是单独承载业务逻辑，而是为整套 RAG Agent 系统提供统一的交互入口，用于连接后端服务与 Gateway 能力。

## 1. 模块定位

前端控制台主要负责以下事情：

- 提供问答交互入口
- 展示会话记录
- 触发知识上传与知识入库
- 展示任务状态与知识列表
- 承载部分后台管理视图

换句话说，这里是系统的“操作台”，不是知识处理核心，也不是问答核心。

## 2. 技术栈

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS

## 3. 环境变量

先复制模板文件：

```powershell
Copy-Item .env.example .env.local
```

常用变量如下：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `BACKEND_BASE_URL` | `http://127.0.0.1:8877` | 后端服务地址 |
| `GATEWAY_BASE_URL` | `http://127.0.0.1:8765/gateways/rag_kefu_gateway` | Gateway Runner 地址 |

## 4. 本地启动

安装依赖：

```powershell
pnpm install
```

开发模式启动：

```powershell
pnpm dev --port 3001
```

生产构建与启动：

```powershell
pnpm build
pnpm start --port 3001
```

## 5. 联调前提

前端启动前，建议先确认以下服务已经可用：

- 后端服务：`http://127.0.0.1:8877`
- Gateway Runner：`http://127.0.0.1:8765`

如果后端或 Gateway 未启动，前端页面虽然可以打开，但实际功能无法完成联调。

## 6. 常用检查命令

```powershell
pnpm lint
pnpm build
```

## 7. 目录说明

| 路径 | 作用 |
|---|---|
| `src/` | 前端源码目录 |
| `public/` | 静态资源 |
| `.env.example` | 前端环境变量模板 |
| `package.json` | 前端依赖与脚本定义 |
| `next.config.ts` | Next.js 配置 |
| `tsconfig.json` | TypeScript 配置 |

## 8. 说明

- 前端控制台负责展示和操作，不负责知识切片、检索或模型编排。
- 如果要调整知识问答逻辑，应优先查看 `gateway/`。
- 如果要调整登录、知识任务、日志或管理接口，应优先查看 `backend_service/`。
