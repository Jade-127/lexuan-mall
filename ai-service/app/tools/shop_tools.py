"""给模型用的工具定义（D7：真实接口 + 越权校验 + 调用日志）。

分工：
- app/clients/*      负责"怎么调 HTTP"
- 这个文件          负责"告诉模型有哪些工具、什么时候用、以及安全校验"

注意所有 @tool 函数都是 async 的：ToolNode 在异步图里会自动 await，
这样调 Java 接口时不会阻塞事件循环。
"""
import asyncio
import json

from langchain_core.tools import tool
from langgraph.types import interrupt

from app.chat import store
from app.clients import item_client, trade_client
from app.clients.context import get_conversation_id, get_user_info
from app.common.tool_log import tool_span
from app.rag.retriever import search_knowledge as search_knowledge_docs


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


@tool
async def search_knowledge(question: str) -> str:
    """检索乐选优品的售后政策知识库（退换货、运费、退款、支付、配送、发票等规则）。

    什么时候用：用户问"能不能退""运费谁出""多久到""怎么开发票"这类规则问题。
    不要用于：查具体订单状态（用 query_my_orders）、找商品（用 search_items）。

    返回命中的政策文档片段；如果没有任何相关内容，会返回 found=0，
    这时你必须回答"没有查到相关规定"，绝对不要凭记忆编造政策。
    """
    with tool_span("search_knowledge", {"question": question}) as span:
        hits = await search_knowledge_docs(question)

        if not hits:
            span["error"] = "NO_HIT"       # 记下来，方便统计"知识库覆盖不到的问题"
            return json.dumps(
                {"found": 0, "message": "知识库中没有查到相关规定"}, ensure_ascii=False
            )

        docs = [{"title": h["title"], "content": h["content"], "score": round(h["score"], 3)} for h in hits]
        return json.dumps({"found": len(docs), "docs": docs}, ensure_ascii=False)


async def _resolve_order(order_id: str | None) -> tuple[str | None, str | None]:
    """建单前先把「退哪一笔」确定下来。

    为什么放在代码里而不是只靠提示词：
    模型看到"我要退货"就可能直接建单，但客服根本不知道是哪一单，工单建了也没法处理。
    这里用代码兜底：没给订单号就查用户自己的订单——
      0 笔 → 告诉他没订单
      1 笔 → 直接用这一笔
      多笔 → 列出前 3 笔，让模型去问用户
    返回 (确认的订单号, 需要追问用户的话)；第二个不为 None 时就不该继续建单。
    """
    if order_id:
        return str(order_id), None

    data = await trade_client.query_my_orders()
    orders = (data or {}).get("orders") or []
    if not orders:
        return None, "你名下还没有订单，暂时没法创建售后工单。有其他问题我可以帮你查。"
    if len(orders) == 1:
        return str(orders[0]["orderId"]), None

    lines = []
    for o in orders[:3]:
        fee = o.get("totalFee", 0) or 0
        lines.append(f"- {o['orderId']}（{o.get('status', '')}，{fee / 100:.2f} 元）")
    return None, (
        f"你名下有 {len(orders)} 笔订单，需要先确认是哪一笔：\n"
        + "\n".join(lines)
        + "\n请问要处理哪一笔？把订单号发我就行。"
    )


@tool
async def create_ticket(reason: str, order_id: str | None = None) -> str:
    """为用户创建售后/人工工单，会有真人客服跟进处理。

    这是「写操作」，会先让用户在界面上点确认，同意之后才真正落库。
    什么时候用：用户要转人工、要投诉、要申请售后处理，而知识库和订单工具没法直接解决时。
    不要用于：普通咨询、查订单、找商品。

    reason 写清楚要处理什么（如"申请退货：商品破损"）；order_id 能确定就传，不确定传 null，
    工具会帮你去查用户名下的订单并反过来问你。
    """
    with tool_span("create_ticket", {"reason": reason, "order_id": order_id}) as span:
        # 先确认「退哪一单」。模型很可能在用户只说"我要退货"时就调这个工具，
        # 这种工单建出来客服也没法处理，所以在代码里兜住：查不到唯一订单就反问用户。
        order_id, ask = await _resolve_order(order_id)
        if ask:
            span["error"] = "NEED_ORDER"
            return json.dumps({"created": False, "need_user_input": True, "message": ask}, ensure_ascii=False)

        # 关键：interrupt 放最前面，它前面不要写任何"有副作用"的代码。
        # 因为用户确认后，这个工具函数会从头再跑一遍（interrupt 这次直接返回用户的选择），
        # 放在它前面的写库/发消息会被执行两次。
        decision = interrupt({
            "action": "create_ticket",
            "title": "需要你确认",
            "summary": f"为你创建售后工单：{reason}（订单 {order_id}）",
            "order_id": order_id,
        })

        # 用户点了什么，就是 interrupt() 的返回值。
        if not decision:
            return json.dumps({"created": False, "message": "好的，已取消，没有创建工单"}, ensure_ascii=False)

        # 只有用户同意后才走到这里，而且 user_id 来自服务端上下文，模型改不了
        conv_id = get_conversation_id()
        user_id = int(get_user_info())
        ticket_id = await asyncio.to_thread(store.create_ticket, conv_id, user_id, reason, order_id)

        return json.dumps(
            {
                "created": True,
                "ticket_id": ticket_id,
                "message": f"已创建工单 {ticket_id}，客服会在 24 小时内联系你",
            },
            ensure_ascii=False,
        )
