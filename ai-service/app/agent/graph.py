"""LangGraph 版 Agent（多轮记忆）。

D5 的图是无状态的；D12 挂上 checkpointer + thread_id，图会把每步 state
存进 Postgres，下次同 thread_id 进来接着跑。

关于异步：
PostgresSaver 是同步实现，`ainvoke` 会去调 `aget_tuple` 然后抛 NotImplementedError。
所以这里用官方的 AsyncPostgresSaver + AsyncConnectionPool。
它的初始化是 async 的，不能在模块导入时 await，因此做成"首次使用时惰性初始化"。
"""
import asyncio
import json
import re
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from app.common import trace
from app.agent.router import classify
from app.config import settings
from app.rag.retriever import search_knowledge as search_knowledge_docs
from app.tools.shop_tools import (
    create_ticket,
    get_order_detail,
    query_my_orders,
    search_items,
    search_knowledge,
)

TOOLS = [search_items, query_my_orders, get_order_detail, search_knowledge, create_ticket]

# 命中这些词 = 政策类问题，进模型前强制检索（不靠模型自觉）
# 商品类问题：命中就先查商品库，别让模型凭印象报型号和价格
ITEM_WORDS = ["手机", "耳机", "电视", "冰箱", "洗衣机", "空调", "笔记本", "电脑", "平板", "手表", "相机", "衣服", "鞋", "包"]
PRICE_RE = re.compile(r"(\d+)\s*元")

SYSTEM = (
    "你是乐选优品的在线客服「小乐」。回答简洁：默认不超过 80 字，先给结论。"
    # ↓ 这一条是 D15 评测逼出来的：不写死，模型会凭记忆答政策，50% 的题都不查知识库
    "铁律：凡是涉及规则、政策、费用、时效、流程的问题"
    "（退换货、运费、退款到账、发票、发货时效、配送范围、尺码、客服时间），"
    "必须先调用 search_knowledge 查知识库再回答。这些政策是本店自定的，凭记忆回答一定是错的。"
    "订单状态、物流、金额这类会变的信息，必须调 query_my_orders / get_order_detail 现查，不要用上下文里的旧答案。"
    "工具没返回的信息就说不知道，不要编造订单号、价格、库存、政策。"
    "推荐类问题先调用 search_items 给出 2-3 个选项，再问用户偏好；不要一上来就反问。"
    "推荐只能引用 search_items 返回的商品和价格，绝对不要凭印象报型号或报价——我们的价格会变。"
    "用户消息里出现订单号、又要求售后处理时：先 get_order_detail 查状态，再 create_ticket，两步都必须真的调用工具。"
    "create_ticket 是写操作：用户要求退货、换货、退款、报修、转人工、投诉时，先按政策说明条件，再调用 create_ticket。"
    "『要不要建单』由界面上的确认按钮决定：你直接调用 create_ticket 就行，系统会弹卡片给用户点，"
    "不要在文字里问「要创建吗」「是否为您创建」——那样用户没法点。"
    "只有 create_ticket 返回 created=true 时，才能说「已为你创建工单」；没调工具就绝对不能说已经建单。"
    "调用前必须确认清楚『哪一笔订单』和『具体原因』——用户只说“我要退货”时，先问是哪一笔，不要直接建单。"
    "订单状态决定能做什么：已支付未发货 → 引导“申请退款”，不要回答不能退；"
    "已发货/已完成 → 才谈退货换货；待支付 → 引导取消订单。"
    "工具返回 created=false 表示用户点了取消，回复「好的，已取消，没有创建工单」就行，"
    "不要说“创建失败”或让用户重试。"
    "不要向用户索要照片、图片、截图（对话里收不到），需要材料就让客服在建单后跟进。"
)

_graph = None
_graph_lock = asyncio.Lock()


def _model():
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,   # 工具选择要稳，不要发挥
        max_tokens=500,
        timeout=30,
    )
    return llm.bind_tools(TOOLS)


