"""
Redis Checkpoint 持久化

替换 LangGraph 默认的 MemorySaver，支持：
- 多实例共享对话状态
- TTL 自动过期（默认 7 天）
- msgpack 序列化（比 JSON 体积小 30%）
"""

import os
import msgpack
from typing import Any, Optional

import redis.asyncio as redis
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CHECKPOINT_TTL = int(os.environ.get("CHECKPOINT_TTL_SECONDS", "604800"))  # 7 天


class RedisSaver(BaseCheckpointSaver):
    """
    生产级 Redis Checkpoint 持久化

    Redis Key 设计：
    - Hash: langgraph:checkpoint:{thread_id}
      - field: {checkpoint_id}  → value: msgpack 序列化的 checkpoint
      - TTL: 7 天
    """

    def __init__(self, redis_url: str = REDIS_URL, ttl_seconds: int = CHECKPOINT_TTL):
        self._redis = redis.from_url(redis_url, decode_responses=False)
        self._ttl = ttl_seconds

    async def aget_tuple(self, config: dict) -> Optional[Checkpoint]:
        """获取最新的 checkpoint"""
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

        key = f"langgraph:checkpoint:{thread_id}"
        checkpoints = await self._redis.hgetall(key)
        if not checkpoints:
            return None

        # 按 checkpoint_id（时间戳格式）排序取最新
        latest_id = max(checkpoints.keys())
        data = checkpoints[latest_id]
        try:
            decoded = msgpack.unpackb(data, raw=False)
            return Checkpoint(**decoded)
        except Exception:
            return None

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: dict,
    ) -> dict:
        """写入 checkpoint"""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        key = f"langgraph:checkpoint:{thread_id}"

        # checkpoint_id = 时间戳_步数
        ts = checkpoint.get("ts", "0")
        step = checkpoint.get("step", 0)
        checkpoint_id = f"{ts}_{step}"

        serialized = msgpack.packb(dict(checkpoint), use_bin_type=True)

        pipe = self._redis.pipeline()
        pipe.hset(key, checkpoint_id, serialized)
        pipe.expire(key, self._ttl)
        await pipe.execute()

        return {"configurable": {"thread_id": thread_id}}

    async def aget_next_version(self, config: dict) -> int:
        """获取下一个版本号"""
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return 1
        key = f"langgraph:checkpoint:{thread_id}"
        count = await self._redis.hlen(key)
        return count + 1

    async def alist(
        self,
        config: dict,
        *,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> list[Checkpoint]:
        """列出某个 thread 的所有 checkpoint（用于调试/回溯）"""
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return []

        key = f"langgraph:checkpoint:{thread_id}"
        checkpoints = await self._redis.hgetall(key)

        results = []
        for cid, data in sorted(checkpoints.items()):
            try:
                decoded = msgpack.unpackb(data, raw=False)
                results.append(Checkpoint(**decoded))
            except Exception:
                continue
            if limit and len(results) >= limit:
                break
        return results

    async def adelete(self, config: dict) -> None:
        """删除某个 thread 的所有 checkpoint"""
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            key = f"langgraph:checkpoint:{thread_id}"
            await self._redis.delete(key)
