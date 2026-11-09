"""会话与消息的业务存储（D12）。

和 LangGraph 的 checkpointer 是两层：
- checkpointer（PostgresSaver 自建的表）：存图的完整状态快照，给机器续跑用
- 这里的 ai_conversation / ai_message：存给人看的内容，前端展示、审计、评测用

为什么 conversation_id 用 UUID 而不是自增：
自增可以被枚举（1、2、3…），别人猜到就能尝试读别人的会话。
UUID 猜不到，是"不可枚举"的第一道防线；第二道才是归属校验。
"""
import uuid

import psycopg

from app.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS ai_conversation (
    id          UUID PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    title       VARCHAR(200),
    status      SMALLINT NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON ai_conversation(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_message (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL,
    role            VARCHAR(16) NOT NULL,
    content         TEXT,
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON ai_message(conversation_id, id);
"""


def init_schema() -> None:
    """建业务表（幂等，可重复执行）。"""
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()


def create_conversation(user_id: int, title: str = "新会话") -> str:
    """新建会话，返回 UUID 字符串。"""
    conv_id = str(uuid.uuid4())
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ai_conversation (id, user_id, title) VALUES (%s, %s, %s)",
                (conv_id, user_id, title),
            )
        conn.commit()
    return conv_id


def get_conversation(conv_id: str) -> dict | None:
    """按 id 查会话（查不到返回 None；id 格式非法也返回 None）。"""
    try:
        with psycopg.connect(settings.pg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, user_id, title FROM ai_conversation WHERE id = %s AND status = 1",
                    (conv_id,),
                )
                row = cur.fetchone()
    except psycopg.Error:
        return None
    if not row:
        return None
    return {"id": str(row[0]), "user_id": row[1], "title": row[2]}


def append_message(conversation_id: str, role: str, content: str, latency_ms: int | None = None) -> None:
    """追加一条消息（user / assistant）。"""
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ai_message (conversation_id, role, content, latency_ms) VALUES (%s, %s, %s, %s)",
                (conversation_id, role, content, latency_ms),
            )
            cur.execute("UPDATE ai_conversation SET updated_at = now() WHERE id = %s", (conversation_id,))
        conn.commit()


def list_messages(conversation_id: str, limit: int = 20) -> list[dict]:
    """取最近 N 条消息（前端展示 / 调试用）。"""
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, created_at FROM ai_message
                WHERE conversation_id = %s ORDER BY id DESC LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()
    return [{"role": r[0], "content": r[1], "created_at": r[2].isoformat()} for r in reversed(rows)]
