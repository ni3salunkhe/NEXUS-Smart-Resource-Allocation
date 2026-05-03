"""
NEXUS WebSocket Bridge Service — C2 Fix
─────────────────────────────────────────────────────────────────────────────
Consumes ALL Kafka topics and fans out events to Socket.IO rooms keyed by
tenant_id.  This is the missing link between the backend event bus and the
frontend real-time layer.

Architecture:
  Kafka (all topics) → NexusConsumer → Socket.IO rooms → Frontend clients

Each Socket.IO room name == tenant_id.
The client authenticates with { token, tenantId } in the Socket.IO auth object.
"""

import asyncio
import logging
import os
import sys

import uvicorn
import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings, KafkaTopics
from shared.auth import decode_token
from shared.kafka import NexusConsumer, NexusEvent

logger   = logging.getLogger(__name__)
settings = get_settings()

# ── Socket.IO server ──────────────────────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.CORS_ORIGINS,
    logger=False,
    engineio_logger=False,
)

# Wrap in a FastAPI ASGI app so we can add /health
_fastapi = FastAPI(title="NEXUS WebSocket Bridge", version="2.0.0")
_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@_fastapi.get("/health")
async def health():
    return {"service": "nexus-ws-bridge", "status": "ok",
            "connected_clients": len(sio.manager.rooms)}


# Mount Socket.IO on top of FastAPI
app = socketio.ASGIApp(sio, other_asgi_app=_fastapi)


# ── Auth on connect ───────────────────────────────────────────────────────────
@sio.event
async def connect(sid, environ, auth):
    """Validate JWT and join the correct tenant room."""
    token     = (auth or {}).get("token")
    tenant_id = (auth or {}).get("tenantId")

    if not token or not tenant_id:
        logger.warning(f"WS connect rejected (no token/tenantId): {sid}")
        return False  # reject

    try:
        payload = decode_token(token)
        # Verify tenant matches claim in JWT
        jwt_tenant = payload.get("tenant_id") or payload.get("sub")
        if payload.get("tenant_id") != tenant_id and payload.get("role") != "platform_admin":
            logger.warning(f"WS tenant mismatch for {sid}: jwt={jwt_tenant} auth={tenant_id}")
            return False
    except JWTError as e:
        logger.warning(f"WS connect rejected (invalid JWT): {sid} — {e}")
        return False

    await sio.enter_room(sid, tenant_id)
    logger.info(f"WS client {sid} joined room {tenant_id}")
    await sio.emit("connected", {"status": "ok", "room": tenant_id}, to=sid)


@sio.event
async def disconnect(sid):
    logger.info(f"WS client {sid} disconnected")


# ── Kafka → Socket.IO fanout ──────────────────────────────────────────────────
# Map Kafka topic strings to the Socket.IO event names the frontend expects
# (frontend/src/lib/useSocketEventWiring.ts)
_TOPIC_TO_EVENT: dict[str, str] = {
    KafkaTopics.NEED_CREATED:                  "need.created",
    KafkaTopics.NEED_URGENCY_UPDATED:          "need.urgency_updated",
    KafkaTopics.NEED_STATUS_CHANGED:           "need.status_changed",
    KafkaTopics.TASK_CREATED:                  "task.created",
    KafkaTopics.TASK_DISPATCHED:               "task.dispatched",
    KafkaTopics.TASK_ACCEPTED:                 "task.accepted",
    KafkaTopics.TASK_STARTED:                  "task.started",
    KafkaTopics.TASK_COMPLETED:                "task.completed",
    KafkaTopics.TASK_CANCELLED:                "task.cancelled",
    KafkaTopics.VOLUNTEER_LOCATION_UPDATED:    "volunteer.location_updated",
    KafkaTopics.VOLUNTEER_BURNOUT_ALERT:       "volunteer.burnout_alert",
    KafkaTopics.GAP_REPORT_GENERATED:          "analytics.gap_report.generated",
    KafkaTopics.HOUSEHOLD_CREATED:             "household.created",
    KafkaTopics.HOUSEHOLD_MERGED:              "household.merged",
    KafkaTopics.HOUSEHOLD_LINKED:              "household.linked",
    KafkaTopics.HOUSEHOLD_CONSENT_UPDATED:     "household.consent_updated",
    KafkaTopics.HOUSEHOLD_VULNERABILITY_CHANGED: "household.vulnerability_changed",
    KafkaTopics.NEED_DUPLICATE_DETECTED:       "need.duplicate_detected",
}

ALL_SUBSCRIBED_TOPICS = list(_TOPIC_TO_EVENT.keys())


async def _handle_kafka_event(event: NexusEvent) -> None:
    """Fan out a Kafka event to the correct Socket.IO tenant room."""
    socket_event = _TOPIC_TO_EVENT.get(event.event_type)
    if not socket_event:
        return

    tenant_id = event.tenant_id
    if not tenant_id:
        logger.debug(f"Event {event.event_type} has no tenant_id — skipping fanout")
        return

    await sio.emit(socket_event, event.payload, room=tenant_id)
    logger.debug(f"Fanned out {socket_event} → room:{tenant_id}")


# ── Lifecycle ─────────────────────────────────────────────────────────────────
_consumer: NexusConsumer | None = None
_consumer_task: asyncio.Task | None = None


async def _start_consumer():
    global _consumer
    _consumer = NexusConsumer(
        topics    = ALL_SUBSCRIBED_TOPICS,
        group_id  = "nexus-ws-bridge",
        handler   = _handle_kafka_event,
        enable_dlq= True,
    )
    await _consumer.start()


@_fastapi.on_event("startup")
async def startup():
    global _consumer_task
    _consumer_task = asyncio.create_task(_start_consumer())
    logger.info("WebSocket bridge started — consuming Kafka topics")


@_fastapi.on_event("shutdown")
async def shutdown():
    if _consumer:
        await _consumer.stop()
    if _consumer_task:
        _consumer_task.cancel()
    logger.info("WebSocket bridge stopped")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "services.gateway.ws_bridge:app",
        host="0.0.0.0",
        port=8006,
        log_level="info",
    )
