from redis.asyncio import Redis
from redis.backoff import ExponentialBackoff, NoBackoff
from redis.exceptions import ConnectionError, TimeoutError
import os
from redis.retry import Retry
import json

def initialize_redis(retries: int = 1):
    backoff = ExponentialBackoff() if retries > 1 else NoBackoff()
    retry = Retry(backoff, retries)
    print(os.environ.get("REDISHOST", "localhost"))
    return Redis(  # type: ignore
        host=os.environ.get("REDISHOST", "localhost"),
        port=int(os.environ.get("REDISPORT", 6379)),
        username=os.environ.get("REDISUSER", None),
        password=os.environ.get("REDISPASSWORD", None),
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
    return json.loads(config) if config else {}