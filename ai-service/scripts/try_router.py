"""意图路由的离线验证：不连数据库、不启服务，只测分类准不准。

跑法（ai-service 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\try_router.py

20 条带标注的句子，覆盖四类 + 几条"说法绕"的难例（关键词规则会漏的那种）。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.router import _keyword_fallback, classify  # noqa: E402

CASES = [
    # （问题, 人工标注）
    ("退货运费谁出", "政策"),
    ("七天无理由从哪天开始算", "政策"),
    ("能开发票吗", "政策"),
    ("新疆要加运费吗", "政策"),
    ("你们几点下班，怎么转人工", "政策"),
    ("我的订单到哪了", "订单"),
    ("我有几笔订单", "订单"),
    ("订单 2118193045389615106 什么状态", "订单"),
    ("怎么取消订单", "订单"),
    ("物流信息在哪查", "订单"),
    ("有没有蓝牙耳机", "商品"),
    ("300 元以内的手机推荐一下", "商品"),
    ("OPPO 的手机多少钱", "商品"),
    ("想送朋友一个礼物", "商品"),
    ("荣耀8X 有货吗", "商品"),
    ("今天北京天气怎么样", "闲聊"),
    ("给我讲个笑话", "闲聊"),
    ("你是谁", "闲聊"),
    ("你好", "闲聊"),
    # 难例：关键词规则容易漏
    ("我买的那个东西坏了，能换吗", "政策"),
    ("昨天下单的什么时候能到我家", "订单"),
]


async def main() -> None:
    print(f"{'问题':<28}{'标注':<6}{'模型':<6}{'关键词':<8}结果")
    print("-" * 70)

    ok_model = ok_kw = 0
    for q, expect in CASES:
        got = await classify(q)
        await asyncio.sleep(1.2)      # 别把 QPM 打满
        kw = _keyword_fallback(q)
        ok_model += got == expect
        ok_kw += kw == expect
        mark = "✅" if got == expect else f"❌ 应为{expect}"
        print(f"{q:<28}{expect:<6}{got:<6}{kw:<8}{mark}")

    total = len(CASES)
    print("-" * 70)
    print(f"小模型分类：{ok_model}/{total} = {ok_model / total:.0%}")
    print(f"关键词规则：{ok_kw}/{total} = {ok_kw / total:.0%}   ← 现在线上用的是这个")


if __name__ == "__main__":
    asyncio.run(main())
