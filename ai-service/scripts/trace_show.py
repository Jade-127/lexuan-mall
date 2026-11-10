"""把一次请求的链路打印成时间线（D16 补做）。

跑法（ai-service 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\trace_show.py <trace_id>

trace_id 从哪来：/ai/chat 的返回里有 trace_id 字段，或者看 logs/traces.jsonl 最后几行。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("logs/traces.jsonl")


def load(trace_id: str) -> list[dict]:
    """读出某个 trace_id 的所有事件。"""
    events = []
    if not LOG_FILE.exists():
        return events
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        # ===== 空 1（你写）=====
        # 只把 trace_id 对得上的收进来：if record[...] == ...:
        # （提示：字段名就叫 trace_id）
        if record["trace_id"] == trace_id:
            events.append(record)
    return events


def fmt_tail(e: dict) -> str:
    """把事件里有用的字段拼成一行尾巴，已经写好了。"""
    parts = []
    for key in ("hit", "top", "keyword", "ms", "status", "tool_calls"):
        if key in e:
            parts.append(f"{key}={e[key]}")
    return "  ".join(parts)


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/trace_show.py <trace_id>")
        return

    trace_id = sys.argv[1]
    events = load(trace_id)
    if not events:
        print(f"没找到 trace_id={trace_id}，去 logs/traces.jsonl 里找找")
        return

    base = datetime.fromisoformat(events[0]["ts"])
    print(f"{trace_id}  共 {len(events)} 个事件")
    print("-" * 56)

    for e in events:
        t = datetime.fromisoformat(e["ts"])
        # ===== 空 2（你写）=====
        # 算出 e 相对第一条事件过了多少毫秒，取整数
        # 提示：(t - base).total_seconds() * 1000
        offset = (t - base).total_seconds() * 1000

        # ===== 空 3（你写）=====
        # 拼一行打印出来，格式：  +600ms   prefetch.knowledge    命中 3 篇
        # 提示：f"+{offset:>5.0f}ms   {e['stage']:<22} {fmt_tail(e)}"
        print(f"+{offset:>5.0f}ms   {e['stage']:<22} {fmt_tail(e)}")


if __name__ == "__main__":
    main()
