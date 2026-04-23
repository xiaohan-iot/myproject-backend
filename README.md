# Gap Monitor Backend

面向你的 **水电 / 风电气隙在线监测系统** 的 FastAPI 后端工程。

这个后端已经包含：

- 阿里云 IoT 平台 **AMQP 服务端订阅** 消费
- WebSocket 实时推送 `/ws/device`
- 最新数据接口 `/api/device/latest`
- 历史数据接口 `/api/device/history`
- 健康检查接口 `/api/health`
- 前端导航配置接口 `/api/navigation`
- 可选 SQLite 落盘（默认关闭）
- ACK 前移：**入队成功后立刻 ACK**
- AMQP 断线自动重连

## 一、目录结构

```text
gap_monitor_backend
├─ app
│  ├─ __init__.py
│  ├─ amqp_worker.py
│  ├─ config.py
│  ├─ db.py
│  ├─ main.py
│  ├─ models.py
│  ├─ normalizer.py
│  ├─ state.py
│  └─ websocket_manager.py
├─ .env.example
├─ README.md
└─ requirements.txt
```

## 二、安装依赖

```bash
pip install -r requirements.txt
```

## 三、配置环境变量

把 `.env.example` 复制成 `.env`，然后填入你自己的阿里云参数：

```bash
cp .env .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

重点配置：

- `AMQP_HOST`
- `CONSUMER_GROUP_ID`
- `AMQP_CLIENT_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`

## 四、启动

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**不要使用 `--reload` 做 AMQP 长连调试。**

## 五、接口说明

### 1. 健康检查

`GET /api/health`

返回：

```json
{
  "ok": true,
  "amqp_enabled": true,
  "amqp_connected": true,
  "db_enabled": false,
  "queue_size": 0,
  "last_msg_ts": 1776840000000,
  "last_msg_ago_ms": 1200,
  "last_disconnect_ts": null,
  "last_disconnect_ago_ms": null,
  "time": 1776840001200
}
```

### 2. 最新数据

`GET /api/device/latest`

### 3. 历史数据

`GET /api/device/history?limit=200`

### 4. 前端导航配置

`GET /api/navigation`

给前端侧边栏用。

### 5. WebSocket

`/ws/device`

收到新数据后会推送：

```json
{
  "type": "device_update",
  "data": { ... }
}
```

## 六、当前支持的字段

后端默认解析这些字段：

- `distance_mm`
- `c_re`
- `d_im`
- `x`
- `y`
- `temp`
- `humi`
- `current_pos`
- `pos_valid`
- `calib_source`

支持以下阿里云上报格式：

- `payload["items"][field]["value"]`
- `payload["params"][field]`
- `payload[field]`

## 七、建议

1. 给这个后端单独使用一个消费组。
2. `AMQP_CLIENT_ID` 保持唯一。
3. 调试阶段建议 `ENABLE_DB_WRITE=0`。
4. 前端历史曲线建议低频拉取，比如 5~10 秒一次。

## 八、停止服务

建议使用终端里的 `Ctrl + C` 正常退出，不要优先用强杀。
