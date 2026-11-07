"""给模型用的工具定义（D6：真实接口版）。

分工：
- app/clients/item_client.py  负责"怎么调 HTTP"
- 这个文件负责"告诉模型有哪些工具、什么时候用"

注意两个 @tool 函数都是 async 的：ToolNode 在异步图里会自动 await，
这样调 Java 接口时不会阻塞事件循环。
"""
import json

from langchain_core.tools import tool

from app.clients import item_client, trade_client


@tool
async def search_items(
    keyword: str,
    min_price: int | None = None,
    max_price: int | None = None,
) -> str:
    """按关键词和价格上限（单位：分）搜索在售商品。

    什么时候用：用户问"有没有 / 推荐 / 多少钱 / 哪个好"这类商品相关的问题。
    不要用于：订单、物流、退款、支付等售后问题。
    """
    data = await item_client.search_items(
        keyword=keyword,
        min_price=min_price,
        max_price=max_price,
        page_size=5,
    )
    return json.dumps(data, ensure_ascii=False)


@tool
async def query_my_orders(status: int | None = None) -> str:
    """查询当前登录用户自己的订单列表，只能查本人，不能查别人。

    什么时候用：用户问"我的订单 / 买了啥 / 发货了吗 / 到哪了"。
    不要用于：商品推荐、价格咨询。
    状态码：1 待支付 2 已支付 3 已发货 4 已完成 5 已取消。
    """
    # 注意：参数里没有 userId，userId 由 trade_client 从请求上下文里取，
    # 模型无法伪造，这是防越权的关键。
    data = await trade_client.query_my_orders(status=status)
    return json.dumps(data, ensure_ascii=False)
