"""乐选优品 · 智能客服 Agent 服务入口。

D1：/health
D2：/ai/ping —— 第一次真正调用大模型
"""
import time

from fastapi import FastAPI, Query

from app.config import settings
from app.llm import chat_once
SYSTEM = (
    "你是乐选优品的在线客服「小乐」。"
    "回答必须简洁：默认不超过 80 字，先给结论，不寒暄、不自报家门、不罗列无关能力。"
    "只有用户明确要求详细说明时才展开。"
)

app = FastAPI(
    title="乐选优品 · 智能客服 Agent",
    version="0.2.0",
    description="售前推荐 / 订单查询 / 售后政策问答",
)


@app.get("/health")
async def health():
    """探活接口，网关和部署脚本会用到。"""
    return {"status": "ok", "app": settings.app_name, "model": settings.chat_model}


@app.get("/ai/ping")
async def ping(
    q: str = Query("你好，用一句话介绍你自己", description="要发给模型的话"),
):
    """最小可用的模型调用：输入一句话，返回模型回答 + 耗时 + token 数。

    这个接口只用来自测，正式对话后面走 SSE 流式接口。
    """
    started = time.perf_counter()
    try:
        result = await chat_once(q, system=SYSTEM)
    except Exception as exc:  # 网络 / Key / 模型名错误都从这里暴露，方便调试
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "hint": "401 检查 Key，404 检查模型名，超时检查网络/代理",
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "model": settings.chat_model,
        "question": q,
        "answer": result["content"],
        "latency_ms": latency_ms,
        "tokens": {
            "prompt": result["prompt_tokens"],
            "completion": result["completion_tokens"],
        },
    }
