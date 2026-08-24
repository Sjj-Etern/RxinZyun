# 更新日志 (UPDATE LOG)

> 项目：正点原子 ESP32-S3 + DHT11 温湿度上报
> 目标：脱离 USB 数据线，通过 WiFi + WebSocket 向后端上报温湿度数据

---

## [v0.2.3] 2026-07-31 —— 核心修复：显式指定传输类型为 TCP

### 一、问题现象（持续）

v0.2.2 修改后仍然报错：
```
E (11830) esp-tls: [sock=54] select() timeout
E (11830) transport_ws: Error connecting to host 192.168.1.103:8080
E (11830) websocket_client: esp_transport_connect() failed with -1,
          transport_error=ESP_ERR_ESP_TLS_CONNECTION_TIMEOUT
```

### 二、根因

`esp_websocket_client` 在 ESP-IDF v5.5.5 + managed component v1.8.0 中，**即使 URI 是 `ws://` 且设置了 TLS 相关字段为 NULL，底层仍可能默认走 TLS 路径**。

原因在于：没有显式设置 `.transport` 字段，导致内部传输类型判定异常。

### 三、修复内容

| 文件 | 改动 |
|------|------|
| `main/ws_client.c` | 添加 `.transport = WEBSOCKET_TRANSPORT_OVER_TCP` 强制使用明文 TCP |

### 四、关键代码

```c
esp_websocket_client_config_t ws_cfg = {
    .uri = uri,
    .transport = WEBSOCKET_TRANSPORT_OVER_TCP,  // ← 核心修复：强制明文 TCP
    // ...
};
```

### 五、验证

重新编译烧录：
```powershell
idf.py build flash monitor
```

预期成功输出：
```
I (xxx) WS_CLIENT: WebSocket connected
I (xxx) APP: [CB] WebSocket UP
```

---

## [v0.2.2] 2026-07-31 —— 修复 WebSocket 连接超时（显式禁用 TLS）

### 一、问题现象

后端服务已监听 `0.0.0.0:8080`，防火墙已放行，本机 test.py 用 `ws://192.168.1.103:8080` 能连上，但 **ESP32 始终连接超时**：

```
E (11840) esp-tls: [sock=54] select() timeout
E (11840) transport_ws: Error connecting to host 192.168.1.103:8080
E (11840) websocket_client: esp_transport_connect() failed with -1,
          transport_error=ESP_ERR_ESP_TLS_CONNECTION_TIMEOUT, errno=119
```

### 二、根因

虽然 URI 是 `ws://`（明文），但 `esp_websocket_client` 在 IDF v5.5.5 中**默认仍可能触发 TLS 路径**，导致 `esp-tls` 模块尝试 TLS 握手并 10 秒超时。

### 三、修复内容

| 文件 | 改动 |
|------|------|
| `main/ws_client.c` | 在 `ws_client_init` 中显式禁用 TLS：`use_global_ca_store=false`、`cert_pem=NULL`、`client_cert=NULL`、`client_key=NULL`、`skip_cert_common_name_check=true`；增加 `user_agent`、`ping_interval_ms=0` |
| `main/ws_client.c` | `ws_send_sensor_data` 未连接时静默返回（不再每 2 秒打 warning）；发送超时改为 1 秒（避免死等） |
| `main/main.c` | WS 发送返回 `ESP_ERR_INVALID_STATE` 时不打 warning（避免刷屏） |

### 四、验证

重新编译烧录：

```powershell
idf.py build flash monitor
```

预期输出（连接成功）：
```
I (xxx) WS_CLIENT: WebSocket connected
I (xxx) APP: [CB] WebSocket UP
```

---

## [v0.2.1] 2026-07-31 —— 修复编译错误（缺失 stdbool.h）

### 一、问题现象

执行 `idf.py build` 时编译失败，报错：

```
wifi.h:13:34: error: unknown type name 'bool'
ws_client.h:13:32: error: unknown type name 'bool'
note: 'bool' is defined in header '<stdbool.h>'; this is probably fixable by adding '#include <stdbool.h>'
```

### 二、根因

`wifi.h` 与 `ws_client.h` 中使用了 `bool` 类型（在回调函数签名和返回值中），但两个头文件都没有包含 `<stdbool.h>`。C 语言中 `bool` 不是原生关键字，必须通过 `<stdbool.h>` 引入。

### 三、修复内容

| 文件 | 改动 |
|------|------|
| `main/wifi.h` | 在 `#include "esp_err.h"` 前增加 `#include <stdbool.h>` |
| `main/ws_client.h` | 在 `#include "esp_err.h"` 前增加 `#include <stdbool.h>` |

### 四、验证

修复后请重新编译：

```powershell
idf.py build
```

预期可正常通过编译（除非另有问题）。

---

## [v0.2.0] 2026-07-31 —— 接入 WiFi + WebSocket（后端待对接）

### 一、本次更新概述

在原有「USB 串口上报」基础上，新增 **WiFi STA** 与 **WebSocket 客户端** 两个模块，使设备能够脱离 USB 数据线、通过 WiFi 联网向后端 WebSocket 服务上报温湿度数据。

> ⚠️ 后端 WebSocket 服务端尚未开发，当前固件已可**烧录测试**：
> - WiFi 模块会尝试连接 `app_config.h` 中配置的路由器；
> - WebSocket 模块会尝试连接占位地址，因无服务端会自动重试（不会卡死）；
> - **串口仍保留 `[SENSOR_DATA]{...}` 输出**，后端未就绪时也能通过串口监控数据。

