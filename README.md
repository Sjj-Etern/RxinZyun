# 医院药品运输系统 (Hospital Medicine Delivery System)

一套面向医院内部场景的药品自动运输系统：药师在 HIS 端扫码复核 → 后端编排工作流 → 通过 ROS WebSocket 调度 1 号/2 号小车 → 控制 ESP32 电梯门禁跨楼层配送 → 大屏前端实时展示全程状态。

本仓库为**多项目组合（monorepo）**，共包含 **5 个子项目**。

---

## 系统架构

```
                 ┌──────────────┐   HTTP/MySQL    ┌──────────────────────────┐
 药师扫码 ─────▶ │  HIS         │ ──────────────▶ │  医院大屏后端 (FastAPI)    │
  (hospital/his/client) │ (Express+TS)│ 共享 hospital │ - 工作流编排          │
                 └──────────────┘   数据库         │  - 车1/车2 ROS 通信        │
                                                     │  - 电梯 TCP 控制          │
               ┌──────────────────┐                  │  - 摄像头/语音            │
               │ 医院大屏前端(Vue3)│ ◀── HTTP/SSE ──┤                           │
               └──────────────────┘                  └─────────────┬────────────┘
                                                                     │
            ┌──────────────────────────────────┬────────────────────┴───────┐
            ▼                                  ▼                            ▼
   ┌─────────────────┐              ┌──────────────────┐          ┌──────────────────┐
   │ 1 号小车 (ROS)   │  WebSocket   │ 2 号小车 (ROS)    │  TCP     │ ESP32 电梯门禁    │
   │ 192.168.51.16    │ ◀──────────▶ │ 192.168.51.43    │ ◀──────▶ │ (elevator_access  │
   │ :9090 rosbridge  │              │ :9090 rosbridge  │  10833   │  _control)       │
   └─────────────────┘              └──────────────────┘          └──────────────────┘
```

- **数据库**：MySQL `hospital` 库，HIS 与大屏后端共享同一数据库。
- **ROS 通信**：通过 rosbridge WebSocket（:9090）收发 `{op, topic, msg}` 信封格式消息。
- **电梯通信**：大屏后端 TCP 服务端 :10833，ESP32 作为客户端连接；UDP :10832 用于发现。
- **语音播报**：海康摄像头 ISAPI HTTP 接口。

---

## 子项目清单

### 1. `hospital/his` — HIS 系统（药师端）
药师信息系统的后端 + 扫码前端。

- **`hospital/his/server`** — HIS 后端
  - 技术栈：Node.js + Express + TypeScript + MySQL2 + JWT + bcrypt
  - 职责：处方/药品/追溯码管理、扫码状态机（pending → scanned_outbound → scanned_confirm）、节点 3 扫码复核完成检测并通知大屏后端触发 `pharmacist-success`。
  - 启动：
    ```bash
    cd hospital/his/server
    npm install
    npm run dev      # tsx watch，默认 :3001
    # 或 npm run build && npm start
    ```
  - 注：服务端带 `.integrity` 源码完整性校验，修改源码后需运行 `node scripts/generate-checksums.js <密码>` 重新生成校验清单。

- **`hospital/his/client`** — HIS 扫码前端
  - 技术栈：React 18 + Vite + TypeScript + html5-qrcode + echarts
  - 职责：摄像头扫码核验、药品追溯码出库/确认、操作记录展示。
  - 启动：
    ```bash
    cd hospital/his/client
    npm install
    npm run dev      # Vite，默认 :3002
    ```

### 2. `hospital_dashboard_backend` — 医院大屏后端
系统核心编排服务。

- 技术栈：Python + FastAPI + Uvicorn + pymysql + websockets
- 职责：
  - 连接 MySQL `hospital` 库（与 HIS 共享），提供工作流状态/处方进度 API；
  - `ros_listener`：监听车 1 ROS 状态（running-started / lift-arrive / nurse_arrive 等），驱动工作流节点流转；
  - `his_sender`：向车 1/车 2 ROS 发送药品坐标、pharmacist-success / lift-across / lift-open / nurse-success 等信号（连续发送直至收到回执）；
  - 电梯 ESP32 TCP 通信（开关门、go_floor、UDP 发现）；
  - 摄像头语音播报（ISAPI）。
- 启动：
  ```bash
  cd hospital_dashboard_backend
  pip install -r requirements.txt   # FastAPI/uvicorn/pymysql/websockets/pydantic-settings 等
  python app.py                      # 默认 :8080
  ```
