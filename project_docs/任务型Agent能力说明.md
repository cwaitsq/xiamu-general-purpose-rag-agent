# 任务型Agent能力说明

## 这次补的不是“聊天功能”，而是任务闭环

当前项目除了原有的 RAG 问答和知识入库，现在新增了一条更像企业级 Agent 的能力线：

- 查订单
- 查库存
- 自动建工单
- 高风险请求自动转人工
- 保留步骤日志、工具调用日志、失败原因和运行指标

这条能力线的重点不是“模型说得像不像”，而是“系统有没有真正完成任务，且过程可追踪”。

## 新增后端能力

主要在 `backend_service/` 增加了任务型 Agent 模块和运行记录能力：

- `backend_service/agent_tasks.py`
  负责订单 / 库存 / 工单工具调用、任务编排、运行日志和结果落库。
- `POST /api/agent/tasks/run`
  认证用户可直接调用的任务型 Agent 接口。
- `POST /api/demo/agent/tasks/run`
  用于本地演示和 n8n 联调的入口。
- `GET /api/admin/agent/tasks/runs`
  查看任务运行记录。
- `GET /api/admin/agent/tasks/runs/<run_id>`
  查看单次运行详情。
- `GET /api/admin/agent/tasks/metrics`
  查看聚合后的任务指标。

## 新增可观测性

每次任务运行都会保留：

- `tool_calls`
  记录每次工具调用的输入、输出、状态、耗时。
- `step_logs`
  记录规划、校验、分支决策、失败点。
- `metrics`
  记录耗时、工具调用次数、是否拒答、是否转人工、是否检测到幻觉。
- `failure_reason`
  给管理台、评测脚本和后续排障直接使用。

## 新增评测方式

新增脚本：

- `tools/run_agent_eval.py`

脚本会用固定 benchmark 跑任务型 Agent，并输出：

- `accuracy`
- `refusal_rate`
- `hallucination_rate`
- `handoff_rate`
- `average_latency_ms`

这是给“项目能不能拿来讲面试”最有帮助的一块，因为你终于不只是说“我做了 Agent”，而是能说“我怎么评估 Agent 的质量”。

## 新增 n8n 工作流

新增工作流文件：

- `n8n工作流/04_任务型Agent_订单库存工单闭环版.json`

这条工作流支持：

- webhook 接收任务请求
- 调用后端任务型 Agent
- 返回结构化结果
- 结果里直接带工具调用日志、步骤日志和任务指标

这比“只调一次大模型然后回一句话”更像企业内部真实用法。

## 当前边界

这版仍然是企业级展示基线，不是已经接入真实 ERP / OMS / WMS 的生产系统。

现在的工具层是本地可控样例数据，优点是：

- 可联调
- 可测试
- 可复现
- 可讲清楚

它的下一步应该是把订单、库存、工单工具替换成真实内部 API 或服务连接器。

## 你对外怎么讲更有分量

建议这样讲：

1. 这不是单纯的 RAG 问答项目，我把它往任务型 Agent 方向扩展了。
2. Agent 不是直接碰高风险业务，而是先做查询、核验、建工单和转人工。
3. 我给 Agent 加了 trace、tool log、failure reason 和评测脚本，所以它不是黑盒。
4. 这套结构后续可以把 mock tool 换成真实企业 API，而不是重写整套系统。

## 后续最值得继续做的 4 件事

1. 把工具注册做成可配置 Tool Registry，不再写死在代码里。
2. 补权限模型，让不同租户和不同角色只能用指定工具。
3. 增加真实外部系统接入，例如 ERP、工单系统、库存系统。
4. 把评测脚本接到 CI，形成固定回归基线。
