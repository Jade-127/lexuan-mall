"""端到端评测：测的是「整条 Agent 链路」，不是单个函数。

和 D11 的 harness.py 区别：
    harness.py  只测检索：给问题，看能不能召回对的政策文档
    这个脚本    测整条链路：会不会选对工具、回答里有没有关键信息、有没有乱调工具、弹没弹确认

每条用例跑一次真实的图（带工具、带记忆），记录：调了哪些工具 / 回答 / 耗时 / 是否弹确认。

评分三件事：
    1. 工具选择：该调的调了，不该调的一个没调
    2. 关键信息：回答里必须出现的关键词（商品名、状态、金额等）
    3. 写操作：必须弹确认（eval 到这里就停，不点确认，所以不会真建单）

用法（ai-service 目录下）：
    .\\.venv\\Scripts\\python.exe eval\\run_eval.py
    .\\.venv\\Scripts\\python.exe eval\\run_eval.py --category 售后
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 默认的 ProactorEventLoop 不能跑 psycopg 异步（D8 踩过一次，这里是同一个坑）。
# 必须在创建事件循环之前切到 Selector，run.py 里也是这么干的。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.agent.graph import run_graph            # noqa: E402
from app.clients.context import set_conversation_id, set_user_info  # noqa: E402

CASES_FILE = Path("eval/agent_cases.jsonl")
REPORT_FILE = Path("eval/report.md")

# 评测统一用 jack（user_id=1），他名下有 14 笔订单、1 笔已发货，够覆盖各种状态
EVAL_USER = "1"


def load_cases(category: str | None) -> list[dict]:
    cases = []
    for line in CASES_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        case = json.loads(line)
        if category and case.get("category") != category:
            continue
        cases.append(case)
    return cases


def score(case: dict, called: list[str], answer: str, confirmed: bool) -> list[str]:
    """给一条用例打分，返回所有不合格的原因（空列表 = 通过）。"""
    problems = []
    expect = case.get("expect_tools") or []

    for tool in expect:
        if tool not in called:
            problems.append(f"没调用 {tool}")
    for tool in case.get("must_not_call") or []:
        if tool in called:
            problems.append(f"不该调用 {tool}")

    # 负例：期望不调任何工具
    if not expect and called:
        problems.append(f"负例却调了 {called}")

    if case.get("expect_confirm"):
        if not confirmed:
            problems.append("没有弹确认")
    elif confirmed:
        problems.append("不该弹确认")

    for kw in case.get("expect_keywords") or []:
        if kw not in (answer or ""):
            problems.append(f"回答里没有「{kw}」")

    return problems


async def run_case(case: dict) -> dict:
    """跑一条用例，返回结果。每条用独立的 thread_id，互不影响记忆。"""
    set_user_info(EVAL_USER)
    set_conversation_id(str(uuid.uuid4()))       # 建单时会写库，必须是合法 UUID

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            run_graph(case["question"], thread_id=f"eval:{uuid.uuid4()}"),
            timeout=90,
        )
    except Exception as exc:                      # noqa: BLE001
        return {"case": case, "error": f"{type(exc).__name__}: {exc}", "problems": ["执行异常"]}

    latency_ms = int((time.perf_counter() - started) * 1000)
    called = [t["tool"] for t in result.get("trace", []) if "tool" in t]
    confirmed = bool(result.get("interrupt"))
    answer = result.get("answer") or ""

    problems = score(case, called, answer, confirmed)
    return {
        "case": case,
        "called": called,
        "answer": answer,
        "confirmed": confirmed,
        "latency_ms": latency_ms,
        "problems": problems,
    }


def write_report(results: list[dict], tool_acc: float, kw_acc: float) -> None:
    latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
    avg = int(statistics.mean(latencies)) if latencies else 0
    p95 = int(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if latencies else 0

    lines = [
        "# 评测报告",
        "",
        f"- 用例数：{len(results)}",
        f"- 工具选择准确率：**{tool_acc:.0%}**",
        f"- 关键信息命中率：**{kw_acc:.0%}**",
        f"- 平均响应：{avg / 1000:.1f}s，P95：{p95 / 1000:.1f}s",
        "",
        "| ID | 类别 | 问题 | 调用工具 | 耗时 | 结果 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        c = r["case"]
        mark = "✅" if not r["problems"] else "❌ " + "；".join(r["problems"])
        lines.append(
            f"| {c['id']} | {c.get('category', '')} | {c['question'][:28]} "
            f"| {', '.join(r.get('called', [])) or '—'} | {r.get('latency_ms', 0) / 1000:.1f}s | {mark} |"
        )
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None, help="只跑某一类：售前/售中/售后")
    args = parser.parse_args()

    cases = load_cases(args.category)
    if not cases:
        print("没有用例，检查 eval/agent_cases.jsonl")
        return

    print(f"{'ID':<5}{'类别':<6}{'工具':<28}{'耗时':<8}结果")
    print("-" * 92)

    results = []
    for case in cases:
        r = await run_case(case)
        results.append(r)
        mark = "✅" if not r["problems"] else "❌ " + "；".join(r["problems"])
        called = ", ".join(r.get("called", [])) or "—"
        print(f"{case['id']:<5}{case.get('category', ''):<6}{called:<28}{r.get('latency_ms', 0) / 1000:<8.1f}{mark}")

    passed = sum(1 for r in results if not r["problems"])
    with_kw = [r for r in results if r["case"].get("expect_keywords")]
    kw_passed = sum(1 for r in with_kw if not any("没有「" in p for p in r["problems"]))

    tool_acc = passed / len(results)
    kw_acc = kw_passed / len(with_kw) if with_kw else 1.0

    print("-" * 92)
    print(f"通过 {passed}/{len(results)}   工具选择准确率 {tool_acc:.0%}   关键信息命中 {kw_passed}/{len(with_kw)}")

    failed = [r for r in results if r["problems"]]
    if failed:
        print("\n失败详情：")
        for r in failed:
            print(f"\n  #{r['case']['id']} {r['case']['question']}")
            print(f"    期望工具: {r['case'].get('expect_tools')}  实际: {r.get('called')}")
            print(f"    回答: {(r.get('answer') or '')[:80]}")
            print(f"    问题: {r['problems']}")

    write_report(results, tool_acc, kw_acc)
    print(f"\n报告已写入 {REPORT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
