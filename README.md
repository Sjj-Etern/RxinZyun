# 医院药品运输系统 (Hospital Medicine Delivery System)

一套面向医院内部场景的药品自动运输系统：医生在 HIS 端开具处方 → 后端编排工作流 → 通过 ROS WebSocket 调度 1 号/2 号小车取药送药 → 控制 ESP32 电梯门禁完成跨楼层配送 → 大屏前端实时展示全程 15 节点运输状态。

本仓库为**多项目组合（monorepo）**，共包含 **5 个子项目**。

---

## 系统架构

```
                 ┌──────────────┐   HTTP/MySQL    ┌──────────────────────────┐
 医生开方 ─────▶ │  HIS         │ ──────────────▶ │  医院大屏后端 (FastAPI)    │
 药师扫码        │ (Express+TS) │   共享 hospital │  - 工作流编排（8步电梯流程） │
  (hospital/his) └──────────────┘      数据库      │  - 车1/车2 ROS 通信        │
                                                 │  - 电梯 TCP 控制          │
               ┌──────────────────┐              │  - 摄像头代理/语音播报      │
               │ 医院大屏前端(Vue3)│ ◀── HTTP/SSE ─┤                           │
               │  15节点时间线大屏  │              └─────────────┬────────────┘
               └──────────────────┘                            │
            ┌────────────────────────────┬─────────────────────┴───────┐
            ▼ WebSocket(rosbridge :9090)  ▼ WebSocket(rosbridge :9090)   ▼ TCP :10833
   ┌─────────────────┐          ┌──────────────────┐          ┌──────────────────┐
   │ 1 号小车 (ROS)   │          │ 2 号小车 (ROS)    │          │ ESP32 电梯门禁    │
   │ 取药车           │          │ 送药车(跨梯运输)   │          │ UDP发现+TCP长连接  │
   │ 192.168.51.16   │          │ 192.168.51.43    │          │ 继电器模拟按键     │
   │ :9090            │          │ :9090            │          │ +红外楼层移动     │
   └─────────────────┘          └──────────────────┘          └──────────────────┘
```

- **数据库**：MySQL `hospital` 库，HIS 与大屏后端共享同一数据库。
- **ROS 通信**：通过 rosbridge WebSocket（:9090）收发 `{op, topic, msg}` 信封格式消息。
- **电梯通信**：大屏后端为 TCP 服务端 :10833，ESP32 作为客户端连接；UDP :10832 用于设备发现。
- **语音播报**：音频服务 + 海康摄像头 ISAPI HTTP 接口。

### 核心业务流（车2 跨楼层配送信号链）

```
处方创建(approved) → 后端取处方发坐标给车1
→ 车1 取药(节点1-4) → 节点3扫码出库 → HIS通知后端 → ①pharmacist-success连发(回执停)
→ 车2 抵达电梯 lift-arrive → 停① → 电梯TCP开门 → ②lift-across连发
→ 车2 进梯 → 电梯TCP关门 → go_floor → ESP32上报floor_arrived(真实反馈)
→ ③lift-open连发 → 节点4扫码确认 → HIS通知后端 → ④nurse-success×3
→ 车2 nurse_arrive → 语音"药物已送达请您确认" → 处方置dispensed
```

---

## 子项目清单

### 1. `hospital/his` — HIS 系统（医生/药师端）

HIS 信息系统的后端 + Web 前端。

**配置（重要）**：新版采用集中式 `.env` 配置，需先复制模板：

```bash
cd hospital/his
cp .env.example .env    # 然后填写 MySQL 连接、JWT 密钥等约 30 个变量，缺失将拒绝启动
```

- **`hospital/his/server`** — HIS 后端
  - 技术栈：Node.js + Express + TypeScript + MySQL2 + JWT + bcrypt
  - 职责：处方/药品/患者/追溯码管理、发药配送（选机器人+建配送记录）、扫码状态机（pending → scanned_outbound → scanned_confirm）、节点 3 扫码出库完成检测并通知大屏后端触发 `pharmacist-success`、节点 4 扫码确认完成检测并通知触发 `nurse-success`。
  - 处方创建即为 `approved` 状态（无药师审核环节），供大屏后端取送。
  - 启动：
    ```bash
    cd hospital/his/server
    npm install
    npm run dev      # tsx watch，默认 :3001
    # 或 npm run build && npm start
    ```

- **`hospital/his/client`** — HIS 前端
  - 技术栈：React 18 + Vite + TypeScript + html5-qrcode + echarts
  - 职责：医生开方、药房管理、扫码核验（追溯码出库/确认）、配送记录、机器人管理。
  - 启动：
    ```bash
    cd hospital/his/client
    npm install
    npm run dev      # Vite，默认 :3002（读 hospital/his/.env）
    ```

