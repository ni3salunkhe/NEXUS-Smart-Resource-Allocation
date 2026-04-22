"""
Kafka Integration Layer
─ NexusProducer: Singleton with retry/backoff and thread-safe lifecycle
─ NexusConsumer: Resilient consumer with startup backoff and dead-letter support
─ NexusEvent: Canonical event envelope
"""
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError, KafkaConnectionError
import json
import asyncio
import logging
import time
from typing import Callable, Awaitable, Any, Optional
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
    """
    Singleton Kafka producer with:
    - Retry/backoff on startup
    - Thread-safe lifecycle (no external reset)
    - Graceful degradation when Kafka is unavailable
    """
    _instance: "NexusProducer" = None
    _lock: asyncio.Lock = None

    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None
        self._started = False
        self._starting = False

    @classmethod
    def get(cls) -> "NexusProducer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_ready(self) -> bool:
        return self._started and self._producer is not None

    async def start(self, max_retries: int = 5, base_delay: float = 1.0):
        """Start producer with exponential backoff retry."""
        if self._started:
            return

        # Prevent concurrent start attempts
        if NexusProducer._lock is None:
            NexusProducer._lock = asyncio.Lock()

        async with NexusProducer._lock:
            if self._started:  # Double-check after acquiring lock
                return

            self._starting = True
            for attempt in range(1, max_retries + 1):
                try:
                    self._producer = AIOKafkaProducer(
                        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                        value_serializer=lambda v: v,  # pre-serialized bytes
                        compression_type="gzip",
                        acks="all",
                        request_timeout_ms=10000,
                        retry_backoff_ms=500,
                    )
                    await self._producer.start()
                    self._started = True
                    self._starting = False
                    logger.info(f"Kafka producer started (attempt {attempt})")
                    return
                except (KafkaConnectionError, KafkaError, OSError) as e:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(f"Kafka producer start failed (attempt {attempt}/{max_retries}): {e}. Retrying in {delay:.1f}s...")
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                    else:
                        self._starting = False
                        logger.error(f"Kafka producer failed after {max_retries} attempts. Running in degraded mode.")
                        raise

    async def stop(self):
        """Stop producer gracefully. Does NOT reset the singleton."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            self._started = False
            logger.info("Kafka producer stopped")

    async def emit(
        self,
        topic: str,
        event: NexusEvent,
        key: str = None,
    ) -> None:
        if not self._started or not self._producer:
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
    """
    Resilient consumer with:
    - Startup retry with exponential backoff
    - Dead-letter queue routing for failed messages
    - Configurable max retries per message
    """

    DLQ_SUFFIX = ".dlq"
    MAX_HANDLER_RETRIES = 3

    def __init__(
        self,
        topics: list[str],
        group_id: str,
        handler: Callable[[NexusEvent], Awaitable[None]],
        enable_dlq: bool = True,
    ):
        self.topics    = topics
        self.group_id  = group_id
        self.handler   = handler
        self.enable_dlq = enable_dlq
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running  = False
        self._processed_ids: set = set()  # For idempotency

    async def start(self, max_retries: int = 10, base_delay: float = 2.0):
        """Start consumer with retry/backoff to survive GroupCoordinatorNotAvailable."""
        for attempt in range(1, max_retries + 1):
            try:
                self._consumer = AIOKafkaConsumer(
                    *self.topics,
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    group_id=self.group_id,
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    value_deserializer=lambda v: v,  # raw bytes
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=10000,
                    max_poll_interval_ms=300000,
                )
                await self._consumer.start()
                self._running = True
                logger.info(f"Consumer started (attempt {attempt}): topics={self.topics} group={self.group_id}")
                await self._consume_loop()
                return
            except (KafkaConnectionError, KafkaError, OSError) as e:
                delay = base_delay * (2 ** (attempt - 1))
                delay = min(delay, 60)  # Cap at 60s
                logger.warning(f"Consumer start failed (attempt {attempt}/{max_retries}): {e}. Retrying in {delay:.1f}s...")
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Consumer failed after {max_retries} attempts.")
                    raise

    async def stop(self):
        self._running = False
        if self._consumer:
            try:
                await asyncio.wait_for(self._consumer.stop(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Consumer stop timed out")

    async def _consume_loop(self):
        while self._running:
            try:
                # Use a small timeout to allow checking self._running
                res = await self._consumer.getmany(timeout_ms=1000)
                for tp, msgs in res.items():
                    for msg in msgs:
                        if not self._running: break
                        await self._process_message(msg)
            except Exception as e:
                if self._running:
                    logger.error(f"Consumer loop error: {e}")
                await asyncio.sleep(1.0)

    async def _process_message(self, msg):
        try:
            event = NexusEvent.deserialize(msg.value)

            # Event-level idempotency: skip if already processed
            if event.event_id in self._processed_ids:
                logger.debug(f"Skipping duplicate event: {event.event_id}")
                return

            # Attempt handler with retries
            handled = False
            for retry in range(self.MAX_HANDLER_RETRIES):
                try:
                    await self.handler(event)
                    self._processed_ids.add(event.event_id)
                    # Cap the set size to prevent memory leak
                    if len(self._processed_ids) > 100_000:
                        self._processed_ids = set(list(self._processed_ids)[-50_000:])
                    handled = True
                    break
                except Exception as handler_err:
                    logger.warning(f"Handler retry {retry+1}/{self.MAX_HANDLER_RETRIES} for {event.event_id}: {handler_err}")
                    if retry < self.MAX_HANDLER_RETRIES - 1:
                        await asyncio.sleep(0.5 * (retry + 1))

            if not handled and self.enable_dlq:
                await self._send_to_dlq(msg, event)

        except Exception as e:
            logger.error(f"Consumer error on {msg.topic}:{msg.partition}:{msg.offset} — {e}")

    async def _send_to_dlq(self, original_msg, event: NexusEvent):
        """Route failed message to dead-letter queue topic."""
        dlq_topic = original_msg.topic + self.DLQ_SUFFIX
        try:
            producer = NexusProducer.get()
            if producer.is_ready:
                dlq_event = NexusEvent(
                    event_type=f"dlq.{event.event_type}",
                    payload={
                        "original_event": event.to_dict(),
                        "failure_reason": "max_retries_exceeded",
                        "original_topic": original_msg.topic,
                        "original_offset": original_msg.offset,
                    },
                    tenant_id=event.tenant_id,
                    correlation_id=event.correlation_id,
                )
                await producer.emit(dlq_topic, dlq_event)
                logger.warning(f"Sent to DLQ: {dlq_topic} event_id={event.event_id}")
            else:
                logger.error(f"Cannot send to DLQ (producer not ready): event_id={event.event_id}")
        except Exception as e:
            logger.error(f"DLQ send failed for event_id={event.event_id}: {e}")


# ── Topic initialization ──────────────────────────────────────
ALL_TOPICS = [v for k, v in vars(KafkaTopics).items() if not k.startswith("_")]

async def ensure_topics_exist(topics: list = None, max_retries: int = 5, base_delay: float = 2.0):
    """Create Kafka topics if they don't exist. Retries on coordinator errors."""
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    target_topics = topics if topics is not None else ALL_TOPICS
    for attempt in range(1, max_retries + 1):
        try:
            admin = AIOKafkaAdminClient(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
            await admin.start()
            try:
                existing = await admin.list_topics()
                to_create = [
                    NewTopic(name=t, num_partitions=3, replication_factor=1)
                    for t in target_topics if t not in existing
                ]
                if to_create:
                    await admin.create_topics(to_create)
                    logger.info(f"Created Kafka topics: {[t.name for t in to_create]}")
                else:
                    logger.info(f"All {len(target_topics)} topics already exist")
                return  # Success
            finally:
                await admin.close()
        except Exception as e:
            delay = base_delay * (2 ** (attempt - 1))
            delay = min(delay, 30)
            logger.warning(f"Topic setup failed (attempt {attempt}/{max_retries}): {e}. Retrying in {delay:.1f}s...")
            if attempt < max_retries:
                await asyncio.sleep(delay)
            else:
                logger.error(f"Topic setup failed after {max_retries} attempts: {e}")