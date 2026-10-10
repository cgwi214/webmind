"""Redis 缓存与任务状态。

保存：任务实时状态、任务队列、Agent 运行状态、RAG 组件文档热点缓存。
CACHE_BACKEND=auto 时，Redis 不可达自动降级为进程内缓存。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webmind.cache")

STATUS_FLOW = [
    "queued",
    "parsing",
    "generating",
    "reviewing",
    "adapting",
    "delivered",
    "needs_clarification",
    "human_required",
    "failed",
]


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            expire = time.time() + ttl if ttl else 0
            self._data[key] = (value, expire)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            value, expire = self._data.get(key, (default, 0))
            if expire and time.time() > expire:
                self._data.pop(key, None)
                return default
            return value

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return [k for k in self._data if k.startswith(prefix)]


class RedisCache(MemoryCache):
    def __init__(self) -> None:
        super().__init__()
        import redis  # 局部导入

        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=1,
        )
        self.client.ping()

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        self.client.set(key, payload, ex=ttl)

    def get(self, key: str, default: Any = None) -> Any:
        raw = self.client.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return raw

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def keys(self, prefix: str = "") -> list[str]:
        return list(self.client.scan_iter(match=f"{prefix}*"))


_cache: MemoryCache | None = None
_lock = threading.Lock()


def get_cache() -> MemoryCache:
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        backend = (settings.CACHE_BACKEND or "auto").lower()
        if backend == "redis":
            _cache = RedisCache()
            logger.info("缓存后端: Redis(%s:%s)", settings.REDIS_HOST, settings.REDIS_PORT)
        elif backend == "memory":
            _cache = MemoryCache()
        else:
            try:
                _cache = RedisCache()
                logger.info("缓存后端: Redis(%s:%s)", settings.REDIS_HOST, settings.REDIS_PORT)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 不可用(%s)，降级为进程内缓存", exc)
                _cache = MemoryCache()
        return _cache


def cache_backend_name() -> str:
    return "redis" if isinstance(get_cache(), RedisCache) else "memory"


# ===================== 任务状态 =====================


def set_task_status(task_id: str, status: str, current_agent: str = "", message: str = "") -> None:
    payload = {
        "task_id": task_id,
        "status": status,
        "current_agent": current_agent,
        "message": message,
        "updated_at": time.time(),
    }
    get_cache().set(f"task:status:{task_id}", payload, ttl=86400)


def get_task_status(task_id: str) -> dict:
    return get_cache().get(f"task:status:{task_id}", {}) or {}


def set_agent_state(task_id: str, agent: str, payload: dict) -> None:
    get_cache().set(f"task:agent:{task_id}:{agent}", payload, ttl=86400)


def get_agent_states(task_id: str) -> dict:
    cache = get_cache()
    result = {}
    for key in cache.keys(f"task:agent:{task_id}:"):
        result[key.split(":")[-1]] = cache.get(key)
    return result


# ===================== 任务队列 =====================


def enqueue(task_id: str) -> None:
    queue = get_cache().get("task:queue", []) or []
    if task_id not in queue:
        queue.append(task_id)
        get_cache().set("task:queue", queue)


def dequeue(task_id: str) -> None:
    queue = get_cache().get("task:queue", []) or []
    if task_id in queue:
        queue.remove(task_id)
        get_cache().set("task:queue", queue)


def queue_snapshot() -> list[str]:
    return get_cache().get("task:queue", []) or []


# ===================== 通用缓存（RAG 热点文档等） =====================


def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    get_cache().set(f"cache:{key}", value, ttl=ttl)


def cache_get(key: str, default: Any = None) -> Any:
    return get_cache().get(f"cache:{key}", default)
