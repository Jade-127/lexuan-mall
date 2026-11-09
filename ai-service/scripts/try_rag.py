"""知识库检索自测（D8）。

用法（ai-service 目录下）：
    .\.venv\Scripts\python.exe scripts\try_rag.py

关注点：
1. 相关政策问题能否命中正确文档，分数多少
2. 无关问题是否返回空（阈值生效）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.retriever import search_knowledge  # noqa: E402

QUESTIONS = [
    "退货的运费谁出？",
    "支持哪些支付方式？",
    "发票怎么开？",
    "今天天气怎么样？",          # 应该返回空
    "你们老板是谁？",            # 应该返回空
]


async def main() -> None:
    for q in QUESTIONS:
        hits = await search_knowledge(q)
        print(f"\n=== {q} ===")
        if not hits:
            print("  （无结果，低于阈值 → 应当回答“没有查到相关规定”）")
            continue
        for h in hits:
            print(f"  [{h['score']:.3f}] {h['title']}")


if __name__ == "__main__":
    asyncio.run(main())
