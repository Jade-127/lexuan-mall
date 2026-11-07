"""给模型用的工具定义（D7：真实接口 + 越权校验 + 调用日志）。

分工：
- app/clients/*      负责"怎么调 HTTP"
- 这个文件          负责"告诉模型有哪些工具、什么时候用、以及安全校验"

注意所有 @tool 函数都是 async 的：ToolNode 在异步图里会自动 await，
这样调 Java 接口时不会阻塞事件循环。
"""
import json

from langchain_core.tools import tool

from app.clients import item_client, trade_client
from app.clients.context import get_user_info
from app.common.tool_log import tool_span


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
    with tool_span("search_items", {"keyword": keyword, "min_price": min_price, "max_price": max_price}):
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
    # 参数里没有 userId，userId 由 trade_client 从请求上下文里取，模型无法伪造
    with tool_span("query_my_orders", {"status": status}) as span:
        data = await trade_client.query_my_orders(status=status)
        if "error" in data:
            span["error"] = "UNAUTHENTICATED"
        return json.dumps(data, ensure_ascii=False)


@tool
async def get_order_detail(order_id: str) -> str:
    """根据订单号查询订单详情，只能查当前登录用户自己的订单。

    什么时候用：用户明确给出了订单号（如"订单 2118208508551122946 到哪了"），
    或订单列表中只有一个订单、需要看细节时。
    不要用于：查询订单列表（那用 query_my_orders）。
    """
    with tool_span("get_order_detail", {"order_id": order_id}) as span:
        order = await trade_client.get_order_detail(order_id)

        # 1. 查不到
        if not order:
            span["error"] = "NOT_FOUND"
            return json.dumps({"error": "订单不存在或单号不正确"}, ensure_ascii=False)

        # 2. 越权：不是当前登录用户的订单
        if str(order["userId"]) != str(get_user_info()):
            span["error"] = "FORBIDDEN"
            return json.dumps({"error": "该订单不属于当前用户，无法查询"}, ensure_ascii=False)

        # 3. 正常返回，顺手抹掉不需要给模型看的字段
        order.pop("userId", None)
        return json.dumps(order, ensure_ascii=False)
