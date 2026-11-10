"""知识库入库脚本。

做三件事：
1. 读 data/knowledge 下的 md 文件
2. 按段落切块（每块约 400 字，重叠 50 字），并给每块加上标题
3. 调百炼 text-embedding-v3 向量化，写入 pgvector

为什么每块要带标题：
一块正文可能只写"由商家承担"，脱离标题就不知道说的是什么。
带上"退货运费规则"这个标题，向量表达更完整，检索命中率明显更高。

用法（在 ai-service 目录下）：
    .\.venv\Scripts\python.exe scripts\ingest_knowledge.py

可重复执行：每次会先清空表再重建，避免重复入库。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg                                    # noqa: E402
from langchain_core.documents import Document     # noqa: E402
from langchain_openai import OpenAIEmbeddings     # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

from app.config import settings                   # noqa: E402

KNOWLEDGE_DIR = Path("data/knowledge")

# 切分参数：
# - chunk_size=400：中文约 400 字一块，够表达一个完整条款
# - chunk_overlap=50：相邻块重叠 50 字，避免一句话被切成两半丢上下文
splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "；", "，", " ", ""],
)


def load_documents() -> list[Document]:
    """读取所有 md 文件，转成 Document 列表。"""
    docs: list[Document] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
        docs.append(Document(page_content=text, metadata={"doc_id": path.stem, "title": title}))
    return docs


def split_documents(docs: list[Document]) -> list[Document]:
    """切块，并把标题拼到每块开头。"""
    chunks: list[Document] = []
    for chunk in splitter.split_documents(docs):
        title = chunk.metadata.get("title", "")
        chunk.page_content = f"【{title}】\n{chunk.page_content}"
        chunks.append(chunk)
    return chunks


def get_embeddings() -> OpenAIEmbeddings:
    """百炼的 embedding 也走 OpenAI 兼容协议。

    check_embedding_ctx_length=False：百炼不走 OpenAI 的 token 分块逻辑，
    传原始字符串最稳。
    """
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.openai_base_url,
        check_embedding_ctx_length=False,
        chunk_size=10,          # 百炼 embedding 单次最多 10 条，必须分批
    )


async def main() -> None:
    docs = load_documents()
    chunks = split_documents(docs)
    print(f"读取 {len(docs)} 篇文档，切分为 {len(chunks)} 个块")

    embeddings = get_embeddings()
    print("开始向量化（首次会慢一点）...")
    vectors = await embeddings.aembed_documents([c.page_content for c in chunks])
    print(f"向量化完成，维度 = {len(vectors[0])}")

    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE ai_knowledge RESTART IDENTITY")
            for chunk, vec in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO ai_knowledge (doc_id, title, content, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (
                        chunk.metadata["doc_id"],
                        chunk.metadata["title"],
                        chunk.page_content,
                        psycopg.types.json.Jsonb(chunk.metadata),
                        str(vec),          # 列表转成 "[0.1,0.2,...]" 字符串，再 cast 成 vector
                    ),
                )
        conn.commit()

    print("入库完成")
    with psycopg.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ai_knowledge")
            print("表内记录数:", cur.fetchone()[0])


if __name__ == "__main__":
    asyncio.run(main())
