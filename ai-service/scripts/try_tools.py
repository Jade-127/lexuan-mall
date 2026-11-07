"""开发自测：工具层的三种情况（自己单 / 别人单 / 不存在）。

用法（在 ai-service 目录下）：
    .\.venv\Scripts\python.exe scripts\try_tools.py

注意：必须在**同一个事件循环**里跑完所有用例。
如果分多次 asyncio.run，httpx 单例会绑定到第一个（已关闭）的循环，
第二次调用就会报 "Event loop is closed" —— 这是我们踩过的坑。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.context import set_user_info          # noqa: E402
from app.tools.shop_tools import get_order_detail      # noqa: E402


async def main() -> None:
    set_user_info("1")   # 假装是 Jack

    cases = [
        ("2118208508551122946", "Jack 自己的订单"),
        ("123865420",           "Rose 的订单（应被拒绝）"),
        ("999999999999",        "不存在的订单号"),
    ]

    for order_id, desc in cases:
        result = await get_order_detail.ainvoke({"order_id": order_id})
        print(f"\n--- {desc} ---")
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
