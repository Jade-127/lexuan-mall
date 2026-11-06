"""LLM 客户端封装。

要点（面试会问）：
1. 客户端是「有连接池」的对象，全局复用一个，不要每次请求都 new 一个。
2. 百炼提供 OpenAI 兼容协议，所以我们用官方 openai SDK，只改 base_url。
3. 这里用 AsyncOpenAI，因为 FastAPI 是异步的；用同步客户端会把事件循环堵住。
"""
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


@lru_cache
def get_client() -> AsyncOpenAI:
    """进程内单例。lru_cache 在这里的作用是「只创建一次」。"""
    return AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        timeout=30.0,
        max_retries=1,
    )


async def chat_once(prompt: str, system: str | None = None) -> dict:
    """单轮对话（D2 用，后面会被 LangGraph 取代）。

    返回：{"content": 模型回答, "prompt_tokens": ..., "completion_tokens": ...}
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = await get_client().chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.7,
    )

    choice = resp.choices[0]
    usage = resp.usage
    return {
        "content": choice.message.content,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
    }
