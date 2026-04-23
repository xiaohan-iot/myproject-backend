from __future__ import annotations

import asyncio
import io
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .amqp_worker import AliyunAmqpWorker, payload_worker, print_boot_config
from .config import settings
from .db import (
    clear_sensor_data,
    close_db,
    get_db,
    get_history_from_db,
    get_latest_from_db,
    init_db,
)
from .models import HealthResponse
from .state import history_cache, latest_state
from . import state
from .websocket_manager import manager

_amqp_worker: AliyunAmqpWorker | None = None
_queue_worker_task: asyncio.Task | None = None


NAVIGATION = [
    {
        "key": "monitor",
        "title": "实时监测",
        "icon": "▣",
        "expanded": True,
        "children": [
            {"key": "overview", "title": "总览面板"},
            {"key": "gap", "title": "气隙距离"},
            {"key": "env", "title": "环境参数"},
        ],
    },
    {
        "key": "device",
        "title": "设备状态",
        "icon": "⌘",
        "expanded": False,
        "children": [],
    },
    {
        "key": "history",
        "title": "历史趋势",
        "icon": "☰",
        "expanded": False,
        "children": [
            {"key": "distance_curve", "title": "距离曲线"},
            {"key": "complex_curve", "title": "c_re / d_im"},
            {"key": "xy_curve", "title": "x / y"},
        ],
    },
    {
        "key": "record",
        "title": "参数记录",
        "icon": "◫",
        "expanded": False,
        "children": [
            {"key": "realtime_table", "title": "实时参数表"},
        ],
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _amqp_worker, _queue_worker_task

    init_db()
    print_boot_config()

    state.payload_queue = asyncio.Queue(maxsize=settings.queue_maxsize)
    _queue_worker_task = asyncio.create_task(payload_worker())

    if settings.enable_amqp:
        loop = asyncio.get_running_loop()
        _amqp_worker = AliyunAmqpWorker(loop)
        _amqp_worker.start()

    try:
        yield
    finally:
        if _amqp_worker is not None:
            _amqp_worker.stop()
            _amqp_worker.join(timeout=3)

        if _queue_worker_task is not None:
            _queue_worker_task.cancel()
            try:
                await _queue_worker_task
            except asyncio.CancelledError:
                pass

        close_db()


app = FastAPI(title="Gap Monitor Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.cors_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Gap Monitor Backend is running."}


@app.get("/api/health", response_model=HealthResponse)
def health() -> dict[str, Any]:
    qsize = state.payload_queue.qsize() if state.payload_queue is not None else 0

    amqp_connected = False
    if _amqp_worker is not None and _amqp_worker.conn is not None:
        try:
            amqp_connected = _amqp_worker.conn.is_connected()
        except Exception:
            amqp_connected = False

    now_ms = int(time.time() * 1000)

    return {
        "ok": True,
        "amqp_enabled": settings.enable_amqp,
        "amqp_connected": amqp_connected,
        "db_enabled": settings.enable_db_write,
        "queue_size": qsize,
        "last_msg_ts": state.last_msg_ts or None,
        "last_msg_ago_ms": (now_ms - state.last_msg_ts) if state.last_msg_ts else None,
        "last_disconnect_ts": state.last_disconnect_ts or None,
        "last_disconnect_ago_ms": (now_ms - state.last_disconnect_ts) if state.last_disconnect_ts else None,
        "time": now_ms,
    }


@app.get("/api/device/latest")
def get_latest() -> dict[str, Any]:
    db_latest = get_latest_from_db()
    if db_latest is not None:
        return db_latest
    return latest_state


@app.get("/api/device/history")
def get_history(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, list[dict[str, Any]]]:
    db_history = get_history_from_db(limit)
    if db_history:
        return db_history

    result: dict[str, list[dict[str, Any]]] = {}
    for key, q in history_cache.items():
        data = list(q)
        result[key] = data[-limit:]
    return result


@app.get("/api/navigation")
def get_navigation() -> list[dict[str, Any]]:
    return NAVIGATION


@app.get("/api/db/info")
def db_info() -> dict[str, Any]:
    if not settings.enable_db_write:
        return {
            "db_enabled": False,
            "count": 0,
            "sqlite_path": settings.sqlite_path,
        }

    db = get_db()
    row = db.execute("SELECT COUNT(*) AS cnt FROM sensor_data").fetchone()
    return {
        "db_enabled": True,
        "count": row["cnt"] if row else 0,
        "sqlite_path": settings.sqlite_path,
    }


@app.post("/api/db/clear")
async def clear_db_api() -> dict[str, Any]:
    if not settings.enable_db_write:
        raise HTTPException(status_code=400, detail="数据库写入未启用，无法清空数据库。")

    clear_sensor_data()

    for key in list(latest_state.keys()):
        latest_state[key] = None

    for q in history_cache.values():
        q.clear()

    state.last_msg_ts = 0

    await manager.broadcast_json({"type": "device_update", "data": latest_state})

    return {"ok": True, "message": "数据库与内存缓存已清空。"}


@app.get("/api/db/export-excel")
def export_db_excel():
    if not settings.enable_db_write:
        raise HTTPException(status_code=400, detail="数据库写入未启用，无法导出 Excel。")

    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 openpyxl，请先执行 pip install openpyxl")

    db = get_db()
    rows = db.execute(
        """
        SELECT id, created_at, product_key, device_name,
               c_re, d_im, x, y, distance_mm,
               temp, humi, current_pos, pos_valid, calib_source, raw_json
        FROM sensor_data
        ORDER BY id DESC
        """
    ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "sensor_data"

    headers = [
        "id",
        "created_at",
        "product_key",
        "device_name",
        "c_re",
        "d_im",
        "x",
        "y",
        "distance_mm",
        "temp",
        "humi",
        "current_pos",
        "pos_valid",
        "calib_source",
        "raw_json",
    ]
    ws.append(headers)

    for row in rows:
        ws.append([
            row["id"],
            row["created_at"],
            row["product_key"],
            row["device_name"],
            row["c_re"],
            row["d_im"],
            row["x"],
            row["y"],
            row["distance_mm"],
            row["temp"],
            row["humi"],
            row["current_pos"],
            row["pos_valid"],
            row["calib_source"],
            row["raw_json"],
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sensor_data.xlsx"},
    )


@app.websocket("/ws/device")
async def ws_device(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "device_update", "data": latest_state})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)