"""手写版 tool-call 循环（D4）。

为什么手写：先把「模型决策 → 代码执行 → 结果回灌 → 再问一次」这个循环
亲手跑一遍，明天 D5 用 LangGraph 的 create_react_agent 替换它时，
你才知道框架替你省掉了哪几行。
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.tools.demo_tools import query_my_orders, search_items

# 工具清单：模型能看到的「菜单」
TOOLS = [search_items, query_my_orders]
TOOL_MAP = {t.name: t for t in TOOLS}

SYSTEM = (
    "你是乐选优品的在线客服「小乐」。"
    "回答问题优先使用工具提供的事实，不要编造订单号、价格、库存。"
    "回答简洁：默认不超过 80 字，先给结论。"
)


def _get_model():
    """返回一个「已绑定工具」的模型对象。

    bind_tools 的作用：每次请求都把工具清单附在 schema 里发给模型，
    模型才知道「我有哪些工具可以点」。
    """
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        temperature=0.3,
        max_tokens=500,
        timeout=30,
    )
    return llm.bind_tools(TOOLS)


async def run_agent(question: str, max_rounds: int = 5) -> dict:
    """跑一轮 Agent，返回最终回答 + 工具调用轨迹（trace 方便调试和讲解）。"""
    model = _get_model()
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=question)]
    trace: list[dict] = []

    for round_no in range(1, max_rounds + 1):
        ai_msg = await model.ainvoke(messages)
        messages.append(ai_msg)  # 模型这一轮说的话也要进历史

        # 没有工具调用 = 模型认为可以直接回答了，循环结束
        if not ai_msg.tool_calls:
            return {
                "answer": ai_msg.content,
                "rounds": round_no,
                "trace": trace,
            }

        # 有工具调用：逐个执行（可能并行多个），再把结果塞回去
        for call in ai_msg.tool_calls:
            name, args, call_id = call["name"], call["args"], call["id"]
            try:
                tool = TOOL_MAP[name]
                result = tool.invoke(args)
            except KeyError:
                # 模型幻觉出一个不存在的工具名，必须兜住
                result = json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
            except Exception as exc:  # 工具内部异常也不能让整个对话崩掉
                result = json.dumps({"error": str(exc)}, ensure_ascii=False)

            trace.append({"tool": name, "args": args, "result_preview": result[:160]})
            messages.append(ToolMessage(content=result, tool_call_id=call_id))

    # 超过最大轮数：兜底，避免模型反复调用把 token 烧光
    return {
        "answer": "抱歉，这个问题我处理得有点久，帮我转人工吧。",
        "rounds": max_rounds,
        "trace": trace,
    }