### 2. `hospital_dashboard_backend` — 医院大屏后端

系统核心编排服务。

- 技术栈：Python + FastAPI + Uvicorn + pymysql + websockets
- 职责：
  - 连接 MySQL `hospital` 库（与 HIS 共享），提供工作流状态/处方进度/15 节点时间线 API；
  - `ros_listener`：监听车 1/车 2 ROS 状态（running-started / lift-arrive / nurse_arrive 等），驱动工作流节点流转与电梯 8 步编排；
  - `his_sender`：向车 1/车 2 发送药品坐标与控制信号（pharmacist-success / lift-across / lift-open / nurse-success，采用"连续发送 + 回执驱动停止"模式）；
  - `elevator_control`：电梯 ESP32 TCP 通信（UDP 发现、开关门、go_floor、floor_arrived 真实到达反馈）；
  - 摄像头代理（车 POV 流转发、走廊 RTSP 转 MJPEG）与语音播报；
  - `workflow_event_service`：15 节点事件流水记录（时间线数据源）。
- 启动：
  ```bash
  cd hospital_dashboard_backend
  pip install -r requirements.txt
  python app.py                      # 默认 :8080
  ```
- 配置：`.env`（含 MySQL、ROS、电梯、摄像头、信号延迟等，关键项见下表）。
- 接口文档：启动后访问 `http://127.0.0.1:8080/docs`（Swagger UI）。
- 辅助工具：`mock_rosbridge.py`（无车调试）、`test_elevator_*.py`（电梯联调）、`log_summarizer.py`（日志摘要）。

### 3. `hospital_dashboard_frontend` — 医院大屏前端

医院大屏实时监控界面。

- 技术栈：Vue 3 + Vite + TypeScript
- 职责：
  - 实时场景图（CAD 布局 + 地图，三态模式、坐标转换、实时轮询）；
  - 摄像头视频流（车 POV1/POV2 + 走廊监控，实时流优先、本地视频兜底）；
  - 处方运输 15 节点竖向时间线（3 阶段：处方流转 / 跨梯运输 / 交付确认，数据来自事件流水）。
- 启动：
  ```bash
  cd hospital_dashboard_frontend
  npm install
  npm run dev      # Vite，默认 :5174（VITE_PORT 可配）
  npm run build    # 构建部署
  ```

### 4. `elevator_access_control` — ESP32 电梯门禁

电梯楼层控制与门禁（IO 改版：业务楼层为 2 楼 ↔ 4 楼）。

- 技术栈：ESP-IDF v5.5.5（C），目标芯片 ESP32-S3（QFN56，16MB Flash）
- 硬件绑定（当前）：

  | 功能 | GPIO | 继电器 | 说明 |
  | --- | --- | --- | --- |
  | 2 楼按钮 | IO9 | 继电器1 | 吸合 50ms 模拟按键 |
  | 4 楼按钮 | IO10 | 继电器2 | 吸合 50ms 模拟按键 |
  | 开门键 | IO17 | 继电器3 | 吸合 50ms 模拟按键 |
  | 关门键 | IO18 | 继电器4 | 吸合 50ms 模拟按键 |
  | 电源键 | IO19 | 继电器5 | TCP `power` 命令远程触发 |
  | DHT11 温湿度 | IO20 | — | 电梯井环境采集 |
  | 红外发射 | IO8 | — | RMT 模拟轿厢楼层键（上下行/停止） |

- 职责：
  - UDP :10832 广播发现，TCP :10833 客户端连接后端（断线 5 秒重连）；
  - 解析后端 JSON 命令（`open_door` / `close_door` / `go_floor` / `power` / `status`，含 `seq` 字段，均回 ACK）；
  - `go_floor`：先回 ACK 再异步执行（继电器按键 + 红外楼层移动），移动完成主动上报 `floor_arrived`（真实反馈，替代后端估算）；
  - LCD 显示楼层/温湿度，全命令 SEND/RECV/ACK 日志。
- 编译烧录（需 ESP-IDF v5.5.5，注意勿用其他版本环境）：
  ```bash
  cd elevator_access_control
  idf.py build
  idf.py -p COM3 flash monitor
  ```

### 5. `temperature_humidity_sensor` — ESP32 温湿度采集

环境温湿度采集并通过 WebSocket 上报。

- 技术栈：ESP-IDF（C），目标芯片 ESP32-S3
- 目录：`temperature_humidity_sensor/dht11_demo/`（`main/main.c`、`wifi.c/h`、`ws_client.c/h`、`app_config.h`）
- 职责：连接 WiFi → 读取 DHT11 温湿度 → 经 WebSocket 客户端上报大屏后端。
- 编译烧录（需 ESP-IDF v5.5.5）：
  ```bash
  cd temperature_humidity_sensor/dht11_demo
  idf.py build
  idf.py -p COMx flash monitor
  ```

