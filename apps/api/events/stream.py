"""Server-Sent Events bridge over Redis pub/sub.

Workers publish JSON to channel `job:<id>`; the SSE handler relays those
messages to subscribed clients.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from apps.api.core.config import get_settings


def _channel_for_job(job_id: str) -> str:
    return f"job:{job_id}"


async def publish_event(job_id: str, event: dict) -> None:
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.publish(_channel_for_job(job_id), json.dumps(event))
    finally:
        await redis.aclose()


async def event_stream(job_id: str) -> AsyncIterator[dict]:
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel_for_job(job_id))
    try:
        # initial ping so client knows connection is open
        yield {"event": "ready", "data": json.dumps({"job_id": job_id})}
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if msg is None:
                yield {"event": "ping", "data": "{}"}
                continue
            yield {"event": "job", "data": msg["data"]}
            try:
                payload = json.loads(msg["data"])
                if payload.get("status") in ("done", "failed"):
                    break
            except json.JSONDecodeError:
                pass
            await asyncio.sleep(0)
    finally:
        await pubsub.unsubscribe(_channel_for_job(job_id))
        await pubsub.aclose()
        await redis.aclose()
