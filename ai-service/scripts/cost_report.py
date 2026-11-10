"""单轮成本统计（D17）。

数据来源：logs/traces.jsonl 里 call_model 记的 llm.call 事件（每轮模型调用记一次）。

为什么要算这个：
面试官问"这东西上线一个月多少钱"的时候，答"不贵"等于没答。
能说出"一次对话约 2400 token、3 分钱，日活 1000 就是 90 块/天"，才是真做过。

价格写死在下面，改价只改这一处（按阿里云百炼 qwen-plus 公开价估算，以控制台为准）。

用法（ai-service 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\cost_report.py
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

LOG_FILE = Path("logs/traces.jsonl")

# qwen-plus 价格（元 / 千 token）
PRICE_IN = 0.0008
PRICE_OUT = 0.002


def main() -> None:
    if not LOG_FILE.exists():
        print(f"没有 {LOG_FILE}，先跑几次对话")
        return

    per_trace: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "calls": 0, "ms": 0})
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        tid = e.get("trace_id")
        if not tid:
            continue
        if e.get("stage") == "llm.call":
            per_trace[tid]["in"] += e.get("in_tokens", 0)
            per_trace[tid]["out"] += e.get("out_tokens", 0)
            per_trace[tid]["calls"] += 1
        elif e.get("stage", "").startswith("graph."):
            per_trace[tid]["ms"] += e.get("ms", 0)

    traces = {k: v for k, v in per_trace.items() if v["calls"] > 0}
    if not traces:
        print("还没有记录到 token 数据（需要重启服务后再对话）")
        return

    rows = []
    for tid, v in traces.items():
        cost = v["in"] / 1000 * PRICE_IN + v["out"] / 1000 * PRICE_OUT
        rows.append((tid, v, cost))
    rows.sort(key=lambda r: -r[2])

    total_cost = sum(r[2] for r in rows)
    avg_in = statistics.mean(v["in"] for _, v, _ in rows)
    avg_out = statistics.mean(v["out"] for _, v, _ in rows)
    avg_calls = statistics.mean(v["calls"] for _, v, _ in rows)
    avg_cost = total_cost / len(rows)

    print(f"共 {len(rows)} 次对话，总成本 ¥{total_cost:.4f}\n")
    print(f"平均每轮：输入 {avg_in:.0f} token，输出 {avg_out:.0f} token，"
          f"调模型 {avg_calls:.1f} 次，成本 ¥{avg_cost:.5f}")
    print(f"按日活 1000 次估算：¥{avg_cost * 1000:.2f} / 天，"
          f"¥{avg_cost * 1000 * 30:.0f} / 月\n")

    print(f"{'trace_id':<14}{'模型调用':<10}{'输入':<10}{'输出':<10}{'成本(元)':<12}耗时")
    print("-" * 66)
    for tid, v, cost in rows[:10]:
        print(f"{tid:<14}{v['calls']:<10}{v['in']:<10}{v['out']:<10}{cost:<12.5f}{v['ms']}ms")


if __name__ == "__main__":
    main()
