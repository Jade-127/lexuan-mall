"""假工具：先用写死的数据把机制跑通，D6 再换成真实接口。

注意每个 docstring：它就是给模型看的"使用说明"，
写清楚「什么时候用」比写清楚「内部怎么实现」重要得多。
"""
import json

from langchain_core.tools import tool

# 假装这是数据库里的商品（价格单位：分）
FAKE_ITEMS = [
    {"id": 1001, "name": "某品牌旗舰手机 12+256G", "price": 299900, "stock": 12},
    {"id": 1002, "name": "某品牌中端手机 8+128G", "price": 159900, "stock": 30},
    {"id": 1003, "name": "某品牌超薄笔记本 14 英寸", "price": 499900, "stock": 5},
]

# 假装这是当前登录用户的订单
FAKE_ORDERS = [
    {"orderId": "2118201300929163265", "status": "待支付", "totalFee": 181200},
    {"orderId": "2118193045389615106", "status": "已支付", "totalFee": 181200},
]


@tool
def search_items(keyword: str, max_price: int | None = None) -> str:
    """按关键词和价格上限（单位：分）搜索在售商品。

    什么时候用：用户问"有没有 / 推荐 / 多少钱 / 哪个好"这类商品相关的问题。
    不要用于：订单、物流、退款、支付等售后问题。
    """
    hits = [i for i in FAKE_ITEMS if keyword in i["name"]]
    if max_price is not None:
        hits = [i for i in hits if i["price"] <= max_price]
    if not hits:
        return json.dumps({"found": 0, "items": []}, ensure_ascii=False)
    return json.dumps({"found": len(hits), "items": hits}, ensure_ascii=False)


@tool
def query_my_orders(status: str | None = None) -> str:
    """查询当前登录用户自己的订单列表，只能查本人，不能查别人。

    什么时候用：用户问"我的订单 / 买了啥 / 发货了吗 / 到哪了"。
    不要用于：商品推荐、价格咨询。
    """
    hits = FAKE_ORDERS
    if status:
        hits = [o for o in hits if o["status"] == status]
    return json.dumps({"count": len(hits), "orders": hits}, ensure_ascii=False)