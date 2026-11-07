"""LangGraph 版 Agent（D5）。

对比 D4 的 manual_loop.py：那边是我们自己写 while、自己判断、自己执行工具；
这边把「决策 → 执行 → 回灌」画成了一张图，由 LangGraph 调度。

三个核心件：
- MessagesState：预置 state，只有一个字段 messages，并自带 add_messages reducer（追加 + 去重）
- ToolNode：给定工具列表，自动执行模型请求的 tool_calls，并把结果变成 ToolMessage
- tools_condition：条件边，看最后一条消息有没有 tool_calls → 有就去 "tools"，没有就 END
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings
from app.tools.demo_tools import query_my_orders, search_items

TOOLS = [search_items, query_my_orders]

SYSTEM = (
    "你是乐选优品的在线客服「小乐」。"
    "回答问题优先使用工具提供的事实，不要编造订单号、价格、库存、物流。"
    "工具没返回的信息就说不知道。"
    "回答简洁：默认不超过 80 字，先给结论。"
)


def _model():
    """每次调用返回一个绑定了工具的模型。"""
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
    """agent 节点：把整段历史喂给模型，返回它这一轮的输出。

    注意：这里返回的是 {"messages": [ai_msg]}，
    LangGraph 会用 add_messages 追加到 state，而不是覆盖。
    """
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM)] + list(messages)
    ai_msg = _model().invoke(messages)
    return {"messages": [ai_msg]}


def build_graph():
    """画图：agent ⇄ tools，由 tools_condition 决定什么时候停。"""
    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    # 条件边：最后一条消息有 tool_calls → "tools"；没有 → END
    graph.add_conditional_edges("agent", tools_condition)
    # 工具执行完必须回到 agent，让它把结果翻译成人话
    graph.add_edge("tools", "agent")
    return graph.compile()


# 编译一次，全局复用（编译有开销，别每次请求都编译）
GRAPH = build_graph()


async def run_graph(question: str) -> dict:
    """跑一次图，并把工具调用轨迹整理出来，方便和 D4 对比。"""
    result = await GRAPH.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"recursion_limit": 10},  # 保命：最多走 10 步
    )

    messages = result["messages"]
    trace = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                trace.append({"tool": call["name"], "args": call["args"]})
        elif isinstance(msg, ToolMessage):
            trace.append({"tool_result": str(msg.content)[:160]})

    final = messages[-1]
    return {
        "answer": final.content,
        "message_count": len(messages),  # 对比 D4 的 rounds，看框架多存了哪些消息
        "trace": trace,
    }
