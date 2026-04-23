from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque, Dict

from .config import settings

HISTORY_KEYS = [
    "distance_mm",
    "c_re",
    "d_im",
    "x",
    "y",
    "temp",
    "humi",
    "current_pos",
]

latest_state: Dict[str, Any] = {
    "productKey": None,
    "deviceName": None,
    "c_re": None,
    "d_im": None,
    "x": None,
    "y": None,
    "distance_mm": None,
    "temp": None,
    "humi": None,
    "current_pos": None,
    "pos_valid": None,
    "calib_source": None,
    "updatedAt": None,
    "raw": None,
}

history_cache: Dict[str, Deque[dict[str, int | float]]] = {
    key: deque(maxlen=settings.history_limit) for key in HISTORY_KEYS
}

payload_queue: asyncio.Queue[dict[str, Any]] | None = None

last_msg_ts = 0
last_disconnect_ts = 0
