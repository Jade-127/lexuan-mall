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


def _build_messages(prompt: str, system: str | None) -> list[dict]:
    """组装 messages：system 在前，user 在后。"""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


async def chat_once(
    prompt: str,
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.3,
) -> dict:
    """单轮对话：一次性拿完整回答（D2 用）。

    三个控长的开关：
    - system：软约束，告诉模型「简洁、别寒暄」
    - max_tokens：硬截断，超过就停，直接省 completion token
    - temperature：0.3 更稳定，客服场景不需要发散
    """
    kwargs: dict = {
        "model": settings.chat_model,
        "messages": _build_messages(prompt, system),
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    resp = await get_client().chat.completions.create(**kwargs)

    choice = resp.choices[0]
    usage = resp.usage
    return {
        "content": choice.message.content,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "finish_reason": choice.finish_reason,
    }


async def chat_stream_text(
    prompt: str,
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.3,
):
    """流式对话：模型吐一小段，我们就 yield 一小段（D3 用）。

    和 chat_once 只差一个参数：stream=True。
    这时返回的不是「一个完整响应」，而是「一个异步迭代器」，
    我们要一块一块地读，读到一块就转发一块给前端。
    """
    kwargs: dict = {
        "model": settings.chat_model,
        "messages": _build_messages(prompt, system),
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    stream = await get_client().chat.completions.create(**kwargs)

    async for chunk in stream:
        # 有些 chunk 只带 usage、choices 为空（收尾包），必须判空
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield content#TODO
