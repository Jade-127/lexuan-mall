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
