"""乐选优品 · 智能客服 Agent 服务入口。

对外接口（全部经网关 /ai/** 暴露，JWT 由网关校验后透传 user-info）：
    GET  /health                        探活
    POST /ai/chat                       对话（多轮记忆、工具调用、写操作弹确认）
    POST /ai/chat/confirm               用户确认/取消后继续执行写操作
    GET  /ai/tickets                    我的工单
    GET  /ai/conversations/{id}/messages   会话历史
    GET  /ai/traces/{trace_id}          按 trace_id 回放一次请求的链路
"""
import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.graph import resume_graph, run_graph
from app.chat import store
from app.clients.context import set_conversation_id, set_user_info
from app.common import rate_limit, trace
from app.config import settings

app = FastAPI(
    title="乐选优品 · 智能客服 Agent",
    version="1.0.0",
    description="售前推荐 / 订单查询 / 售后政策问答",
)

# 聊天页（静态文件）。页面本身不需要鉴权，调接口时带 token 走网关。
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    """探活接口，网关和部署脚本会用到。"""
    return {"status": "ok", "app": settings.app_name, "model": settings.chat_model}


# ==================== 会话与对话 ====================

store.init_schema()      # 建 ai_conversation / ai_message / ai_ticket（幂等）

# ==================== 对话接口 ====================

store.init_schema()      # 建 ai_conversation / ai_message（幂等）


class ChatIn(BaseModel):
    conversation_id: str | None = None      # 不传 = 新建会话
    message: str


def ensure_owner(conv: dict, user_id: int) -> None:
    """
    校验会话归属：不是本人的会话，一律拒绝。
    """
    if conv["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问该会话")


@app.post("/ai/chat")
async def chat(request: Request, body: ChatIn):
    """带多轮记忆的对话。

    - 不传 conversation_id：新建会话，返回 id
    - 传了：校验归属 → 恢复该会话的历史 → 继续对话
    """
    user_info = request.headers.get("user-info")
    if not user_info:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = int(user_info)

    # 先限流，再干活。超了直接 429，别浪费模型调用。
    ok, wait_seconds = rate_limit.allow(user_id)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=f"小乐有点忙不过来啦，请 {wait_seconds} 秒后再试～",
        )

    conv_id = body.conversation_id
    if conv_id:
        conv = await asyncio.to_thread(store.get_conversation, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        ensure_owner(conv, user_id)
    else:
        conv_id = await asyncio.to_thread(store.create_conversation, user_id)

    set_user_info(user_info)
    set_conversation_id(conv_id)          # 建工单时工具要读它
    trace_id = trace.new_trace()          # 这条请求一个 trace_id，贯穿到最后
    trace.event("api.chat.start", user_id=user_id, conv=conv_id[:8], message=body.message[:40])
    started = time.perf_counter()
    # thread_id 拼上用户，保证 A 的会话不可能被 B 的线程读到
    result = await run_graph(body.message, thread_id=f"{user_id}:{conv_id}")
    latency_ms = int((time.perf_counter() - started) * 1000)
    trace.event("api.chat.end", status="need_confirm" if result["interrupt"] else "done", ms=latency_ms)

    await asyncio.to_thread(store.append_message, conv_id, "user", body.message)

    # 图停在 interrupt：不落 assistant 消息，只告诉前端"要弹确认框"
    if result["interrupt"]:
        info = result["interrupt"]
        await asyncio.to_thread(
            store.append_message, conv_id, "assistant", f"【待确认】{info.get('summary', '')}", latency_ms
        )
        return {
            "ok": True,
            "status": "need_confirm",
            "conversation_id": conv_id,
            "confirm": info,
            "trace": result.get("trace", []),
            "trace_id": trace_id,
            "latency_ms": latency_ms,
        }

    await asyncio.to_thread(store.append_message, conv_id, "assistant", result["answer"], latency_ms)

    return {
        "ok": True,
        "status": "done",
        "conversation_id": conv_id,
        "answer": result["answer"],
        "trace": result.get("trace", []),
        "trace_id": trace_id,
        "latency_ms": latency_ms,
        "message_count": result["message_count"],
    }


class ConfirmIn(BaseModel):
    conversation_id: str
    approved: bool          # true = 确认创建，false = 取消


@app.post("/ai/chat/confirm")
async def chat_confirm(request: Request, body: ConfirmIn):
    """用户点了确认/取消之后调这里，让暂停中的图继续跑完。"""
    user_info = request.headers.get("user-info")
    if not user_info:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = int(user_info)

    conv = await asyncio.to_thread(store.get_conversation, body.conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    ensure_owner(conv, user_id)

    set_user_info(user_info)
    set_conversation_id(body.conversation_id)
    started = time.perf_counter()
    result = await resume_graph(body.approved, thread_id=f"{user_id}:{body.conversation_id}")
    latency_ms = int((time.perf_counter() - started) * 1000)

    await asyncio.to_thread(store.append_message, body.conversation_id, "user",
                            "确认" if body.approved else "取消")
    await asyncio.to_thread(store.append_message, body.conversation_id, "assistant",
                            result["answer"], latency_ms)

    return {
        "ok": True,
        "status": "done",
        "conversation_id": body.conversation_id,
        "answer": result["answer"],
        "latency_ms": latency_ms,
    }


@app.get("/ai/tickets")
async def my_tickets(request: Request, limit: int = Query(10, ge=1, le=50)):
    """我的工单列表（做题/演示用，确认工单真的落库了）。"""
    user_info = request.headers.get("user-info")
    if not user_info:
        raise HTTPException(status_code=401, detail="未登录")
    tickets = await asyncio.to_thread(store.list_tickets, int(user_info), limit)
    return {"user_id": int(user_info), "count": len(tickets), "tickets": tickets}


@app.get("/ai/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str, request: Request):
    """查看会话消息（前端渲染历史用），同样要校验归属。"""
    user_info = request.headers.get("user-info")
    if not user_info:
        raise HTTPException(status_code=401, detail="未登录")

    conv = await asyncio.to_thread(store.get_conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    ensure_owner(conv, int(user_info))

    messages = await asyncio.to_thread(store.list_messages, conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


# ==================== 链路回放 ====================

TRACE_FILE = Path("logs") / "traces.jsonl"


@app.get("/ai/traces/{trace_id}")
async def get_trace(trace_id: str):
    """按 trace_id 回放一次请求的完整链路（前端调试 / 排查线上问题用）。

    只读本地日志，不需要登录，方便直接 curl：
        curl http://127.0.0.1:8087/ai/traces/<trace_id>
    """
    if not TRACE_FILE.exists():
        return {"trace_id": trace_id, "count": 0, "events": []}

    events = []
    for line in TRACE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("trace_id") == trace_id:
            events.append(record)

    total_ms = sum(e.get("ms", 0) for e in events if e.get("stage", "").startswith("graph."))
    return {"trace_id": trace_id, "count": len(events), "graph_ms": total_ms, "events": events}