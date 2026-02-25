import asyncio
import os

import redis.asyncio as aioredis
from fastapi import Request
from fastapi.responses import StreamingResponse

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Send a keepalive comment every N seconds to prevent proxy / load-balancer timeouts
HEARTBEAT_INTERVAL = 15


async def _event_generator(request: Request):
    """
    Subscribe to the Redis 'resume_events' pub/sub channel and forward
    each message to the browser as an SSE event.

    Also sends a ':keepalive' comment every 15 s so nginx / proxies don't
    close the connection due to inactivity.
    """
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("resume_events")

    last_ping = asyncio.get_event_loop().time()

    try:
        while True:
            # Bail out if the browser closed the tab / navigated away
            if await request.is_disconnected():
                break

            # Non-blocking check — waits up to 1 s for a message
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )

            if message and message["type"] == "message":
                yield f"data: {message['data']}\n\n"
                last_ping = asyncio.get_event_loop().time()

            # Heartbeat so nginx doesn't close an idle SSE connection
            now = asyncio.get_event_loop().time()
            if now - last_ping >= HEARTBEAT_INTERVAL:
                yield ": keepalive\n\n"
                last_ping = now

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe("resume_events")
        await r.aclose()


async def sse_endpoint(request: Request):
    """
    GET /api/events

    Long-lived SSE stream. The browser keeps this connection open and
    receives a push notification the moment a resume finishes parsing.

    X-Accel-Buffering: no  — tells nginx to disable response buffering
                              so events reach the browser immediately.
    """
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
