"""
工具查询层

封装对外部系统的查询。当前：
- 订单/物流：Mock 数据（生产替换为真实 API）
- FAQ：向量检索（P1 方案：方舟 Embedding API + numpy 余弦相似度 + 同义词/分类混合打分）
"""

import asyncio
from typing import Optional

from schemas import QueryOrderInput, SearchKnowledgeInput
from schemas.faq_schema import FAQDocument
from tools.mock_data import MOCK_ORDERS, MOCK_TRACKING, MOCK_FAQ
from tools.embedding import embed_text, embed_texts, search_faq


# ==================== 订单查询（Mock，生产替换点）====================

async def query_order(order_id: str | None) -> dict:
    """
    查询订单详情（带参数契约校验）。

    生产替换：await order_service.query(order_id)
    """
    if not order_id:
        return {"error": "NO_ORDER_ID", "data": None}

    try:
        QueryOrderInput(order_id=order_id)
    except Exception as e:
        return {"error": f"PARAM_INVALID: {e}", "data": None}

    data = MOCK_ORDERS.get(order_id)
    if data:
        if data.get("tracking_no"):
            data["tracking"] = MOCK_TRACKING.get(data["tracking_no"], [])
        return {"data": data}

    return {"error": "ORDER_NOT_FOUND", "data": None}


# ==================== FAQ 向量检索（P1 混合打分方案）====================

# FAQ 向量库：启动时预计算所有 FAQ 条目的 embedding
# P1：缓存携带完整 FAQDocument 对象，支持同义词和分类上下文加分
_FAQ_VECTOR_CACHE: Optional[list[tuple[FAQDocument, list[float]]]] = None

# 意图 → 分类映射，用于 context_bonus
_INTENT_CATEGORY_MAP: dict[str, str] = {
    "refund": "售后",
    "shipping": "物流",
    "order_status": "物流",
}


async def _build_faq_vector_cache() -> list[tuple[FAQDocument, list[float]]]:
    """预计算所有 FAQ 条目的 embedding 向量"""
    global _FAQ_VECTOR_CACHE
    if _FAQ_VECTOR_CACHE is not None:
        return _FAQ_VECTOR_CACHE

    faq_docs = list(MOCK_FAQ.values())
    if not faq_docs:
        _FAQ_VECTOR_CACHE = []
        return _FAQ_VECTOR_CACHE

    # 对 FAQ 标准问题做 embedding
    questions = [doc.question for doc in faq_docs]
    vectors = await embed_texts(questions)
    _FAQ_VECTOR_CACHE = list(zip(faq_docs, vectors))
    return _FAQ_VECTOR_CACHE


def _build_faq_vector_cache_sync() -> list[tuple[FAQDocument, list[float]]]:
    """同步方式预计算 FAQ 向量（用于启动时兜底）"""
    global _FAQ_VECTOR_CACHE
    if _FAQ_VECTOR_CACHE is not None:
        return _FAQ_VECTOR_CACHE

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已有事件循环，创建新任务
            future = asyncio.ensure_future(_build_faq_vector_cache())
            # 这里不能阻塞，返回空列表让异步路径处理
            return []
        return loop.run_until_complete(_build_faq_vector_cache())
    except RuntimeError:
        # 无事件循环，创建临时 loop
        return asyncio.run(_build_faq_vector_cache())


def _compute_keyword_bonus(query: str, doc: FAQDocument) -> tuple[float, str | None]:
    """
    计算关键词 bonus：检查 query 是否命中标准问题或同义词。

    Returns:
        (bonus, matched_keyword) — bonus 为 0.15/0.08/0.0，matched_keyword 为命中的词或 None
    """
    # 命中标准问题（加分更高）
    if doc.question in query:
        return 0.15, doc.question

    # 命中同义词
    for syn in doc.synonyms:
        if syn in query:
            return 0.08, syn

    return 0.0, None


def _compute_context_bonus(last_intent: str | None, doc: FAQDocument) -> float:
    """计算分类上下文 bonus：上一轮意图分类与当前 FAQ 分类一致时加分"""
    if not last_intent:
        return 0.0
    expected_category = _INTENT_CATEGORY_MAP.get(last_intent)
    if expected_category and expected_category == doc.category:
        return 0.05
    return 0.0


