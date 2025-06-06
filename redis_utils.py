from redis.asyncio import Redis
from redis.backoff import ExponentialBackoff, NoBackoff
from redis.exceptions import ConnectionError, TimeoutError
import os
from redis.retry import Retry
import json

def initialize_redis(retries: int = 1):
    backoff = ExponentialBackoff() if retries > 1 else NoBackoff()
    retry = Retry(backoff, retries)
    return Redis(  # type: ignore
        host=os.environ.get("REDISHOST", "34.67.141.27"),
        port=int(os.environ.get("REDISPORT", 6377)),
        username=os.environ.get("REDISUSER", None),
        password=os.environ.get("REDISPASSWORD", "password"),
        db=0,
        decode_responses=True,
        retry=retry,
        ssl=bool(os.environ.get("REDISSSL", False)),
        ssl_cert_reqs="none",
        retry_on_error=[ConnectionError, TimeoutError],
        health_check_interval=30,
    )

async def get_config_by_room_id(room_id: str) -> dict:
    redis = initialize_redis()
    config = await redis.get(room_id)
    return config