"""HTTP 客户端单例。

为什么要单例：httpx.AsyncClient 内部维护连接池，每次请求都新建一个
等于每次都重新握手，既慢又浪费文件句柄。
"""
from functools import lru_cache

import httpx


@lru_cache
def get_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=3.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
