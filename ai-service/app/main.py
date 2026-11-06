"""乐选优品 · 智能客服 Agent 服务入口。

D1：/health
D2：/ai/ping —— 第一次真正调用大模型，并验证「控长」的三个开关
D3：/ai/chat/stream —— SSE 流式输出，接通网关后即可被前端消费
"""
import json
import time

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.llm import chat_once, chat_stream_text

app = FastAPI(
    title="乐选优品 · 智能客服 Agent",
    version="0.3.0",
    description="售前推荐 / 订单查询 / 售后政策问答",
)

# 客服人格：先定「怎么说话」，再谈「说什么」。
# 这几句话直接决定了回答长度和语气，改 prompt 比改代码有用得多。
SYSTEM = (
    "你是乐选优品的在线客服「小乐」。"
    "回答必须简洁：默认不超过 80 字，先给结论，不寒暄、不自报家门、不罗列无关能力。"
    "只有用户明确要求详细说明时才展开。"
)


def sse(event: str, data: dict) -> str:
    """拼一条 SSE 消息。

    协议规定：event 行给事件名，data 行给内容，最后必须空一行表示「这条结束」。
    ensure_ascii=False 是为了让中文直接输出，不然会变成 \\u4f60\\u597d 这种。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health():
    """探活接口，网关和部署脚本会用到。"""
    return {"status": "ok", "app": settings.app_name, "model": settings.chat_model}


@app.get("/ai/ping")
async def ping(
    q: str = Query("你好，用一句话介绍你自己", description="要发给模型的话"),
    max_tokens: int = Query(200, ge=16, le=2000, description="输出上限，越小越省钱"),
):
    """最小可用的模型调用：输入一句话，返回回答 + 耗时 + token 数。

    这个接口只用来自测，正式对话走下面的流式接口。
    """
    started = time.perf_counter()
    try:
        result = await chat_once(q, system=SYSTEM, max_tokens=max_tokens)
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
        "finish_reason": result["finish_reason"],
    }


@app.get("/ai/chat/stream")
async def chat_stream(
    q: str = Query(..., description="用户这句话"),
    max_tokens: int = Query(500, ge=16, le=2000),
):
    """SSE 流式对话：边生成边推送。

    为什么用流式：等整段生成完再返回，用户要干等 3~5 秒；
    流式可以让第一个字在 1 秒内出现，体感完全不同，也方便前端做「正在输入」。

    事件约定（前端按事件名分派）：
      start  -> {"model": "qwen-plus"}
      delta  -> {"content": "你"}
      done   -> {"chars": 42, "latency_ms": 1234}
      error  -> {"type": "XXXError", "message": "..."}
    """

    async def event_generator():
        started = time.perf_counter()
        chars = 0
        yield sse("start", {"model": settings.chat_model})
        try:
            async for piece in chat_stream_text(q, system=SYSTEM, max_tokens=max_tokens):
                chars += len(piece)
                yield sse("delta", {"content": piece})
        except Exception as exc:  # 流到一半失败也要让前端知道，不能静默断开
            yield sse("error", {"type": type(exc).__name__, "message": str(exc)[:300]})
            return
        yield sse("done", {
            "chars": chars,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 告诉 nginx 不要缓冲，否则流式会被攒成一坨
        },
    )
