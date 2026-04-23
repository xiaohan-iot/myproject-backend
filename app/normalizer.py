from __future__ import annotations

import time
from typing import Any

from .state import HISTORY_KEYS, history_cache


def get_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        direct = payload.get(key)
        if isinstance(direct, dict) and "value" in direct:
            return direct.get("value")
        if direct is not None and not isinstance(direct, dict):
            return direct

        for container_key in ("items", "params", "data"):
            container = payload.get(container_key)
            if not isinstance(container, dict):
                continue
            item = container.get(key)
            if isinstance(item, dict) and "value" in item:
                return item.get("value")
            if item is not None:
                return item
    return None


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    updated_at = payload.get("gmtCreate") or int(time.time() * 1000)

    return {
        "productKey": payload.get("productKey"),
        "deviceName": payload.get("deviceName"),
        "c_re": get_value(payload, "c_re"),
        "d_im": get_value(payload, "d_im"),
        "x": get_value(payload, "x"),
        "y": get_value(payload, "y"),
        "distance_mm": get_value(payload, "distance_mm"),
        "temp": get_value(payload, "temp"),
        "humi": get_value(payload, "humi"),
        "current_pos": get_value(payload, "current_pos"),
        "pos_valid": get_value(payload, "pos_valid"),
        "calib_source": get_value(payload, "calib_source"),
        "updatedAt": updated_at,
        "raw": payload,
    }


def append_history(data: dict[str, Any]) -> None:
    ts = data.get("updatedAt") or int(time.time() * 1000)
    for key in HISTORY_KEYS:
        value = data.get(key)
        if value is not None:
            history_cache[key].append({"time": ts, "value": value})
