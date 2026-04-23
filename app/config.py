from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    cors_origins: List[str] = None  # type: ignore[assignment]

    history_limit: int = int(os.getenv("HISTORY_LIMIT", "500"))
    enable_db_write: bool = os.getenv("ENABLE_DB_WRITE", "0") == "1"
    sqlite_path: str = os.getenv("SQLITE_PATH", "sensor_data.db")
    queue_maxsize: int = int(os.getenv("QUEUE_MAXSIZE", "1000"))

    enable_amqp: bool = os.getenv("ENABLE_AMQP", "1") == "1"
    amqp_host: str = os.getenv("AMQP_HOST", "").strip()
    iot_instance_id: str = os.getenv("IOT_INSTANCE_ID", "").strip()
    consumer_group_id: str = os.getenv("CONSUMER_GROUP_ID", "").strip()
    client_id: str = os.getenv("AMQP_CLIENT_ID", "gap-monitor-backend-001").strip()
    access_key_id: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip()
    access_key_secret: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "").strip()

    heartbeat_ms: int = int(os.getenv("AMQP_HEARTBEAT_MS", "10000"))
    reconnect_seconds: int = int(os.getenv("AMQP_RECONNECT_SECONDS", "2"))

    def __post_init__(self) -> None:
        raw = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins = [x.strip() for x in raw.split(",") if x.strip()]

    def validate_for_amqp(self) -> None:
        required = {
            "AMQP_HOST": self.amqp_host,
            "CONSUMER_GROUP_ID": self.consumer_group_id,
            "ALIBABA_CLOUD_ACCESS_KEY_ID": self.access_key_id,
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": self.access_key_secret,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"缺少环境变量: {', '.join(missing)}")


def mask_secret(value: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return value[:keep_start] + "*" * (len(value) - keep_start - keep_end) + value[-keep_end:]


settings = Settings()
