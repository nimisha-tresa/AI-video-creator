from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.services.auth import decode_token

settings = get_settings()
router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """Manages per-user WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id].discard(ws) if hasattr(
                self._connections[user_id], "discard"
            ) else self._connections[user_id].remove(ws)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


async def broadcast_generation_update(user_id: str, payload: dict) -> None:
    """Called by Celery workers via Redis pub/sub to push progress updates."""
    await manager.send_to_user(user_id, {"type": "generation_update", "data": payload})


@router.websocket("/generations/{user_id}")
async def generation_ws(websocket: WebSocket, user_id: str, token: str):
    # Validate token
    try:
        payload = decode_token(token)
        if payload.get("sub") != user_id:
            await websocket.close(code=4001)
            return
    except ValueError:
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)
    redis = aioredis.from_url(settings.redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"user:{user_id}:generations")

    async def _redis_listener():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                data = json.loads(msg["data"])
                await manager.send_to_user(user_id, data)

    listener_task = asyncio.create_task(_redis_listener())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        manager.disconnect(user_id, websocket)
        await pubsub.unsubscribe(f"user:{user_id}:generations")
        await redis.aclose()
