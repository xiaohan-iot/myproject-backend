from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import ssl
import threading
import time
from typing import Any

import stomp

from .config import mask_secret, settings
from .db import save_to_db
from .normalizer import append_history, normalize_payload
from .state import latest_state
from .state import last_disconnect_ts as _last_disconnect_ts  # noqa
from .state import last_msg_ts as _last_msg_ts  # noqa
from . import state
from .websocket_manager import manager


class AliyunListener(stomp.ConnectionListener):
    def __init__(self, loop: asyncio.AbstractEventLoop, conn: stomp.Connection):
        super().__init__()
        self.loop = loop
        self.conn = conn

    def on_connected(self, frame):
        print(
            f"[AMQP] connected callback | ts={int(time.time())} | "
            f"group={settings.consumer_group_id} | client={settings.client_id}"
        )

    def on_disconnected(self):
        state.last_disconnect_ts = int(time.time() * 1000)
        print(f"[AMQP] disconnected | ts={int(time.time())}")

    def on_error(self, frame):
        print("[AMQP] error:", getattr(frame, "body", frame))

    def on_heartbeat_timeout(self):
        print("[AMQP] heartbeat timeout")

    def on_message(self, frame):
        body = getattr(frame, "body", "")
        headers = getattr(frame, "headers", {})

        print("\n[AMQP] ===== 收到新消息 =====")
        print("[AMQP] headers:", headers)
        print("[AMQP] body:", body)

        state.last_msg_ts = int(time.time() * 1000)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw_text": body}

        message_id = headers.get("message-id")
        subscription = headers.get("subscription")

        def _enqueue_and_ack() -> None:
            try:
                if state.payload_queue is None:
                    print("[AMQP] queue not ready")
                    return

                state.payload_queue.put_nowait(payload)
                print("[AMQP] payload queued")

                if message_id and subscription:
                    self.conn.ack(id=message_id, subscription=subscription)
                    print(f"[AMQP] ack sent: {message_id}")
            except asyncio.QueueFull:
                print("[AMQP] queue full, payload dropped")
            except Exception as exc:
                print("[AMQP] enqueue/ack failed:", exc)

        self.loop.call_soon_threadsafe(_enqueue_and_ack)


async def process_payload(payload: dict[str, Any]) -> None:
    partial = normalize_payload(payload)

    merged = dict(latest_state)

    for key, value in partial.items():
        if key in ("updatedAt", "raw"):
            continue
        if value is not None:
            merged[key] = value

    merged["updatedAt"] = partial.get("updatedAt")
    merged["raw"] = partial.get("raw")

    latest_state.clear()
    latest_state.update(merged)

    append_history(partial)

    try:
        save_to_db(merged)
    except Exception as exc:
        print("[DB] save failed:", exc)

    try:
        await manager.broadcast_json({"type": "device_update", "data": merged})
    except Exception as exc:
        print("[WS] broadcast failed:", exc)


async def payload_worker() -> None:
    while True:
        payload = await state.payload_queue.get()  # type: ignore[union-attr]
        try:
            await process_payload(payload)
            print("[QUEUE] payload processed ok")
        except Exception as exc:
            print("[QUEUE] process failed:", exc)
        finally:
            state.payload_queue.task_done()  # type: ignore[union-attr]


class AliyunAmqpWorker(threading.Thread):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__(daemon=True)
        self.loop = loop
        self.stop_event = threading.Event()
        self.conn: stomp.Connection | None = None

    def build_auth(self) -> tuple[str, str]:
        timestamp = str(int(time.time() * 1000))
        parts = [
            "authMode=aksign",
            "signMethod=hmacsha1",
            f"timestamp={timestamp}",
            f"authId={settings.access_key_id}",
        ]
        if settings.iot_instance_id:
            parts.append(f"iotInstanceId={settings.iot_instance_id}")
        parts.append(f"consumerGroupId={settings.consumer_group_id}")

        username = f"{settings.client_id}|{','.join(parts)}|"
        sign_content = f"authId={settings.access_key_id}&timestamp={timestamp}"
        password = base64.b64encode(
            hmac.new(
                settings.access_key_secret.encode("utf-8"),
                sign_content.encode("utf-8"),
                digestmod=hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return username, password

    def new_connection(self) -> stomp.Connection:
        conn = stomp.Connection(
            [(settings.amqp_host, 61614)],
            heartbeats=(settings.heartbeat_ms, settings.heartbeat_ms),
        )
        conn.set_listener("", AliyunListener(self.loop, conn))
        conn.set_ssl(
            for_hosts=[(settings.amqp_host, 61614)],
            ssl_version=ssl.PROTOCOL_TLS,
        )
        return conn

    def stop(self) -> None:
        self.stop_event.set()
        try:
            if self.conn and self.conn.is_connected():
                self.conn.disconnect()
        except Exception:
            pass

    def run(self) -> None:
        settings.validate_for_amqp()

        while not self.stop_event.is_set():
            try:
                self.conn = self.new_connection()
                username, password = self.build_auth()
                self.conn.connect(username, password, wait=True)
                self.conn.subscribe(destination="/topic/#", id=1, ack="client-individual")
                print(
                    f"[AMQP] connected and subscribed | group={settings.consumer_group_id} | client={settings.client_id}"
                )

                while not self.stop_event.is_set():
                    if not self.conn or not self.conn.is_connected():
                        print(f"[AMQP] connection lost, reconnecting in {settings.reconnect_seconds}s...")
                        break
                    time.sleep(2)

            except Exception as exc:
                print("[AMQP] reconnect after error:", exc)
                time.sleep(settings.reconnect_seconds)
            finally:
                try:
                    if self.conn and self.conn.is_connected():
                        self.conn.disconnect()
                except Exception:
                    pass
                self.conn = None


def print_boot_config() -> None:
    print("\n========== BOOT CONFIG ==========")
    print(f"[BOOT] ENABLE_AMQP={settings.enable_amqp}")
    print(f"[BOOT] ENABLE_DB_WRITE={settings.enable_db_write}")
    print(f"[BOOT] AMQP_HOST={settings.amqp_host}")
    print(f"[BOOT] IOT_INSTANCE_ID={settings.iot_instance_id or '(empty)'}")
    print(f"[BOOT] CONSUMER_GROUP_ID={settings.consumer_group_id}")
    print(f"[BOOT] AMQP_CLIENT_ID={settings.client_id}")
    print(f"[BOOT] ACCESS_KEY_ID={mask_secret(settings.access_key_id)}")
    print(f"[BOOT] ACCESS_KEY_SECRET={mask_secret(settings.access_key_secret)}")
    print("=================================\n")
