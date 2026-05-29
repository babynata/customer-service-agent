"""
健康检查接口
"""

from datetime import datetime, timezone
from fastapi import APIRouter

from api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """服务健康检查"""
    return HealthResponse(
        status="ok",
        version="v3.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
