from __future__ import annotations

import redis

from app.config import RedisConfig


def build_redis_client(config: RedisConfig):
    return redis.Redis(
        host=config.host,
        port=config.port,
        decode_responses=config.decode_responses,
    )
