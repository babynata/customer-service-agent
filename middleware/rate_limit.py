"""
限流中间件

基于 Redis 滑动窗口的 IP 限流 + 会话限流。
"""

import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from state.redis_saver import redis


# 限流配置
IP_QPS_LIMIT = 10       # 单 IP 每秒最多 10 次
SESSION_HOUR_LIMIT = 30  # 单会话每小时最多 30 轮


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis 滑动窗口限流"""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # 只限流 /chat 接口
        if path != "/chat":
            return await call_next(request)

        # IP 限流
        now = int(time.time())
        window_key = f"rate_limit:ip:{client_ip}:{now // 1}"

        try:
            pipe = redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 1)
            results = await pipe.execute()
            count = results[0]
        except Exception:
            # Redis 失败时放行，避免误杀
            return await call_next(request)

        if count > IP_QPS_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {IP_QPS_LIMIT} requests per second",
            )

        return await call_next(request)


class SessionRateLimit:
    """会话级限流（用于 Gradio /chat 接口）"""

    @staticmethod
    async def check(session_id: str) -> bool:
        """检查会话是否超过每小时限制"""
        now = int(time.time())
        window_key = f"rate_limit:session:{session_id}:{now // 3600}"

        try:
            pipe = redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 3600)
            results = await pipe.execute()
            count = results[0]
            return count <= SESSION_HOUR_LIMIT
        except Exception:
            return True
