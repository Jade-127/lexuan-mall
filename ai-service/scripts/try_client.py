"""开发自测脚本：不启动 Agent 服务，直接验证 trade_client。

用法（在 ai-service 目录下）：
    .\.venv\Scripts\python.exe scripts\try_client.py

前提：trade-service 已在 8085 启动，且 MySQL/Nacos 正常。
"""
import asyncio
import sys
from pathlib import Path

# 让脚本能 import app 包（脚本在 scripts/ 下，父目录才是项目根）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients import trade_client          # noqa: E402
from app.clients.context import set_user_info  # noqa: E402


async def main() -> None:
    cases = [
        ("1", "2118208508551122946", "Jack 自己的订单"),
        ("1", "123865420", "Rose 的订单（Jack 不该看到归属 userId=2）"),
        ("1", "999999999999", "不存在的订单号"),
        ("2", "123865420", "Rose 查自己的订单"),
    ]

    for user_info, order_id, desc in cases:
        set_user_info(user_info)
        result = await trade_client.get_order_detail(order_id)
        print(f"\n--- {desc} ---")
        print(f"user_info={user_info}  order={order_id}")
        print(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())
