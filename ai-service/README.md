# ai-service · 乐选优品 · 智能客服 Agent

hmall 电商项目中的 AI 能力模块（Python / FastAPI / LangGraph / 阿里云百炼）。

> 位置：`D:\WorkSpace\hmall\ai-service`
> 说明：这是 hmall 仓库里的一个非 Maven 模块。Maven 只会构建根 `pom.xml` 里 `<modules>` 声明的模块，这个目录没有 `pom.xml`，所以**不会参与 Java 构建**，两边互不影响。

## 文档

| 文档 | 说明 |
|---|---|
| [docs/01-设计文档.md](docs/01-设计文档.md) | 架构、接口契约、数据模型、Agent/工具设计、RAG、安全、里程碑 |
| [docs/02-学习计划.md](docs/02-学习计划.md) | 知识点清单 + 20 个工作日排期 + 奖励 |
| [docs/学习计划打卡板.html](docs/学习计划打卡板.html) | 可视化进度看板（浏览器打开，可打勾） |

## 环境要求

- Python 3.11+（本机 3.11.9；LangGraph 要求 ≥3.10，**不需要 3.13**）
- 阿里云百炼 API Key

## 快速开始（D1）

```powershell
cd D:\WorkSpace\hmall\ai-service

# 1. 建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 装依赖
pip install -r requirements.txt

# 3. 准备配置
copy .env.example .env
# 打开 .env，把 DASHSCOPE_API_KEY 换成自己的

# 4. 启动
uvicorn app.main:app --reload --port 8087
```

浏览器打开 <http://127.0.0.1:8087/health>，看到 `{"status":"ok",...}` 就算 D1 完成。
接口文档在 <http://127.0.0.1:8087/docs>。

## 目录

```
ai-service/
├── app/
│   ├── main.py      FastAPI 入口
│   └── config.py    环境变量配置
├── docs/            设计与计划文档
├── requirements.txt
└── .env.example
```

后续按设计文档逐步加入 `agent/`、`rag/`、`clients/`、`db/`。

## 与 hmall 的关系

- 端口：`8087`
- 网关：`hm-gateway` 增加路由 `/ai/**` → `http://127.0.0.1:8087`，鉴权复用现有 JWT 过滤器，自动透传 `user-info`
- 数据库：独立的 PostgreSQL（pgvector），不碰业务库 MySQL