- 配置：`.env`（**已排除上传**，参考 `.env.example`），含 MySQL、ROS、电梯、摄像头、延迟参数等。

### 3. `hospital_dashboard_frontend` — 医院大屏前端
医院大屏实时监控界面。

- 技术栈：Vue 3 + Vite + TypeScript
- 职责：实时场景图、摄像头视频流（优先实时、本地兜底）、工作流节点进度、处方运输状态展示。
- 启动：
  ```bash
  cd hospital_dashboard_frontend
  npm install
  npm run dev      # Vite，默认 :5173
  ```

### 4. `temperature_humidity_sensor` — ESP32 温湿度采集
环境温湿度采集并通过 WebSocket 上报。

- 技术栈：ESP-IDF（C），目标芯片 ESP32-S3（正点原子开发板）
- 目录：`temperature_humidity_sensor/dht11_demo/`（`main/main.c`、`wifi.c/h`、`ws_client.c/h`、`app_config.h`）
- 职责：连接 WiFi → 读取 DHT11 温湿度 → 经 WebSocket 客户端上报。
- 编译烧录（需 ESP-IDF v5.5.5）：
  ```bash
  cd temperature_humidity_sensor/dht11_demo
  idf.py build
  idf.py -p COMx flash monitor
  ```

### 5. `elevator_access_control` — ESP32 电梯门禁
电梯楼层控制与门禁。

- 技术栈：ESP-IDF（C），目标芯片 ESP32-S3（QFN56）
- 目录：`elevator_access_control/main/main.c` + `components/`、`CMakeLists.txt`、`partitions-16MiB.csv`、`sdkconfig`
- 职责：
  - UDP :10832 服务发现，TCP :10833 客户端自动重连（5 秒）；
  - 解析后端 JSON 命令（`open_door` / `close_door` / `go_floor` / `status`，含 `seq` 字段）；
  - 继电器控制楼层：继电器1 (GPIO9)→3 楼、继电器2 (GPIO10)→5 楼、继电器3 (GPIO3)→1 楼；
  - 全命令 SEND/RECV/ACK/DONE 日志，`go_floor` 先回 ACK 再异步执行（避免阻塞 TCP）。
- 编译烧录（需 ESP-IDF v5.5.5）：
  ```bash
  cd elevator_access_control
  idf.py build
  idf.py -p COM3 flash monitor
  ```

---

## 环境依赖

| 依赖 | 版本/说明 |
| --- | --- |
| Node.js | ≥ 18（HIS、大屏前端） |
| Python | ≥ 3.10（大屏后端） |
| ESP-IDF | v5.5.5（两个 ESP32 项目） |
| MySQL | 8.x（库 `hospital`，HIS 与后端共享） |
| ROS + rosbridge | rosbridge_server（:9090 WebSocket） |

---

## 通信端口速查

| 服务 | 地址/端口 |
| --- | --- |
| HIS 后端 | :3001 |
| 大屏后端 | :8080 |
| HIS 前端 | Vite 默认 :3002 |
| 车 1 / 车 2 ROS | 192.168.51.16 / .43 :9090 |
| 电梯 ESP32 TCP | :10833（后端为服务端） |
| 电梯 ESP32 UDP 发现 | :10832 |

---

## 配置与敏感文件说明

- 各项目的 `.env` 文件含数据库密码、摄像头密码、内网 IP 等敏感信息，**已通过 `.gitignore` 排除上传**；模板见 `hospital_dashboard_backend/.env.example`。
- `hospital/his/client` 的 `cert.pem` / `key.pem`（开发用 HTTPS 证书/私钥）同样已排除。
- 关键延迟/间隔参数均可于后端 `.env` 统一配置，例如：
  - `LIFT_ACROSS_DELAY`：电梯到达后发送跨楼信号延迟（秒）
  - `CAR2_SIGNAL_INTERVAL`：车 2 信号连续发送重发间隔（秒）
  - `PHARMACIST_SUCCESS_DELAY`：节点 3 扫码复核完成 → 发送 pharmacist-success 的延迟（秒）

---

## 分支说明

- `main`：已合并 `new_sjj` 与 `Combination_hospital`，作为当前统一主分支。
- `new_sjj`：HIS、旧版大屏、移动端和 ROS 辅助程序等历史项目线。
- `Combination_hospital`：包含 HIS、新版大屏后端/前端、DHT11 WebSocket 和电梯门禁的组合项目线。
