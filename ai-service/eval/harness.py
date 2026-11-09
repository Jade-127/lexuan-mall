"""检索评测框架（D11）。

做什么：
1. 读 eval/cases.jsonl（10 条问题 + 期望命中的文档）
2. 每条调 search_knowledge
3. 用 is_hit() 判断是否命中
4. 汇总召回率，列出失败用例

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


def is_hit(hits: list[dict], expect_doc: str) -> bool:
    """判断一次检索算不算命中。

    规则：
    1. expect_doc 为空字符串 → 这是「负例」（知识库本来就不该有答案）
       只有 hits 为空才算命中；如果检索出了任何文档，算失败（说明阈值没挡住噪音）
    2. expect_doc 非空 → 返回的前 3 条里，只要有任意一条的 doc_id == expect_doc，就算命中

    返回 True/False。

    ====== 下面这 6 行归你写 ======

    # 提示：
    #   负例分支：if not expect_doc: return len(hits) == 0
    #   正例分支：遍历 hits，看 h["doc_id"] 是否等于 expect_doc
    #   doc_id 形如 "03-退货运费规则"

    ================================
    """
    if not expect_doc:
        if not hits:
            return True
        else:
            return False
    else:
        for hit in hits:
            if hit["doc_id"] == expect_doc:
                return True
    return False


async def main() -> None:
    cases = [json.loads(line) for line in CASES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

    passed = 0
    failed: list[dict] = []

    print(f"{'ID':<4}{'命中':<6}{'问题':<28}期望文档")
    print("-" * 78)

    for case in cases:
        hits = await search_knowledge(case["question"])
        ok = is_hit(hits, case["expect_doc"])
        passed += int(ok)

        mark = "✅" if ok else "❌"
        print(f"{case['id']:<4}{mark:<6}{case['question']:<28}{case['expect_doc'] or '（负例）'}")

        if not ok:
            failed.append({
                "case": case,
                "top_titles": [f"{h['title']}({h['score']:.2f})" for h in hits[:3]],
            })

    total = len(cases)
    rate = passed / total * 100
    print("-" * 78)
    print(f"召回率：{passed}/{total} = {rate:.0f}%")

    if failed:
        print("\n失败用例：")
        for f in failed:
            print(f"\n  #{f['case']['id']} {f['case']['question']}")
            print(f"    期望: {f['case']['expect_doc'] or '（应为空）'}")
            print(f"    实际: {f['top_titles'] or '（空）'}")

    if rate < 80:
        print("\n⚠️ 召回率低于 80%，先别调阈值，去找原因：文档缺内容？表述不匹配？")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