async def query_faq(query: str, last_intent: str | None = None) -> dict:
    """
    FAQ 语义检索（向量相似度 + 混合打分）。

    P1 方案：
    1. 用户 query → 方舟 Embedding API → 向量
    2. 与预计算的 FAQ 向量做余弦相似度计算
    3. 混合打分：cosine_sim + keyword_bonus + context_bonus
    4. 超过条目级阈值则返回，否则未命中

    Args:
        query: 用户查询文本
        last_intent: 上一轮意图（用于分类上下文加分），如 "refund"、"shipping"

    生产演进：
    - P1：接入 Milvus，支持万级 FAQ + 混合检索
    - P2：接入 BGE Reranker，精排 Top-K
    """
    if not query or not query.strip():
        return {"matched": False, "answer": None, "sources": []}

    # 参数契约校验
    try:
        validated = SearchKnowledgeInput(query=query.strip())
        query = validated.query
    except Exception as e:
        return {"matched": False, "answer": None, "sources": [], "error": f"PARAM_INVALID: {e}"}

    # 1. query 向量化
    try:
        query_vec = await embed_text(query.strip())
    except Exception:
        # Embedding API 失败时降级为关键词匹配
        return _query_faq_fallback(query, last_intent)

    if not query_vec:
        return _query_faq_fallback(query, last_intent)

    # 2. 获取 FAQ 向量库
    faq_vectors = _FAQ_VECTOR_CACHE
    if faq_vectors is None:
        faq_vectors = await _build_faq_vector_cache()

    if not faq_vectors:
        return {"matched": False, "answer": None, "sources": []}

    # 3. 向量检索
    results = search_faq(query_vec, faq_vectors, top_k=3)
    if not results:
        return {"matched": False, "answer": None, "sources": []}

    best = results[0]
    best_doc: FAQDocument = best["doc"]

    # 4. 混合打分
    final_score = best["score"]

    # 关键词 bonus（命中标准问题 or 同义词）
    kw_bonus, matched_keyword = _compute_keyword_bonus(query, best_doc)
    final_score = min(1.0, final_score + kw_bonus)

    # 分类上下文 bonus
    ctx_bonus = _compute_context_bonus(last_intent, best_doc)
    final_score = min(1.0, final_score + ctx_bonus)

    # 5. 条目级阈值判断
    threshold = best_doc.confidence_threshold
    if final_score < threshold:
        return {
            "matched": False,
            "answer": None,
            "sources": [{"doc_id": r["doc"].id, "score": r["score"]} for r in results],
            "best_score": final_score,
        }

    # 使用命中的同义词或标准问题作为 matched_keyword
    display_keyword = matched_keyword or best_doc.question

    return {
        "matched": True,
        "answer": {
            "answer": best_doc.answer,
            "confidence": round(final_score, 3),
            "matched_keyword": display_keyword,
            "category": best_doc.category,
        },
        "sources": [{"doc_id": r["doc"].id, "score": r["score"]} for r in results],
    }


def _query_faq_fallback(query: str, last_intent: str | None = None) -> dict:
    """Embedding API 失败时的降级方案：关键词匹配（含同义词扩展）"""
    best_doc: FAQDocument | None = None
    best_keyword: str | None = None

    for doc in MOCK_FAQ.values():
        # 检查标准问题
        if doc.question in query:
            best_doc = doc
            best_keyword = doc.question
            break
        # 检查同义词
        for syn in doc.synonyms:
            if syn in query:
                best_doc = doc
                best_keyword = syn
                break
        if best_doc:
            break

    if not best_doc:
        return {"matched": False, "answer": None, "sources": []}

    # 降级模式下固定置信度 0.85
    confidence = 0.85
    # 分类上下文加分（降级模式也支持）
    ctx_bonus = _compute_context_bonus(last_intent, best_doc)
    confidence = min(1.0, confidence + ctx_bonus)

    return {
        "matched": True,
        "answer": {
            "answer": best_doc.answer,
            "confidence": round(confidence, 3),
            "matched_keyword": best_keyword,
            "category": best_doc.category,
            "fallback": True,
        },
        "sources": [{"doc_id": best_doc.id, "score": 1.0}],
    }


# 启动时预加载（同步兜底，不影响主流程）
_FAQ_VECTOR_CACHE = None
