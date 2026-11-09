"""LangGraph 版 Agent（D12：多轮记忆）。

D5 的图是无状态的；D12 挂上 checkpointer + thread_id，图会把每步 state
存进 Postgres，下次同 thread_id 进来接着跑。

关于异步：
PostgresSaver 是同步实现，`ainvoke` 会去调 `aget_tuple` 然后抛 NotImplementedError。
所以这里用官方的 AsyncPostgresSaver + AsyncConnectionPool。
它的初始化是 async 的，不能在模块导入时 await，因此做成"首次使用时惰性初始化"。
"""
import asyncio
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from app.config import settings
from app.tools.shop_tools import (
    create_ticket,
    get_order_detail,
    query_my_orders,
    search_items,
    search_knowledge,
)

TOOLS = [search_items, query_my_orders, get_order_detail, search_knowledge, create_ticket]

SYSTEM = (
    "你是乐选优品的在线客服「小乐」。"
    "回答问题优先使用工具提供的事实，不要编造订单号、价格、库存、物流、政策。"
    "工具没返回的信息就说不知道。"
    "回答简洁：默认不超过 80 字，先给结论。"
    "订单状态、物流、价格这类会变的信息，每次都要重新调工具查，不要用上下文里的旧答案。"
    "create_ticket 是写操作：只在用户明确要转人工/投诉/申请售后时调用，调用前先说一句你要做什么；"
    "用户取消后不要再重复调用同一个工单。"
)

_graph = None
_graph_lock = asyncio.Lock()


def _model():
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        temperature=0.3,
        max_tokens=500,
        timeout=30,
    )
    return llm.bind_tools(TOOLS)


def call_model(state: MessagesState) -> dict:
    """agent 节点：把整段历史喂给模型，返回它这一轮的输出。"""
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM)] + list(messages)
    ai_msg = _model().invoke(messages)
    return {"messages": [ai_msg]}


def build_graph(checkpointer=None):
    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
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
        "answer": messages[-1].content,
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
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 10}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config=config,
    )
    return _payload(result)


async def resume_graph(decision: bool, thread_id: str) -> dict:
    """用户点了确认/取消之后，把图从暂停的地方接着跑。

    Command(resume=...) 里的值，就是工具里 interrupt() 这一行的返回值。
    必须用同一个 thread_id，否则 checkpointer 找不到那段暂停中的状态。
    """
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 10}
    result = await graph.ainvoke(Command(resume=decision), config=config)
    return _payload(result)
