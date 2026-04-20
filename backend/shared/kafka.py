from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
import json
import asyncio
import logging
from typing import Callable, Awaitable, Any
from uuid import uuid4
from datetime import datetime, timezone

from .config import get_settings, KafkaTopics

logger = logging.getLogger(__name__)
settings = get_settings()


class NexusEvent:
    """Canonical event envelope for all Kafka messages."""
    def __init__(
        self,
        event_type: str,
        payload: dict,
        tenant_id: str = None,
        user_id: str = None,
        correlation_id: str = None,
    ):
        self.event_id      = str(uuid4())
        self.event_type    = event_type
        self.payload       = payload
        self.tenant_id     = tenant_id
        self.user_id       = user_id
        self.correlation_id = correlation_id or str(uuid4())
        self.timestamp     = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_id":       self.event_id,
            "event_type":     self.event_type,
            "payload":        self.payload,
            "tenant_id":      self.tenant_id,
            "user_id":        self.user_id,
            "correlation_id": self.correlation_id,
            "timestamp":      self.timestamp,
        }

    def serialize(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "NexusEvent":
        d = json.loads(data.decode("utf-8"))
        evt = cls(
            event_type=d["event_type"],
            payload=d["payload"],
            tenant_id=d.get("tenant_id"),
            user_id=d.get("user_id"),
            correlation_id=d.get("correlation_id"),
        )
        evt.event_id  = d["event_id"]
        evt.timestamp = d["timestamp"]
        return evt


class NexusProducer:
    """Singleton Kafka producer. Call start() on app startup."""
    _instance: "NexusProducer" = None

    def __init__(self):
        self._producer: AIOKafkaProducer = None

    @classmethod
    def get(cls) -> "NexusProducer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: v,  # pre-serialized bytes
            compression_type="gzip",
            enable_idempotence=True,
            acks="all",
            retries=5,
        )
        await self._producer.start()
        logger.info("Kafka producer started")

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def emit(
        self,
        topic: str,
        event: NexusEvent,
        key: str = None,
    ) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer not started")
        try:
            await self._producer.send_and_wait(
                topic,
                value=event.serialize(),
                key=key.encode() if key else None,
                headers=[
                    ("event_type", event.event_type.encode()),
                    ("tenant_id", (event.tenant_id or "").encode()),
                    ("correlation_id", event.correlation_id.encode()),
                ]
            )
            logger.debug(f"Emitted {event.event_type} -> {topic}")
        except KafkaError as e:
            logger.error(f"Kafka emit failed: {e}")
            raise


class NexusConsumer:
    """Base consumer. Subclass and implement handle_event()."""

    def __init__(
        self,
        topics: list[str],
        group_id: str,
        handler: Callable[[NexusEvent], Awaitable[None]],
    ):
        self.topics   = topics
        self.group_id = group_id
        self.handler  = handler
        self._consumer: AIOKafkaConsumer = None
        self._running  = False

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda v: v,  # raw bytes
        )
        await self._consumer.start()
        self._running = True
        logger.info(f"Consumer started: topics={self.topics} group={self.group_id}")
        await self._consume_loop()

    async def stop(self):
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    async def _consume_loop(self):
        async for msg in self._consumer:
            if not self._running:
                break
            try:
                event = NexusEvent.deserialize(msg.value)
                await self.handler(event)
            except Exception as e:
                logger.error(f"Consumer error on {msg.topic}:{msg.partition}:{msg.offset} — {e}")
                # Continue consuming; dead-letter queue would go here in prod


# ── Topic initialization ──────────────────────────────────────
ALL_TOPICS = [v for k, v in vars(KafkaTopics).items() if not k.startswith("_")]

async def ensure_topics_exist():
    """Create all Kafka topics if they don't exist. Call at startup."""
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    await admin.start()
    try:
        existing = await admin.list_topics()
        to_create = [
            NewTopic(name=t, num_partitions=3, replication_factor=1)
            for t in ALL_TOPICS if t not in existing
        ]
        if to_create:
            await admin.create_topics(to_create)
            logger.info(f"Created Kafka topics: {[t.name for t in to_create]}")
    except Exception as e:
        logger.warning(f"Topic setup warning: {e}")
    finally:
        await admin.close()