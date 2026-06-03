"""
文本嵌入服务

P0 方案：调用火山方舟 Embedding API，FAQ 数据量小，直接用 numpy 余弦相似度计算。
不引入 Milvus，降低部署复杂度。
"""

import os
import asyncio
import numpy as np
from typing import Any, Optional

# 使用 langchain_openai 的 OpenAIEmbeddings 兼容调用方舟接口
# 方舟 Embedding API 与 OpenAI /v1/embeddings 兼容
from langchain_openai import OpenAIEmbeddings


ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# 火山方舟嵌入模型 endpoint（如 bge-large-zh）
EMBEDDING_MODEL = os.environ.get("ARK_EMBEDDING_MODEL", "bge-large-zh")

# 全局嵌入模型实例（延迟初始化）
_embeddings: Optional[OpenAIEmbeddings] = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=ARK_API_KEY,
            base_url=ARK_BASE_URL,
            # 方舟嵌入模型通常不需要高并发限制
            chunk_size=16,
        )
    return _embeddings


def _is_test_key() -> bool:
    """检测当前 API Key 是否为测试用假 key，避免测试环境等待 API 超时"""
    key = ARK_API_KEY.strip()
    return not key or key.startswith("sk-test") or key.startswith("sk-fake") or key == "YOUR_API_KEY"


async def embed_text(text: str) -> list[float]:
    """单条文本嵌入，返回归一化后的向量"""
    if not text or not text.strip():
        return []
    if _is_test_key():
        raise RuntimeError("Embedding API skipped: test key detected")
    emb = _get_embeddings()
    # OpenAIEmbeddings.aembed_query 是异步的
    vec = await emb.aembed_query(text.strip())
    return vec


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本嵌入"""
    if not texts:
        return []
    if _is_test_key():
        raise RuntimeError("Embedding API skipped: test key detected")
    emb = _get_embeddings()
    vectors = await emb.aembed_documents([t.strip() for t in texts if t.strip()])
    return vectors


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def search_faq(query_vec: list[float], faq_vectors: list[tuple[Any, list[float]]], top_k: int = 3) -> list[dict]:
    """
    在 FAQ 向量库中搜索最相似的条目

    Args:
        query_vec: 查询向量
        faq_vectors: [(doc, vector), ...]，doc 为任意对象（如 FAQDocument 实例）
        top_k: 返回前 K 条

    Returns:
        [{"doc": Any, "score": float}, ...]
    """
    scored = []
    for doc, vec in faq_vectors:
        score = cosine_similarity(query_vec, vec)
        scored.append({"doc": doc, "score": round(score, 4)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