---

## 环境依赖

| 依赖 | 版本/说明 |
| --- | --- |
| Node.js | ≥ 18（HIS 前后端、大屏前端） |
| Python | ≥ 3.10（大屏后端） |
| ESP-IDF | v5.5.5（两个 ESP32 项目，路径 D:\SoftWare\Espressif） |
| MySQL | 8.x（库 `hospital`，HIS 与后端共享） |
| ROS + rosbridge | rosbridge_server（:9090 WebSocket），车 1/车 2 车载 |

## 推荐启动顺序

1. **MySQL**（导入 `hospital/his/server/db/` 下的建库/备份脚本）
2. **大屏后端**：`python app.py`（等待电梯 ESP32 UDP 发现并连入 :10833）
3. **HIS 后端**：`npm run dev`（:3001）
4. **HIS 前端**：`npm run dev`（:3002）
5. **大屏前端**：`npm run dev`（:5174）
6. 小车与 ESP32 上电（自动发现/重连）

---

## 通信端口速查

| 服务 | 地址/端口 |
| --- | --- |
| HIS 后端 | :3001 |
| HIS 前端 | :3002（Vite） |
| 大屏后端 | :8080（Swagger：/docs） |
| 大屏前端 | :5174（Vite，VITE_PORT 可配） |
| 车 1 / 车 2 ROS | 192.168.51.16 / .43 :9090（rosbridge） |
| 电梯 ESP32 TCP | :10833（后端为服务端，ESP32 为客户端） |
| 电梯 ESP32 UDP 发现 | :10832（广播发现 → 回 TCP 地址） |

## 关键配置项（hospital_dashboard_backend/.env）

| 变量 | 说明 |
| --- | --- |
| `ELEVATOR_TARGET_FLOOR` | 电梯目标楼层（跨楼层运输终点） |
| `ELEVATOR_FLOOR_ARRIVE_TIMEOUT` | 等待 ESP32 楼层到达上报的超时兜底（默认 20s） |
| `LIFT_ACROSS_DELAY` | 电梯开门后发跨楼信号前等待车 2 进梯的时长（默认 60s） |
| `CAR2_SIGNAL_INTERVAL` | 车 2 信号连续发送重发间隔 |
| `MEDICINE_SEND_MAX_ATTEMPTS` | 车 1 药品 start/running 重发上限（默认 15 次，超限放弃本处方） |
| `PHARMACIST_SUCCESS_DELAY` | 节点 3 扫码完成 → 发送 pharmacist-success 的延迟 |
| `ROBOT1_HOST/PORT`、`ROBOT2_HOST/PORT` | 两车 rosbridge 地址（车 1 摄像头 :8080 webvideo_server） |

HIS 配置见 `hospital/his/.env.example`（MySQL、JWT、外呼服务等约 30 项）。

---

## 配置与敏感文件说明

- 各项目的 `.env` 文件含数据库密码、摄像头密码、内网 IP 等敏感信息，**已通过 `.gitignore` 排除上传**。
- 模板：`hospital/his/.env.example`；大屏后端 `.env` 参考上文关键配置项。
- `hospital/his/client` 的 `cert.pem` / `key.pem`（开发用 HTTPS 证书/私钥）同样已排除。

## 数据库与备份

- 建库脚本/完整备份：`hospital/his/server/db/`（hospital_full_backup.sql、renxinzhiyun.sql）
- 大屏流程状态与 15 节点事件统一写入 MySQL `hospital` 库；服务启动时自动创建 `prescription_workflow_state` 与 `workflow_events`。
- 本地 SQLite `app.db` 仅作为历史备份，不参与运行时读写；生产数据备份文件不纳入仓库。

## 项目内文档索引

| 文档 | 内容 |
| --- | --- |
| `markdown/电梯IO改版开发文档.md` | 电梯继电器 IO 改版（现状/方向/进度） |
| `hospital_dashboard_backend/markdown/车2_ROS通信文档.md` | 车 2 四信号收发与 8 步电梯编排 |
| `hospital_dashboard_backend/markdown/电梯功能测试报告.md` | 电梯功能测试记录 |
| `hospital/his/TECHNICAL_DOCUMENTATION.md` | HIS 技术文档 |
| `temperature_humidity_sensor/dht11_demo/UPDATE_LOG.md` | 温湿度传感器更新日志 |

---

## 分支说明

- `main`：已合并 `new_sjj` 与 `Combination_hospital`，作为当前统一主分支。
- `new_sjj`：HIS、旧版大屏、移动端和 ROS 辅助程序等历史项目线。
- `Combination_hospital`：包含 HIS、新版大屏后端/前端、DHT11 WebSocket 和电梯门禁的组合项目线。
