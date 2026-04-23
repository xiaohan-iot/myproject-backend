from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import settings

_db_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
    return _db_conn


def get_db_file_path() -> str:
    return str(Path(settings.sqlite_path).resolve())


def init_db() -> None:
    if not settings.enable_db_write:
        return

    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            product_key TEXT,
            device_name TEXT,
            c_re REAL,
            d_im REAL,
            x REAL,
            y REAL,
            distance_mm REAL,
            temp REAL,
            humi REAL,
            current_pos INTEGER,
            pos_valid INTEGER,
            calib_source INTEGER,
            raw_json TEXT
        )
        """
    )
    db.commit()


def save_to_db(data: dict[str, Any]) -> None:
    if not settings.enable_db_write:
        return

    db = get_db()
    db.execute(
        """
        INSERT INTO sensor_data (
            created_at, product_key, device_name, c_re, d_im, x, y,
            distance_mm, temp, humi, current_pos, pos_valid, calib_source, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("updatedAt"),
            data.get("productKey"),
            data.get("deviceName"),
            data.get("c_re"),
            data.get("d_im"),
            data.get("x"),
            data.get("y"),
            data.get("distance_mm"),
            data.get("temp"),
            data.get("humi"),
            data.get("current_pos"),
            int(data.get("pos_valid")) if data.get("pos_valid") is not None else None,
            int(data.get("calib_source")) if data.get("calib_source") is not None else None,
            json.dumps(data.get("raw"), ensure_ascii=False),
        ),
    )
    db.commit()


def clear_sensor_data() -> None:
    if not settings.enable_db_write:
        return

    db = get_db()
    db.execute("DELETE FROM sensor_data")
    db.execute("DELETE FROM sqlite_sequence WHERE name='sensor_data'")
    db.commit()


def get_latest_from_db() -> dict[str, Any] | None:
    if not settings.enable_db_write:
        return None

    db = get_db()
    row = db.execute(
        """
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    raw_json = row["raw_json"]
    raw = None
    if raw_json:
        try:
            raw = json.loads(raw_json)
        except Exception:
            raw = None

    return {
        "productKey": row["product_key"],
        "deviceName": row["device_name"],
        "c_re": row["c_re"],
        "d_im": row["d_im"],
        "x": row["x"],
        "y": row["y"],
        "distance_mm": row["distance_mm"],
        "temp": row["temp"],
        "humi": row["humi"],
        "current_pos": row["current_pos"],
        "pos_valid": row["pos_valid"],
        "calib_source": row["calib_source"],
        "updatedAt": row["created_at"],
        "raw": raw,
    }


def get_history_from_db(limit: int = 200) -> dict[str, list[dict[str, Any]]]:
    if not settings.enable_db_write:
        return {}

    db = get_db()
    rows = db.execute(
        """
        SELECT created_at, distance_mm, c_re, d_im, x, y, temp, humi, current_pos
        FROM sensor_data
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    rows = list(reversed(rows))

    result: dict[str, list[dict[str, Any]]] = {
        "distance_mm": [],
        "c_re": [],
        "d_im": [],
        "x": [],
        "y": [],
        "temp": [],
        "humi": [],
        "current_pos": [],
    }

    for row in rows:
        t = row["created_at"]

        if row["distance_mm"] is not None:
            result["distance_mm"].append({"time": t, "value": row["distance_mm"]})
        if row["c_re"] is not None:
            result["c_re"].append({"time": t, "value": row["c_re"]})
        if row["d_im"] is not None:
            result["d_im"].append({"time": t, "value": row["d_im"]})
        if row["x"] is not None:
            result["x"].append({"time": t, "value": row["x"]})
        if row["y"] is not None:
            result["y"].append({"time": t, "value": row["y"]})
        if row["temp"] is not None:
            result["temp"].append({"time": t, "value": row["temp"]})
        if row["humi"] is not None:
            result["humi"].append({"time": t, "value": row["humi"]})
        if row["current_pos"] is not None:
            result["current_pos"].append({"time": t, "value": row["current_pos"]})

    return result


def close_db() -> None:
    global _db_conn
    if _db_conn is not None:
        _db_conn.close()
        _db_conn = None