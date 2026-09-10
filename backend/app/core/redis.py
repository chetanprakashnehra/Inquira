import json
import logging
from typing import AsyncGenerator, Optional
from app.config import settings

logger = logging.getLogger(__name__)

redis_client = None


async def get_redis():
    """Returns or initializes the global async Redis client."""
    global redis_client
    if redis_client is None:
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
        except Exception as e:
            if settings.ENVIRONMENT == "development":
                logger.warning(f"Could not connect to Redis at {settings.REDIS_URL}: {e}")
            else:
                logger.error(f"Could not connect to Redis in production at {settings.REDIS_URL}: {e}")
            return None
    return redis_client


async def publish_progress(channel: str, data: dict) -> None:
    """Publish real-time ingestion/processing progress to a Redis pub/sub channel."""
    try:
        client = await get_redis()
        if client:
            await client.publish(channel, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to publish progress to channel {channel}: {e}")


async def subscribe_progress(channel: str) -> AsyncGenerator[str, None]:
    """Subscribe to a Redis channel and yield Server-Sent Events (SSE) data chunks."""
    client = await get_redis()
    if not client:
        yield f"data: {json.dumps({'status': 'INFO', 'message': 'Progress streaming active (offline broker mode)'})}\n\n"
        return

    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    except Exception as e:
        logger.error(f"Error streaming from Redis channel {channel}: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
