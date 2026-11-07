"""交易服务客户端：封装对 trade-service 的调用。

关键点：调用 /orders/my 与 /orders/{id} 时必须带上 user-info 头，
否则 trade-service 拿不到 userId，只会返回空列表或报错。
"""
import json

import httpx

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


async def get_order_detail(order_id: str) -> dict | None:
    """按订单号查询订单详情。

    注意：这里故意**不**做归属判断，把 userId 原样返回给调用方，
    让工具层自己决定"不是我的订单"该怎么处理——职责分离，也便于测试。

    返回 None 表示订单不存在（或订单号格式非法）。
    """
    user_info = get_user_info()
    if not user_info:
        return None

    try:
        resp = await get_http().get(
            f"{settings.trade_service_url}/orders/{order_id}",
            headers={"user-info": user_info},
        )
    except httpx.HTTPError:
        return None

    # 订单号不是数字时后端返回 400；查不到时后端返回 200 + 空 body（null 不会序列化）
    if resp.status_code >= 400:
        return None

    body = resp.text.strip()
    if not body or body == "null":
        return None

    data = resp.json()
    if not data or data.get("id") is None:
        return None

    return {
        "orderId": str(data.get("id")),
        "userId": str(data.get("userId")),          # 归属校验要用它
        "status": STATUS_TEXT.get(data.get("status"), str(data.get("status"))),
        "totalFee": data.get("totalFee"),
        "createTime": data.get("createTime"),
        "payTime": data.get("payTime"),
    }


def dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)