# 用户消息里出现订单号 + 售后意图时，本轮必须有建单动作，不靠模型自觉
ORDER_ID_RE = re.compile(r"\b\d{16,20}\b")
WRITE_INTENT_RE = re.compile(r"退|换货|退款|报修|投诉|转人工")
HARD_RULE = (
    "本轮用户已经提供了订单号并明确要求售后处理。你必须先 get_order_detail 查状态，"
    "然后调用 create_ticket 创建工单（系统会弹确认卡片），不要只在文字里询问，不要重复问订单号。"
)


def call_model(state: MessagesState) -> dict:
    """agent 节点：把整段历史喂给模型，返回它这一轮的输出。"""
    history = [m for m in state["messages"] if not isinstance(m, SystemMessage)]

    # 兜一层硬约束：模型偶尔只答政策、不调建单工具，这里把要求并进系统提示（只保留一条 system）
    last_human = next((m for m in reversed(history) if isinstance(m, HumanMessage)), None)
    text = last_human.content if last_human and isinstance(last_human.content, str) else ""
    need_write = bool(ORDER_ID_RE.search(text) and WRITE_INTENT_RE.search(text))
    system_content = SYSTEM + "\n" + HARD_RULE if need_write else SYSTEM

    messages = [SystemMessage(content=system_content)] + history
    ai_msg = _model().invoke(messages)

    # 记 token 消耗。一次对话会调好几轮模型，所以每轮都要记，
    # 最后按 trace_id 求和才是"这一单"的成本。
    usage = getattr(ai_msg, "usage_metadata", None) or {}
    if usage:
        trace.event(
            "llm.call",
            in_tokens=usage.get("input_tokens", 0),
            out_tokens=usage.get("output_tokens", 0),
        )
    return {"messages": [ai_msg]}


async def prefetch(state: MessagesState) -> dict:
    """进模型之前先做两件事：判断问题类型，再把能确定的事实查出来。

    为什么需要这个节点：
    只靠提示词，三分之一的政策题模型会凭记忆直接答（内容还是它自己编的），
    商品推荐也一样——它会报出我们根本没卖的手机型号和价格。
    与其反复调提示词，不如在流程里保证：先分类，再按类型查库，
    把结果伪装成「已完成的工具调用」塞进历史，模型只能基于查到的事实回答。

    分类交给小模型（qwen-flash），而不是用它自己的关键词规则——
    离线 21 条用例上，小模型 21/21，关键词 17/21。

    四类各自怎么走：
        政策 → 查知识库
        订单 → 不预查，交给模型自己调 query_my_orders（要结合上下文判断查哪一笔）
        商品 → 查商品库
        闲聊 → 什么都不查
    """
    text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            text = msg.content if isinstance(msg.content, str) else ""
            break
    if not text:
        return {}

    category = await classify(text)
    trace.event("router.classify", category=category, question=text[:30])

    call_id = f"prefetch-{uuid.uuid4().hex[:8]}"

    # 1) 政策类 → 查知识库
    if category == "政策":
        hits = await search_knowledge_docs(text)
        if not hits:
            trace.event("prefetch.knowledge", hit=0)
            return {}
        trace.event("prefetch.knowledge", hit=len(hits), top=hits[0]["title"])
        payload = json.dumps(
            {"found": len(hits), "docs": [{"title": h["title"], "content": h["content"]} for h in hits]},
            ensure_ascii=False,
        )
        return _injected_call(call_id, "search_knowledge", {"question": text}, payload)

    # 2) 商品类 → 查商品库（品类词当关键词，预算从"300元"这类说法里取）
    if category == "商品":
        item = next((w for w in ITEM_WORDS if w in text), None) or text[:10]
        price = PRICE_RE.search(text)
        args = {"keyword": item}
        if price:
            args["max_price"] = int(price.group(1)) * 100      # 元 → 分
        raw = await search_items.ainvoke(args)
        trace.event("prefetch.items", keyword=item, max_price=args.get("max_price"))
        payload = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        return _injected_call(call_id, "search_items", args, payload)

    return {}


def _injected_call(call_id: str, name: str, args: dict, payload: str) -> dict:
    """伪造一次「模型已经调过工具」的历史，让模型没法忽略检索结果。"""
    return {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}]),
            ToolMessage(content=payload, tool_call_id=call_id, name=name),
        ]
    }


