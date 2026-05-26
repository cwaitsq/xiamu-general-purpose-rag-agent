# 外贸客服 RAG 前端控制台

这是项目的正式前端控制台，不是单独的演示页。

## 现在能做什么

- 看后端和 Gateway 的健康状态
- 直接发起客服问答
- 查看会话历史
- 上传资料并触发知识入库
- 轮询入库任务状态
- 查看知识列表
- 查看问答日志

## 技术栈

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS

## 环境变量

先复制一份环境变量模板：

```powershell
Copy-Item .env.example .env.local
```

默认值：

- `BACKEND_BASE_URL=http://127.0.0.1:8877`
- `GATEWAY_BASE_URL=http://127.0.0.1:8765/gateways/rag_kefu_gateway`

## 本地启动

开发模式：

```powershell
pnpm dev --port 3001
```

生产构建：

```powershell
pnpm build
pnpm start --port 3001
```

## 启动前提

前端只是控制台壳子，后面的服务也要先起来：

- 后端：`http://127.0.0.1:8877`
- Gateway：`http://127.0.0.1:8765`

## 校验命令

```powershell
pnpm lint
pnpm build
```
