"""
熔断器中间件

基于 Redis 计数器的简单熔断实现。
"""

import time
from enum import Enum
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from state.redis_saver import redis


class CircuitState(Enum):
    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断
    HALF_OPEN = "half_open" # 半开（试探）


# 熔断配置
FAILURE_THRESHOLD = 10      # 连续失败次数
FAILURE_RATE_THRESHOLD = 0.2  # 失败率阈值
TIME_WINDOW = 60            # 统计窗口（秒）
COOLDOWN = 30               # 熔断后冷却时间（秒）


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """
    简单熔断中间件

    监控 /chat 接口的 LLM 调用错误率，
    超过阈值时快速失败，保护下游服务。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path != "/chat":
            return await call_next(request)

        state = await self._get_state()

        if state == CircuitState.OPEN:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable (circuit breaker open)",
            )

        response = await call_next(request)

        # 根据响应状态记录成功/失败
        if response.status_code >= 500:
            await self._record_failure()
        else:
            await self._record_success()

        return response

    async def _get_state(self) -> CircuitState:
        """获取当前熔断状态"""
        try:
            state = await redis.get("circuit_breaker:state")
            if state == b"open":
                # 检查冷却时间是否已过
                opened_at = await redis.get("circuit_breaker:opened_at")
                if opened_at:
                    elapsed = time.time() - float(opened_at)
                    if elapsed > COOLDOWN:
                        await redis.set("circuit_breaker:state", "half_open")
                        return CircuitState.HALF_OPEN
                return CircuitState.OPEN
            if state == b"half_open":
                return CircuitState.HALF_OPEN
            return CircuitState.CLOSED
        except Exception:
            return CircuitState.CLOSED

    async def _record_failure(self):
        """记录一次失败"""
        now = int(time.time())
        key = f"circuit_breaker:fails:{now // TIME_WINDOW}"
        try:
            await redis.incr(key)
            await redis.expire(key, TIME_WINDOW * 2)
            await self._check_threshold()
        except Exception:
            pass

    async def _record_success(self):
        """记录一次成功"""
        now = int(time.time())
        key = f"circuit_breaker:success:{now // TIME_WINDOW}"
        try:
            await redis.incr(key)
            await redis.expire(key, TIME_WINDOW * 2)
        except Exception:
            pass

    async def _check_threshold(self):
        """检查是否触发熔断"""
        now = int(time.time())
        window = now // TIME_WINDOW

        try:
            fails = int(await redis.get(f"circuit_breaker:fails:{window}") or 0)
            success = int(await redis.get(f"circuit_breaker:success:{window}") or 0)
            total = fails + success

            if total >= FAILURE_THRESHOLD and fails / total > FAILURE_RATE_THRESHOLD:
                await redis.set("circuit_breaker:state", "open")
                await redis.set("circuit_breaker:opened_at", str(time.time()))
        except Exception:
            pass
