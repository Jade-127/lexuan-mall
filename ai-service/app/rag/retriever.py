"""知识库检索（D8）。

流程：问题 → embedding → pgvector 余弦相似度 → 阈值过滤 → 取 top_k

两个工程决策：
1. 先取 8 条再按阈值过滤：pgvector 只会"按距离排序取 N"，不懂阈值；
   多取几条、自己卡分数，才能实现"查不到就说不知道"。
2. 数据库用同步 psycopg + asyncio.to_thread：
   psycopg 的异步连接在 Windows 的 ProactorEventLoop 上不可用，
   丢到线程池执行既绕开限制，也不阻塞事件循环。
"""
import asyncio

import psycopg
from langchain_openai import OpenAIEmbeddings

from app.config import settings

DEFAULT_THRESHOLD = 0.55
DEFAULT_TOP_K = 3
CANDIDATE_SIZE = 8

_SQL = """
    SELECT doc_id, title, content, 1 - (embedding <=> %s::vector) AS score
    FROM ai_knowledge
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""


def _to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(round(x, 6)) for x in vec) + "]"


def _get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        check_embedding_ctx_length=False,
        chunk_size=10,
    )


def _query_sync(vec: str, limit: int) -> list[tuple]:
    """同步查询（会在独立线程里执行）。"""
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL, (vec, vec, limit))
            return cur.fetchall()


async def search_knowledge(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict]:
    """返回 [{"doc_id","title","content","score"}, ...]，按相关度降序。

    全部低于阈值时返回空列表，调用方据此回答"没有查到相关规定"。
    """
    vec = _to_vector_literal(await _get_embeddings().aembed_query(question))
    rows = await asyncio.to_thread(_query_sync, vec, max(top_k * 3, CANDIDATE_SIZE))

    results = [
        {"doc_id": r[0], "title": r[1], "content": r[2], "score": float(r[3])}
        for r in rows
        if float(r[3]) >= threshold
    ]
    return results[:top_k]
