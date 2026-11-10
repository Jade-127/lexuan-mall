"""工具调用日志。

为什么先用 JSONL 文件而不是数据库：
1. D8 才起 PostgreSQL，现在没有表可写
2. JSONL 一行一条，追加写、不锁表，出问题也不影响主流程
3. 之后迁到 ai_tool_log 表时，这个模块的接口不用变

一行长这样：
{"ts": "2026-11-07T18:50:00", "tool": "get_order_detail", "args": {"order_id": "123"}, "ok": false, "error": "FORBIDDEN", "ms": 12}
"""
import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.common.trace import current_trace

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "tool_calls.jsonl"

logger = logging.getLogger("tool_log")


def _write(record: dict) -> None:
    """写一行 JSONL。日志失败绝不能影响主流程，所以整体 try 住。"""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("写工具日志失败: %s", exc)


@contextmanager
def tool_span(tool_name: str, args: dict | None = None):
    """用 with 包住工具逻辑，自动记录耗时和成败。

    用法：
        with tool_span("get_order_detail", {"order_id": order_id}) as span:
            ...
            span["error"] = "FORBIDDEN"     # 出错时标记一下
            return ...
    最后写入：工具名、参数、耗时、是否成功、错误原因。
    """
    started = time.perf_counter()
    span = {"error": None}
    try:
        yield span
    finally:
        ms = int((time.perf_counter() - started) * 1000)
        _write({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "trace_id": current_trace(),          # 和链路日志串起来
            "tool": tool_name,
            "args": args or {},
            "ok": span["error"] is None,
            "error": span["error"],
            "ms": ms,
        })
