"""工具调用统计（D16）：把 logs/tool_calls.jsonl 汇总成一张表。

为什么需要它：
评测集只覆盖「我想到的问题」，线上真实流量才是大头。
这个脚本用来回答三个问题：
    1. 哪个工具最常被调用？（决定优化优先级）
    2. 哪个工具失败最多？失败原因分布是什么？
    3. 哪个工具最慢？（P95 比平均值更有说服力）

用法（ai-service 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\tool_stats.py
"""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

LOG_FILE = Path("logs/tool_calls.jsonl")


def p95(values: list[int]) -> int:
    if not values:
        return 0
    return sorted(values)[max(0, int(len(values) * 0.95) - 1)]


def main() -> None:
    if not LOG_FILE.exists():
        print(f"没有日志文件：{LOG_FILE}（先跑几次对话）")
        return

    records = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # 半行（进程被杀）直接跳过

    if not records:
        print("日志是空的")
        return

    by_tool: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_tool[r.get("tool", "?")].append(r)

    print(f"共 {len(records)} 次工具调用，{len(by_tool)} 个工具\n")
    print(f"{'工具':<20}{'次数':<8}{'成功率':<10}{'平均ms':<10}{'P95 ms':<10}主要错误")
    print("-" * 78)

    for tool, items in sorted(by_tool.items(), key=lambda kv: -len(kv[1])):
        total = len(items)
        ok = sum(1 for i in items if i.get("ok"))
        ms = [i.get("ms", 0) for i in items]
        errors = Counter(i["error"] for i in items if i.get("error"))
        err_text = "、".join(f"{k}×{v}" for k, v in errors.most_common(3)) or "—"
        print(
            f"{tool:<20}{total:<8}{ok / total:<10.0%}"
            f"{statistics.mean(ms):<10.0f}{p95(ms):<10}{err_text}"
        )

    # 全局新鲜度：日志跨了好几天，看最近一天的量更真实
    dates = Counter(r.get("ts", "")[:10] for r in records)
    print("\n按日期：", "，".join(f"{d} {n} 次" for d, n in sorted(dates.items())))


if __name__ == "__main__":
    main()
