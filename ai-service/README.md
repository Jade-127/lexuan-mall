# ai-service · 智能客服 Agent

电商系统里的 AI 客服模块，以独立 Python 服务运行，经网关 `/ai/**` 对外暴露。

- **技术栈**：Python 3.11 · FastAPI · LangGraph · LangChain · 阿里云百炼（qwen-plus / text-embedding-v3）· PostgreSQL + pgvector
- **定位**：不是 Maven 模块（没有 `pom.xml`），与 Java 侧通过网关和 HTTP 接口解耦，互不影响构建

## 能力

| 能力 | 实现 |
|---|---|
| 工具调用 | 商品检索 / 我的订单 / 订单详情 / 售后政策 RAG / 创建工单（LangGraph `ToolNode`） |
| 多轮记忆 | `AsyncPostgresSaver`，`thread_id = 用户:会话`，重启不丢 |
| 写操作确认 | 工具内 `interrupt()` 暂停，前端确认后 `Command(resume=...)` 续跑 |
| 安全边界 | userId 由服务端上下文注入（不进模型）、会话归属校验、每用户滑窗限流 |
| 前置检索 | 政策/商品类问题命中关键词时先查库，结果作为「已完成的工具调用」注入 |
| 可观测性 | `trace_id` 贯穿请求，`GET /ai/traces/{id}` 回放；工具日志 + token 统计 |

## 接口

全部经网关 `/ai/**` 暴露，JWT 由网关校验后以 `user-info` 头透传。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 探活 |
| POST | `/ai/chat` | 对话，返回 `status=done` 或 `need_confirm` |
| POST | `/ai/chat/confirm` | 确认/取消写操作 |
| GET | `/ai/tickets` | 我的工单 |
| GET | `/ai/conversations/{id}/messages` | 会话历史 |
| GET | `/ai/traces/{trace_id}` | 链路回放 |

## 目录

```
ai-service/
├── app/
│   ├── main.py            FastAPI 入口（接口、限流、trace）
│   ├── config.py          环境变量
│   ├── agent/graph.py     LangGraph 图：prefetch → agent ⇄ tools
│   ├── tools/             工具定义（含越权校验、写操作确认）
│   ├── rag/               知识库检索（pgvector + HNSW）
│   ├── chat/              会话与工单存储
│   ├── clients/           调用 Java 服务的 HTTP 客户端 + 请求上下文
│   └── common/            限流、工具日志、链路追踪
├── data/knowledge/        售后政策知识库（15 篇 Markdown）
├── eval/                  评测集与跑批脚本
├── scripts/               知识库灌入、统计、验收脚本
└── static/chat.html       独立调试页（正式入口在商城前端）
```

## 启动

```powershell
cd D:\WorkSpace\hmall\ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # 填入 DASHSCOPE_API_KEY 和 PG_DSN
.\.venv\Scripts\python.exe run.py
```

- 健康检查 <http://127.0.0.1:8087/health>
- 接口文档 <http://127.0.0.1:8087/docs>

## 验收与统计

```powershell
.\.venv\Scripts\python.exe eval\run_eval.py       # 30 条端到端评测
.\.venv\Scripts\python.exe eval\harness.py        # 检索召回率
.\.venv\Scripts\python.exe scripts\smoke_test.py  # 10 项链路验收
.\.venv\Scripts\python.exe scripts\tool_stats.py  # 工具调用统计
.\.venv\Scripts\python.exe scripts\cost_report.py # 单轮成本
```

指标与口径见根目录 README 的「效果与指标」。

## 链路追踪

默认写本地 `logs/traces.jsonl`，按 `trace_id` 回放。需要可视化时在 `.env` 打开：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxx
LANGSMITH_PROJECT=lexuan-agent
```

业务代码无需改动（LangChain / LangGraph 自动上报）。
