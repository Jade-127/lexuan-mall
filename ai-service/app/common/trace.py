"""请求级链路追踪（D16）。

和 D7 的工具日志什么关系：
- tool_log.py  只记「工具被调用」这一层，出事时才看
- trace.py     记「一次对话从头到尾」：哪一步开始、哪一步结束、各花多久、中间有没有走前置检索

为什么不直接用 LangSmith：
它确实更专业（可视化、对比、数据集），但要 API Key + 外网。这套本地实现
字段名刻意和 LangSmith 对齐（trace_id / run 名 / 耗时 / 输入输出），
将来想切换，只要在 .env 里开 LANGCHAIN_TRACING_V2 就行，业务代码不用动。

一行日志长这样：
{"ts":"2026-11-10T17:40:01","trace_id":"a1b2c3","stage":"tool.search_items","ms":312,"ok":true}
"""
import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
TRACE_FILE = LOG_DIR / "traces.jsonl"

logger = logging.getLogger("trace")

# 一次请求一个 trace_id，放在 contextvar 里，工具/节点里随手就能拿到
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace() -> str:
    """请求入口调用：开一条新链路。"""
    tid = uuid.uuid4().hex[:12]
    _trace_id.set(tid)
    return tid


def current_trace() -> str | None:
    return _trace_id.get()


def _write(record: dict) -> None:
    """写一行；日志失败绝不能影响主流程。"""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with TRACE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("写链路日志失败: %s", exc)


def event(stage: str, **fields) -> None:
    """记一个瞬时事件，比如 prefetch 命中了几篇文档。"""
    _write({
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "trace_id": current_trace(),
        "stage": stage,
        **fields,
    })


@contextmanager
def span(stage: str, **fields):
    """记一段有开始和结束的过程，自动算耗时。

    用法：
        with span("graph.run", question=q) as s:
            ...
            s["tools"] = called      # 想额外记点啥，往这个 dict 里塞
    """
    started = time.perf_counter()
    extra: dict = {}
    ok = True
    try:
        yield extra
    except Exception as exc:  # noqa: BLE001
        ok = False
        extra["error"] = f"{type(exc).__name__}: {exc}"[:200]
        raise
    finally:
        _write({
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "trace_id": current_trace(),
            "stage": stage,
            "ms": int((time.perf_counter() - started) * 1000),
            "ok": ok,
            **fields,
            **extra,
        })
