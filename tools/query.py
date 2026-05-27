"""
工具查询层

封装对外部系统的查询。当前使用 Mock 数据，生产环境替换为真实 API。
"""

import asyncio
from schemas import QueryOrderInput
from tools.mock_data import MOCK_ORDERS, MOCK_TRACKING, MOCK_FAQ


async def query_order(order_id: str | None) -> dict:
    """
    查询订单详情（带参数契约校验）。

    生产替换：await order_service.query(order_id)
    """
    if not order_id:
        return {"error": "NO_ORDER_ID", "data": None}

    # 参数契约校验
    try:
        QueryOrderInput(order_id=order_id)
    except Exception as e:
        return {"error": f"PARAM_INVALID: {e}", "data": None}

    data = MOCK_ORDERS.get(order_id)
    if data:
        # 如果已发货，查物流
        if data.get("tracking_no"):
            data["tracking"] = MOCK_TRACKING.get(data["tracking_no"], [])
        return {"data": data}

    return {"error": "ORDER_NOT_FOUND", "data": None}


async def query_faq(query: str) -> dict:
    """
    FAQ 检索（关键词匹配）。

    生产替换：向量数据库 RAG 检索
    """
    for keyword, answer in MOCK_FAQ.items():
        if keyword in query:
            return {"matched": True, "answer": answer}
    return {"matched": False, "answer": None}
