"""Redis и очередь RQ для задач провижининга узлов."""

from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue

from app.core.config import settings

__all__ = ["RedisError", "get_install_queue", "get_redis"]


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=10,
        socket_timeout=60,
        health_check_interval=30,
    )


def get_install_queue() -> Queue:
    return Queue(settings.redis_install_queue_name, connection=get_redis())
