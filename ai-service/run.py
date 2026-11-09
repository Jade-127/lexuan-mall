"""服务启动入口（Windows 专用兼容处理）。

为什么不用 `uvicorn app.main:app` 直接启动：
psycopg 的异步连接（我们用它做 checkpointer 持久化）不能在 Windows 默认的
ProactorEventLoop 上运行，会报：
    Psycopg cannot use the 'ProactorEventLoop' to run in async mode.

事件循环策略必须在 asyncio.run() 之前设置，uvicorn 命令行启动时已经晚了，
所以这里用脚本先设策略，再交给 uvicorn。

用法（ai-service 目录下）：
    .\.venv\Scripts\python.exe run.py
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8087,
        reload=False,      # reload 子进程会丢掉事件循环策略，开发期手动重启
    )
