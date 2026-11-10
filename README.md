# 乐选优品 · Lexuan Youpin

一个 **Spring Cloud 微服务电商** + **LangGraph 智能客服 Agent** 的完整项目。

> 产品名：乐选优品　｜　客服人格：小乐　｜　仓库：`lexuan-mall`

---

## 这是什么

乐选优品是一个电商系统，由两套服务组成：

- **Java 侧**：Spring Cloud 微服务（商品 / 用户 / 购物车 / 交易 / 支付 / 网关），Nacos 注册与配置、RabbitMQ 异步消息、JWT 鉴权
- **Python 侧**：`ai-service`，基于 LangGraph 的智能客服 Agent，支持商品检索、订单查询、售后政策问答（RAG）与转人工

两套服务通过网关统一暴露，前端只面对一个域名。

---

## 架构

```
浏览器 :18080
   │
   ▼
 nginx ──► hm-gateway :8080 ── JWT 校验 ──┬──► item-service   :8081
                                          ├──► cart-service   :8082
                                          ├──► user-service   :8084
                                          ├──► trade-service  :8085
                                          ├──► pay-service    :8086
                                          └──► ai-service     :8087 (Python)
                                                     │
                                    ┌────────────────┼─────────────────┐
                                    ▼                ▼                 ▼
                            阿里云百炼 qwen-plus   pgvector        Java 微服务
                            (对话 + embedding)     (知识库 RAG)    (工具调用)
```

---

## 模块

| 模块 | 端口 | 说明 |
|---|---|---|
| `hm-gateway` | 8080 | 网关，鉴权 + 路由 |
| `item-service` | 8081 | 商品 |
| `cart-service` | 8082 | 购物车 |
| `user-service` | 8084 | 用户与地址 |
| `trade-service` | 8085 | 订单 |
| `pay-service` | 8086 | 支付 |
| `ai-service` | 8087 | **智能客服 Agent（Python）** |
| `hm-common` / `hm-api` | — | 公共模块 / Feign 客户端 |
| `hm-service` | 8080 | 单体版（历史模块，与网关二选一） |

---

## 快速开始

### 1. 基础设施

| 组件 | 地址 |
|---|---|
| Nacos | `192.168.74.128:8848` |
| MySQL | `192.168.74.128:3306` |
| RabbitMQ | `192.168.74.128:5672`（vhost `/itheima`） |
| Redis | `127.0.0.1:6379` |

### 2. 启动 Java 侧

```bash
mvn clean install -DskipTests
# 依次启动 item / user / cart / trade / pay / gateway
```

或双击根目录 `start-all.cmd`。

### 3. 启动 AI 侧

```bash
cd ai-service
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 填入百炼 API Key
uvicorn app.main:app --reload --port 8087
```

### 4. 前端

```bash
# 启动 nginx（配置见 D:\Apps\hmall\hmall-nginx）
# 访问 http://localhost:18080
```

---

## 技术栈

**Java**：Spring Boot 2.7 · Spring Cloud 2021 · Nacos · Gateway · OpenFeign · MyBatis-Plus · MySQL · Redis · RabbitMQ
**Python**：FastAPI · LangGraph · LangChain · 阿里云百炼（qwen-plus / text-embedding-v3）· PostgreSQL + pgvector
**前端**：Vue2（CDN）+ nginx

---

## 文档

- [ai-service 设计文档](ai-service/docs/01-设计文档.md)
- [20 天开发计划](ai-service/docs/02-学习计划.md)
- [进度打卡板](ai-service/docs/学习计划打卡板.html)

---

## 开发进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | ai-service 骨架 + 流式对话 + 网关接入 | 🚧 |
| P1 | 工具调用（商品 / 订单）+ 身份注入 | ⏳ |
| P2 | 知识库 RAG + 转人工 | ⏳ |
| P3 | 多轮记忆 + 前端聊天页 | ⏳ |
| P4 | 评测 + 可观测 | ⏳ |

---

## 效果与指标（实测，2026-11-10）

| 指标 | 结果 | 怎么测的 |
|---|---|---|
| 评测集工具选择准确率 | **93%**（28/30） | `eval/run_eval.py`，售前 / 售中 / 售后各 10 条 |
| 关键信息命中率 | **100%**（5/5） | 同上：回答里必须出现指定关键词（状态、金额等） |
| 知识库召回率 | **100%**（20/20） | `eval/harness.py`，top-3 命中判定 |
| 工具调用成功率 | **94%**（158/169） | `scripts/tool_stats.py`，汇总真实调用日志 |
| 响应延迟 | 平均 **2.9s**，P95 **5.3s** | 30 条评测集逐条计时 |
| 单轮成本 | **¥0.0022**（输入 2571 / 输出 65 token） | `scripts/cost_report.py`，日活 1000 次 ≈ ¥2.2/天 |

> 口径说明：准确率是单轮结果，「退货建单」这条用例在前几轮有波动，多轮平均约 93%，因此不写 100%；
> 成本按 qwen-plus 公开价估算（输入 0.8 元/百万 token、输出 2 元/百万 token），实际以控制台账单为准。

### 怎么复现

```powershell
cd ai-service
.\.venv\Scripts\python.exe eval\run_eval.py            # 端到端评测 → eval/report.md
.\.venv\Scripts\python.exe eval\harness.py             # 检索召回率
.\.venv\Scripts\python.exe scripts\tool_stats.py       # 工具调用统计
.\.venv\Scripts\python.exe scripts\cost_report.py      # 单轮成本
.\.venv\Scripts\python.exe scripts\trace_show.py <id>  # 回放一次请求的链路
```

### 可观测性

每次对话生成一个 `trace_id`，贯穿「前置检索 → 模型调用 → 工具执行 → 落库」：

```
+    0ms   api.chat.start
+  600ms   prefetch.knowledge     hit=3  top=退货运费规则
+ 2099ms   graph.run              ms=2079  tool_calls=['search_knowledge']
+ 2099ms   api.chat.end           ms=2098  status=done
```

- `GET /ai/traces/{trace_id}` 回放整条链路；`logs/traces.jsonl` 本地留存
- 需要更细的分析时，`.env` 里打开 `LANGSMITH_TRACING=true` 即可接入 LangSmith（业务代码零改动）

### 已知问题

- **写操作类用例有波动**：单轮可以跑满 100%，多轮平均 93%，模型偶尔跳过 create_ticket。
  目前靠出口校验兜住（不会出现“假承诺”），根治要靠 constrained decoding 或更细的意图分类。
- **前置检索是关键词规则驱动**：靠「退 / 运费 / 快递 …」约 20 个词命中，说法绕的问题可能漏触发。
  下一步计划用小模型做意图分类替代手写规则。
- **限流存在进程内存**：只对单实例有效，多副本部署需要换成 Redis（ZSET 滑动窗口）。
- **知识库只有 15 篇**：20 条召回用例上的 100% 不代表全量覆盖，长尾政策问题仍会漏。
