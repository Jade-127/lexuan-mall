"""商品服务客户端：封装对 item-service 的调用。"""
import json

from app.clients.http import get_http
from app.config import settings


async def search_items(
    keyword: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    page_size: int = 5,
) -> dict:
    """调用 item-service 的 /items/search，返回精简后的商品列表。

    返回结构故意做「瘦身」：只给模型它需要判断的字段，
    字段越少，模型越不容易乱编，token 也越省。
    """
    params = {"pageNo": 1, "pageSize": page_size}
    if keyword:
        params["keyword"] = keyword
    if min_price is not None:
        params["minPrice"] = min_price
    if max_price is not None:
        params["maxPrice"] = max_price

    resp = await get_http().get(f"{settings.item_service_url}/items/search", params=params)
    resp.raise_for_status()
    data = resp.json()

    items = [
        {
            "id": str(i["id"]),
            "name": i["name"],
            "price": i["price"],       # 单位：分
            "stock": i["stock"],
        }
        for i in data.get("list", [])
    ]
    return {"found": int(data.get("total", 0) or 0), "items": items}


def dumps(obj: dict) -> str:
    """工具统一用这个序列化，ensure_ascii=False 让中文原样输出。"""
    return json.dumps(obj, ensure_ascii=False)
