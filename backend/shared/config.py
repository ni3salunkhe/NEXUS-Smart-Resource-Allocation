from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import os


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────
    APP_NAME: str = "NEXUS"
    APP_ENV: str = Field(default="development", validation_alias=AliasChoices("APP_ENV"))
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, validation_alias=AliasChoices("DEBUG"))

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://nexus:nexus_secret@localhost:6432/nexus",
        validation_alias=AliasChoices("DATABASE_URL")
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://nexus:nexus_secret@localhost:6432/nexus",
        validation_alias=AliasChoices("DATABASE_URL_SYNC")
    )
    DATABASE_URL_REPLICA: str = Field(
        default="postgresql+asyncpg://nexus:nexus_secret@localhost:5433/nexus",
        validation_alias=AliasChoices("DATABASE_URL_REPLICA")
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30

    # ── MongoDB ───────────────────────────────────────────────
    MONGODB_URL: str = Field(
        default="mongodb://nexus:nexus_secret@localhost:27017/nexus_ingestion?authSource=admin",
        validation_alias=AliasChoices("MONGODB_URL")
    )
    MONGODB_DB: str = "nexus_ingestion"

    # ── Elasticsearch ─────────────────────────────────────────
    ELASTICSEARCH_URL: str = Field(
        default="http://localhost:9200",
        validation_alias=AliasChoices("ELASTICSEARCH_URL")
    )

    # ── Kafka ─────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        validation_alias=AliasChoices("KAFKA_BOOTSTRAP_SERVERS")
    )
    KAFKA_CONSUMER_GROUP: str = "nexus-services"

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL")
    )
    REDIS_CACHE_TTL: int = 300  # seconds

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(validation_alias=AliasChoices("JWT_SECRET_KEY"))
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── System Admin ─────────────────────────────────────────
    SYSTEM_ADMIN_EMAIL: str = Field(default="admin@nexus.org", validation_alias=AliasChoices("SYSTEM_ADMIN_EMAIL"))
    SYSTEM_ADMIN_PASSWORD: str = Field(default="admin123", validation_alias=AliasChoices("SYSTEM_ADMIN_PASSWORD"))

    # ── Encryption ────────────────────────────────────────────
    PII_ENCRYPTION_KEY: str = Field(validation_alias=AliasChoices("PII_ENCRYPTION_KEY"))

    # ── AWS ───────────────────────────────────────────────────
    AWS_REGION: str = Field(default="ap-south-1", validation_alias=AliasChoices("AWS_REGION"))
    AWS_S3_BUCKET_RAW: str = Field(default="nexus-raw-ingestion", validation_alias=AliasChoices("AWS_S3_BUCKET_RAW"))
    AWS_KMS_KEY_ID: Optional[str] = Field(default=None, validation_alias=AliasChoices("AWS_KMS_KEY_ID"))

    # ── External APIs ─────────────────────────────────────────
    GOOGLE_VISION_API_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("GOOGLE_VISION_API_KEY"))
    GOOGLE_MAPS_API_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY"))
    GOOGLE_SPEECH_API_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("GOOGLE_SPEECH_API_KEY"))
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, validation_alias=AliasChoices("TWILIO_ACCOUNT_SID"))
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, validation_alias=AliasChoices("TWILIO_AUTH_TOKEN"))
    WHATSAPP_VERIFY_TOKEN: Optional[str] = Field(default=None, validation_alias=AliasChoices("WHATSAPP_VERIFY_TOKEN"))

    # ── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── Rate Limiting ─────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 20

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Kafka topic constants
class KafkaTopics:
    # Ingestion
    INGESTION_IMAGE_RECEIVED    = "ingestion.image.received"
    INGESTION_TEXT_RECEIVED     = "ingestion.text.received"
    INGESTION_AUDIO_RECEIVED    = "ingestion.audio.received"
    INGESTION_CSV_RECEIVED      = "ingestion.csv.received"

    # Household Registry
    HOUSEHOLD_CREATED           = "household.created"
    HOUSEHOLD_UPDATED           = "household.updated"
    HOUSEHOLD_MERGED            = "household.merged"
    HOUSEHOLD_LINKED            = "household.linked"
    HOUSEHOLD_CONSENT_UPDATED   = "household.consent.updated"
    HOUSEHOLD_VULNERABILITY_CHANGED = "household.vulnerability.changed"

    # Needs
    NEED_CREATED                = "need.created"
    NEED_INGESTED               = "need.ingested"
    NEED_VERIFIED               = "need.verified"
    NEED_URGENCY_UPDATED        = "need.urgency.updated"
    NEED_STATUS_CHANGED         = "need.status.changed"
    NEED_DUPLICATE_DETECTED     = "need.duplicate.detected"

    # Tasks
    TASK_CREATED                = "task.created"
    TASK_DISPATCHED             = "task.dispatched"
    TASK_ACCEPTED               = "task.accepted"
    TASK_STARTED                = "task.started"
    TASK_COMPLETED              = "task.completed"
    TASK_CANCELLED              = "task.cancelled"

    # Volunteers
    VOLUNTEER_LOCATION_UPDATED  = "volunteer.location.updated"
    VOLUNTEER_BURNOUT_ALERT     = "volunteer.burnout.alert"

    # Analytics
    GAP_REPORT_GENERATED        = "analytics.gap_report.generated"