### 二、文件变更明细

| 文件 | 操作 | 说明 |
|------|------|------|
| `main/app_config.h` | 修改 | 更新 WS URL 占位为 `ws://192.168.1.100:8080/api/dht11/wifi`，补充使用说明注释 |
| `main/CMakeLists.txt` | 修改 | 新增 `wifi.c`、`ws_client.c` 源文件，新增 `esp_wifi`、`esp_event`、`esp_netif`、`nvs_flash`、`esp_websocket_client`、`esp_timer` 依赖 |
| `main/main.c` | 修改 | 接入 WiFi / WebSocket 初始化与状态回调，主循环在串口输出基础上增加 `ws_send_sensor_data()` 上报 |

> 说明：`wifi.h/.c`、`ws_client.h/.c`、`idf_component.yml` 为上一轮已新建文件，本次未改动。

### 三、main.c 改造要点

1. **启动流程**
   - `dht11_init()` → `wifi_register_callback()` / `ws_register_callback()` → `wifi_init_sta()`（阻塞等 IP，超时 30s）→ `ws_client_init()` → 进入主循环。
2. **主循环（每 `APP_REPORT_INTERVAL_MS` = 2000ms）**
   - 读取 DHT11 → `printf("[SENSOR_DATA]...")`（保留，便于调试）→ `ws_send_sensor_data(temp, humi, rssi)`（WebSocket 上报）。
3. **健壮性**
   - WiFi 连接失败不会卡死，传感器循环继续运行；
   - WebSocket 未连接时 `ws_send_sensor_data()` 返回 `ESP_ERR_INVALID_STATE`，仅打印 warning 不阻塞；
   - WiFi / WebSocket 状态变化通过回调在串口打印 `[CB] ...`。

### 四、上报数据格式（JSON）

```json
{"temp":30,"humi":70}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `temp` | uint8 | 温度（℃），DHT11 整数值 |
| `humi` | uint8 | 湿度（%），DHT11 整数值 |

> 📌 后端开发 WebSocket 服务端时，请按此格式解析。

### 五、烧录前必做配置

打开 `main/app_config.h`，按实际环境修改以下三项：

```c
#define APP_WIFI_SSID         "Your_WIFI_SSID"      // ← 改成你的 WiFi 名
#define APP_WIFI_PASSWORD     "Your_WIFI_PASSWORD"  // ← 改成你的 WiFi 密码
#define APP_WS_URL            "ws://192.168.1.100:8080/api/dht11/wifi"  // ← 后端就绪后改
```

> ⚠️ **重要提醒**：
> - ESP32 不能使用 `127.0.0.1`（那是设备自身回环），必须使用**后端服务所在 PC 的局域网 IP**（如 `192.168.x.x`）。
> - 后端就绪前，WS URL 保持占位即可，固件仍可正常烧录运行，仅 WS 会重试失败。

### 六、烧录测试步骤

```bash
# 1. 设置目标芯片
idf.py set-target esp32s3

# 2. 编译
idf.py build

# 3. 烧录并监控（USB 连接阶段）
idf.py -p COM3 flash monitor
```

### 七、预期串口输出（后端未就绪时）

```
========== DHT11 + WiFi + WebSocket Started ==========
Device ID : esp32s3_dht11_01
WS URL    : ws://192.168.1.100:8080/api/dht11/wifi
Interval  : 2000 ms
I (xxxx) WIFI: WiFi started, connecting to AP...
I (xxxx) WIFI: Got IP: 192.168.1.50
I (xxxx) APP: [CB] WiFi UP, RSSI=-55 dBm
W (xxxx) WS_CLIENT: WebSocket disconnected
W (xxxx) APP: [CB] WebSocket DOWN (will auto-reconnect)
[SENSOR_DATA]{"temp":30,"humi":70}
W (xxxx) APP: WS send skipped: ESP_ERR_INVALID_STATE
...
```

> ✅ 若看到 WiFi UP 和 `[SENSOR_DATA]` 周期输出，即说明固件工作正常。WebSocket 在后端就绪后会自动连上并停止报错。

### 八、后续待办

- [ ] 后端开发 WebSocket 服务端（监听 `/api/dht11/wifi`）
- [ ] 后端就绪后，替换 `APP_WS_URL` 为真实地址
- [ ] （可选）接入 SNTP 同步网络时间，使 `ts` 为绝对时间戳
- [ ] （可选）量产阶段改用 SmartConfig / AP 配网，避免硬编码 WiFi 凭据

---

## [v0.1.0] 2026-07-31 —— 初始框架搭建

### 新增文件

| 文件 | 说明 |
|------|------|
| `main/app_config.h` | 集中配置：WiFi、WebSocket、设备ID、上报周期等 |
| `main/wifi.h` | WiFi STA 模块接口声明 |
| `main/wifi.c` | WiFi STA 实现：事件处理、自动重连、IP 获取、RSSI 查询 |
| `main/ws_client.h` | WebSocket 客户端接口声明 |
| `main/ws_client.c` | WebSocket 实现：事件处理、JSON 构造、数据发送 |
| `main/idf_component.yml` | 组件依赖：声明 `espressif/esp_websocket_client` |

### 功能

- 提供 WiFi STA 连接能力（WPA2-PSK，自动重连）
- 提供 WebSocket 客户端能力（自动重连，状态回调）
- 统一配置入口 `app_config.h`
