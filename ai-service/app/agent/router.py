"""意图路由：先用小模型判断"这是哪类问题"，再决定走哪条链路。

为什么不让主模型自己判断要不要查库：
主模型是"答题选手"不是"分流员"——它对政策类问题的第一反应是直接回答（它觉得自己知道），
提示词只能提高概率，不能保证行为。评测里这一点很明确：纯提示词只把准确率从 50% 提到 63%。

所以分流这件事交给一个专门的小模型：
    快      ~200ms，一次 30 token
    便宜    qwen-turbo 约为 qwen-plus 的 1/10
    可控    只做 4 选 1，答案域极窄，几乎不会跑偏

分类结果决定链路：
    政策 → 先查知识库，再让模型基于检索结果回答
    订单 → 先查本人订单
    商品 → 先查商品库
    闲聊 → 什么都不查，直接回答
"""
import asyncio
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger("router")

CATEGORIES = ("政策", "订单", "商品", "闲聊")

# 关键词兜底：小模型超时/报错时用它，保证链路不中断
FALLBACK_KEYWORDS = {
    "订单": ("订单", "物流", "发货了吗", "到哪了", "快递单"),
    "政策": ("退", "换", "运费", "退款", "发票", "配送", "包邮", "尺码", "售后", "保修", "时效"),
    "商品": ("推荐", "多少钱", "有没有", "有货", "价格", "想买", "送人", "买什么"),
}

SYSTEM = "你是意图分类器。只输出四个类别中的一个词，不要解释，不要标点。"

PROMPT = """把用户这句话归到下面四类之一，只输出类别名：

政策：退换货、运费、退款、发票、发货时效、配送范围、尺码、售后规则、客服时间与转人工
订单：和用户自己的订单有关（查订单、看状态、查物流、取消订单）
商品：想找或了解某个商品（推荐、价格、有没有货、规格、送礼选什么）
闲聊：以上都不是（问候、天气、笑话、问你是谁）

用户说：{q}
类别："""


def _keyword_fallback(question: str) -> str:
    for category in ("订单", "政策", "商品"):
        if any(kw in question for kw in FALLBACK_KEYWORDS[category]):
            return category
    return "闲聊"


async def classify(question: str) -> str:
    """返回 政策 / 订单 / 商品 / 闲聊 之一。

    分类器失败时退回关键词规则——分流出错只会让回答变差，不能让它把请求搞挂。
    """
    for attempt in range(2):
        try:
            return await _classify_once(question)
        except Exception as exc:  # noqa: BLE001
            # 429（每分钟调用上限）最常见：等两秒重试一次，还不行才退回关键词
            logger.warning("分类器第 %d 次失败（%s）", attempt + 1, type(exc).__name__)
            if attempt == 0:
                await asyncio.sleep(2)
    logger.warning("分类器两次都失败，退回关键词规则")
    return _keyword_fallback(question)


async def _classify_once(question: str) -> str:
    try:
        llm = ChatOpenAI(
            model=settings.router_model,
            api_key=settings.dashscope_api_key,
            base_url=settings.openai_base_url,
            temperature=0,          # 分类要确定性
            max_tokens=4,           # 只要一个词
            timeout=8,
        )
        msg = await llm.ainvoke(
            [SystemMessage(content=SYSTEM), HumanMessage(content=PROMPT.format(q=question))]
        )
        text = (msg.content or "").strip()
        for category in CATEGORIES:
            if category in text:
                return category
        logger.warning("分类器返回了无法识别的内容: %r", text[:20])
    except Exception:
        raise
    return _keyword_fallback(question)
