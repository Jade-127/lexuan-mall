"""检索评测框架（D11）。

做什么：
1. 读 eval/cases.jsonl（问题 + 期望命中的文档，可多个）
2. 每条调 search_knowledge
3. 用 is_hit() 判断是否命中
4. 汇总召回率，列出失败用例

为什么 expect_doc 允许是数组：
同一个问题可能有两篇文档都合法（比如"商品有问题运费谁承担"，
「退货运费规则」和「质量问题处理」都写了）。只认一篇会误判成失败，
这叫"标注歧义"，业界通常允许标注多个可接受答案。

用法（ai-service 目录下）：
    .\.venv\Scripts\python.exe eval\harness.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.retriever import search_knowledge  # noqa: E402

CASES_FILE = Path("eval/cases.jsonl")


def is_hit(hits: list[dict], expect_docs: list[str]) -> bool:
    """判断一次检索算不算命中。

    规则：
    1. expect_docs 为空 → 负例：只有 hits 为空才算命中
    2. expect_docs 非空 → 返回的结果里，只要有任意一条的 doc_id 在 expect_docs 里，就算命中
    """
    if not expect_docs:                    # 负例
        return not hits
    return any(h["doc_id"] in expect_docs for h in hits)


async def main() -> None:
    cases = []
    for line in CASES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        # 兼容两种写法：字符串 或 字符串数组，统一成数组
        # 注意：空字符串要变成空数组（否则 [""] 会被当成"有期望文档"）
        exp = case.get("expect_doc", [])
        if isinstance(exp, str):
            exp = [exp] if exp.strip() else []
        case["expect_docs"] = exp
        cases.append(case)

    passed = 0
    failed: list[dict] = []

    print(f"{'ID':<4}{'命中':<6}{'问题':<34}期望文档")
    print("-" * 88)

    for case in cases:
        hits = await search_knowledge(case["question"])
        ok = is_hit(hits, case["expect_docs"])
        passed += int(ok)

        mark = "✅" if ok else "❌"
        expect_text = "、".join(case["expect_docs"]) if case["expect_docs"] else "（负例）"
        print(f"{case['id']:<4}{mark:<6}{case['question']:<34}{expect_text}")

        if not ok:
            failed.append({
                "case": case,
                "top_titles": [f"{h['title']}({h['score']:.2f})" for h in hits[:3]],
            })

    total = len(cases)
    rate = passed / total * 100
    print("-" * 88)
    print(f"召回率：{passed}/{total} = {rate:.0f}%")

    if failed:
        print("\n失败用例：")
        for f in failed:
            print(f"\n  #{f['case']['id']} {f['case']['question']}")
            print(f"    期望: {'、'.join(f['case']['expect_docs']) or '（应为空）'}")
            print(f"    实际: {f['top_titles'] or '（空）'}")

    if rate < 80:
        print("\n⚠️ 召回率低于 80%，先别调阈值，去找原因：文档缺内容？表述不匹配？")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
