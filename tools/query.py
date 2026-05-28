"""
工具查询层

封装对外部系统的查询。当前：
- 订单/物流：Mock 数据（生产替换为真实 API）
- FAQ：向量检索（P0 方案：方舟 Embedding API + numpy 余弦相似度）
"""

import asyncio
from typing import Optional

from schemas import QueryOrderInput
from tools.mock_data import MOCK_ORDERS, MOCK_TRACKING, MOCK_FAQ
from tools.embedding import embed_text, search_faq


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


# ==================== FAQ 向量检索（P0 生产方案）====================

# FAQ 向量库：启动时预计算所有 FAQ 条目的 embedding
# 由于 FAQ 数据量小（~20 条），直接内存存储，不引入 Milvus
_FAQ_VECTOR_CACHE: Optional[list[tuple[str, list[float]]]] = None
_FAQ_EMBEDDING_THRESHOLD = 0.72  # 余弦相似度阈值


async def _build_faq_vector_cache() -> list[tuple[str, list[float]]]:
    """预计算所有 FAQ 条目的 embedding 向量"""
    global _FAQ_VECTOR_CACHE
    if _FAQ_VECTOR_CACHE is not None:
        return _FAQ_VECTOR_CACHE

    faq_keys = list(MOCK_FAQ.keys())
    if not faq_keys:
        _FAQ_VECTOR_CACHE = []
        return _FAQ_VECTOR_CACHE

    # 对 FAQ 关键词做 embedding
    vectors = await embed_texts(faq_keys)
    _FAQ_VECTOR_CACHE = list(zip(faq_keys, vectors))
    return _FAQ_VECTOR_CACHE


def _build_faq_vector_cache_sync() -> list[tuple[str, list[float]]]:
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


async def query_faq(query: str) -> dict:
    """
    FAQ 语义检索（向量相似度）。

    P0 方案：
    1. 用户 query → 方舟 Embedding API → 向量
    2. 与预计算的 FAQ 向量做余弦相似度计算
    3. Top-1 超过阈值则返回，否则未命中

    生产演进：
    - P1：接入 Milvus，支持万级 FAQ + 混合检索
    - P2：接入 BGE Reranker，精排 Top-K
    """
    if not query or not query.strip():
        return {"matched": False, "answer": None, "sources": []}

    # 1. query 向量化
    try:
        query_vec = await embed_text(query.strip())
    except Exception as e:
        # Embedding API 失败时降级为关键词匹配
        return _query_faq_fallback(query)

    if not query_vec:
        return _query_faq_fallback(query)

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

    # 4. 阈值判断 + 混合 bonus（关键词命中加分）
    final_score = best["score"]
    best_key = best["key"]
    if best_key in query:
        final_score = min(1.0, final_score + 0.08)

    if final_score < _FAQ_EMBEDDING_THRESHOLD:
        return {
            "matched": False,
            "answer": None,
            "sources": results,
            "best_score": final_score,
        }

    faq_entry = MOCK_FAQ.get(best_key, {})
    return {
        "matched": True,
        "answer": {
            "answer": faq_entry.get("answer", ""),
            "confidence": round(final_score, 3),
            "matched_keyword": best_key,
        },
        "sources": results,
    }


def _query_faq_fallback(query: str) -> dict:
    """Embedding API 失败时的降级方案：关键词匹配"""
    for keyword, answer in MOCK_FAQ.items():
        if keyword in query:
            return {
                "matched": True,
                "answer": {
                    "answer": answer.get("answer", ""),
                    "confidence": 0.85,
                    "matched_keyword": keyword,
                    "fallback": True,
                },
                "sources": [{"key": keyword, "score": 1.0}],
            }
    return {"matched": False, "answer": None, "sources": []}


# 启动时预加载（同步兜底，不影响主流程）
_FAQ_VECTOR_CACHE = None
