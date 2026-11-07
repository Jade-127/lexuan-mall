"""交易服务客户端：封装对 trade-service 的调用。

关键点：调用 /orders/my 时必须带上 user-info 头，
否则 trade-service 拿不到 userId，只会返回空列表或报错。
"""
import json

from app.clients.context import get_user_info
from app.clients.http import get_http
from app.config import settings

STATUS_TEXT = {1: "待支付", 2: "已支付", 3: "已发货", 4: "已完成", 5: "已取消"}


async def query_my_orders(status: int | None = None) -> dict:
    """查询当前登录用户的订单列表。"""
    user_info = get_user_info()
    if not user_info:
        # 没有登录信息就不要去打扰下游服务了
        return {"error": "当前用户未登录，无法查询订单"}

    params = {}
    if status is not None:
        params["status"] = status

    resp = await get_http().get(
        f"{settings.trade_service_url}/orders/my",
        params=params,
        headers={"user-info": user_info},
    )
    resp.raise_for_status()
    data = resp.json()

    orders = [
        {
            "orderId": str(o["id"]),
            "status": STATUS_TEXT.get(o.get("status"), str(o.get("status"))),
            "totalFee": o.get("totalFee"),
            "createTime": o.get("createTime"),
        }
        for o in data
    ]
    return {"count": len(orders), "orders": orders}


def dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)
