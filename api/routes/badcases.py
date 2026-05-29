"""
Badcase 管理接口

提供 badcase 查询、统计、运营标记功能。
"""

from fastapi import APIRouter, Query
from typing import Optional

from observability.badcase import collector
from api.schemas import ChatResponse


router = APIRouter(tags=["badcases"])


@router.get("/badcases")
async def list_badcases(
    date: Optional[str] = Query(None, description="日期过滤 YYYY-MM-DD"),
    trigger: Optional[str] = Query(None, description="触发类型过滤"),
    status: Optional[str] = Query(None, description="状态过滤: open/reviewed/fixed/ignored"),
    limit: int = Query(50, ge=1, le=200),
):
    """查询 badcase 列表"""
    badcases = collector.list_badcases(
        date=date,
        trigger=trigger,
        status=status,
        limit=limit,
    )
    return {
        "count": len(badcases),
        "items": [
            {
                "id": b.id,
                "timestamp": b.timestamp,
                "session_id": b.session_id,
                "user_query": b.user_query[:100] + "..." if len(b.user_query) > 100 else b.user_query,
                "response": b.response[:100] + "..." if len(b.response) > 100 else b.response,
                "intent": b.intent,
                "confidence": b.confidence,
                "sentiment": b.sentiment,
                "blocked": b.blocked,
                "block_reason": b.block_reason,
                "trigger": b.trigger,
                "status": b.status,
                "notes": b.notes,
            }
            for b in badcases
        ],
    }


@router.get("/badcases/stats")
async def badcase_stats():
    """Badcase 统计"""
    return collector.get_stats()


@router.post("/badcases/{badcase_id}/status")
async def update_badcases_status(
    badcase_id: str,
    status: str,
    notes: str = "",
):
    """更新 badcase 状态（运营标记）"""
    success = collector.update_status(badcase_id, status, notes)
    return {"success": success, "id": badcase_id, "status": status}