def build_graph(checkpointer=None):
    graph = StateGraph(MessagesState)
    graph.add_node("prefetch", prefetch)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "prefetch")
    graph.add_edge("prefetch", "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)


async def get_graph():
    """惰性初始化：第一次调用时建连接池、建表、编译图，之后复用。"""
    global _graph
    if _graph is not None:
        return _graph

    async with _graph_lock:
        if _graph is None:
            pool = AsyncConnectionPool(
                conninfo=settings.pg_dsn,
                max_size=5,
                open=False,
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await pool.open()
            saver = AsyncPostgresSaver(pool)
            await saver.setup()          # 建 checkpoints 相关表（幂等）
            _graph = build_graph(saver)
    return _graph


CLAIM_RE = re.compile(r"已(为您|为你|帮你|给您)?(创建|提交|生成|建好)(了)?(一个)?(售后)?工单")


def _guard_claim(answer: str, trace: list[dict]) -> str:
    """输出兜底：模型声称「已创建工单」，但工具没调、或调用没成功，就把这句话换掉。

    为什么需要：模型有时不调工具，却在回答里说"已为你创建工单"。对用户来说是假承诺，
    比说错话更严重。提示词压不住（评测里反复出现），所以在出口校验一次。

    为什么判两件事而不是一件：
        只看「有没有调用 create_ticket」不够——用户点「取消」时工具也被调用过，
        结果里 created=false，模型若仍说"已创建"，只看调用记录会漏掉这种假话。
    """
    if not answer or not CLAIM_RE.search(answer):
        return answer

    called = {t["tool"] for t in trace if "tool" in t}
    created = any("tool_result" in t and '"created": true' in str(t["tool_result"]) for t in trace)

    if "create_ticket" not in called or not created:
        return "抱歉，工单还没有创建成功。请告诉我订单号，我再帮你提交一次。"
    return answer


def _payload(result: dict) -> dict:
    """把图跑完（或跑到一半暂停）的结果整理成接口要的形状。"""
    messages = result["messages"]
    trace = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                trace.append({"tool": call["name"], "args": call["args"]})
        elif isinstance(msg, ToolMessage):
            trace.append({"tool_result": str(msg.content)[:160]})

    # 图停在 interrupt 时，结果里会多出一个 __interrupt__ 键，
    # 里面是工具传给 interrupt() 的那个 dict（告诉前端要确认什么）。
    interrupts = result.get("__interrupt__") or ()
    if interrupts:
        return {
            "answer": None,
            "interrupt": interrupts[0].value,
            "message_count": len(messages),
            "trace": trace,
        }

    return {
        "answer": _guard_claim(messages[-1].content, trace),
        "interrupt": None,
        "message_count": len(messages),
        "trace": trace,
    }


async def run_graph(question: str, thread_id: str | None = None) -> dict:
    """跑一次图。

    thread_id 决定"哪一段对话"：
    - 传了 → 从 checkpointer 恢复历史，接着聊
    - 没传 → 新线程（等价于无记忆，兼容旧的 /ai/agent/graph 接口）
    """
    graph = await get_graph()
    thread_id = thread_id or f"anon-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 16}

    with trace.span("graph.run", thread_id=thread_id[-32:], question=question[:40]) as s:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config=config,
        )
        payload = _payload(result)
        s["tool_calls"] = [t["tool"] for t in payload["trace"] if "tool" in t]
        s["paused"] = payload["interrupt"] is not None
    return payload


async def resume_graph(decision: bool, thread_id: str) -> dict:
    """用户点了确认/取消之后，把图从暂停的地方接着跑。

    Command(resume=...) 里的值，就是工具里 interrupt() 这一行的返回值。
    必须用同一个 thread_id，否则 checkpointer 找不到那段暂停中的状态。
    """
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 16}
    with trace.span("graph.resume", decision=decision, thread_id=thread_id[-32:]) as s:
        result = await graph.ainvoke(Command(resume=decision), config=config)
        payload = _payload(result)
        s["tool_calls"] = [t["tool"] for t in payload["trace"] if "tool" in t]
    return payload
