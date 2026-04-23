from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DeviceLatest(BaseModel):
    productKey: Optional[str] = None
    deviceName: Optional[str] = None
    c_re: Optional[float] = None
    d_im: Optional[float] = None
    x: Optional[float] = None
    y: Optional[float] = None
    distance_mm: Optional[float] = None
    temp: Optional[float] = None
    humi: Optional[float] = None
    current_pos: Optional[int] = None
    pos_valid: Optional[int] = None
    calib_source: Optional[int] = None
    updatedAt: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


class HistoryPoint(BaseModel):
    time: int
    value: float | int


class HealthResponse(BaseModel):
    ok: bool
    amqp_enabled: bool
    amqp_connected: bool
    db_enabled: bool
    queue_size: int
    last_msg_ts: Optional[int]
    last_msg_ago_ms: Optional[int]
    last_disconnect_ts: Optional[int]
    last_disconnect_ago_ms: Optional[int]
    time: int


class NavigationChild(BaseModel):
    key: str
    title: str


class NavigationMenu(BaseModel):
    key: str
    title: str
    icon: str
    expanded: bool
    children: List[NavigationChild]
