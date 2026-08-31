# 电梯门禁 IO 改版开发文档

> 更新时间：2026-08-30
> 范围：elevator_access_control 固件 + hospital_dashboard_backend 测试脚本
> 主题：继电器引脚重新分配 + 新增电源键 TCP 远程控制 + 业务楼层改为 2楼↔4楼

---

## 一、现状（本次改版已完成）

### 1.1 背景

- 原继电器绑定存在两处历史问题：
  - 继电器3（GPIO3）同时承担"开门键"和"1楼按钮"，功能复用冲突
  - 继电器4（GPIO13）与 SPI_MISO（LCD）撞脚，存在隐患
- 业务调整：电梯业务只涉及 **2楼和4楼**（车2在2楼进梯 → 运至4楼出梯），不再涉及原 1/3/5 楼
- 新需求：电梯"电源键"需支持后端 TCP `power` 命令远程触发
- 硬件已按新分配完成接线

### 1.2 新 IO 绑定表（已实现）

| 功能 | GPIO | 继电器编号 | 电气特性 | 状态 |
| --- | --- | --- | --- | --- |
| 2楼按钮 | IO9 | 继电器1 | 高电平吸合50ms | ✅ 已改 |
| 4楼按钮 | IO10 | 继电器2 | 高电平吸合50ms | ✅ 已改 |
| 开门键 | IO17 | 继电器3 | 高电平吸合50ms | ✅ 已改（原GPIO3） |
| 关门键 | IO18 | 继电器4 | 高电平吸合50ms | ✅ 已改（原GPIO13，消除SPI撞脚） |
| 电源键 | IO19 | 继电器5 | 高电平吸合50ms | ✅ 新增 |
| 温湿度DHT11 | IO20 | — | 单总线 | 不变 |

释放的引脚：GPIO3、GPIO13（空闲）。
1/3/5楼按钮未接线：`toFloor()` 中 relay=-1，跳过物理按键，仅红外移动（不影响流程）。

### 1.3 固件代码改动（已完成 + 编译通过）

| 文件 | 改动内容 |
| --- | --- |
| [relay.c:6-13](../elevator_access_control/components/BSP/RELAY/relay.c#L6-L13) | `relay_gpio_list` 重写为 5 路：2楼@9、4楼@10、开门@17、关门@18、电源@19 |
| [emission.c:65-71](../elevator_access_control/components/BSP/EMISSION/emission.c#L65-L71) | `toFloor()` switch 改映射：case 2→继电器1、case 4→继电器2，其余跳过按键 |
| [emission.c:176-188](../elevator_access_control/components/BSP/EMISSION/emission.c#L176-L188) | 新增 `power_press()`：继电器5(GPIO19)吸合50ms模拟按电源键 |
| [emission.h:67-69](../elevator_access_control/components/BSP/EMISSION/emission.h#L67-L69) | 声明 `power_press()` |
| [tcp_client.c:251-260](../elevator_access_control/components/BSP/WIFI/tcp_client.c#L251-L260) | 新增 `power` 命令分发：执行 power_press() 并回 ACK |

TCP 命令协议（现状全量）：

| 命令 | 功能 | ACK |
| --- | --- | --- |
| `open_door` | 继电器3(GPIO17)吸合50ms | ok |
| `close_door` | 继电器4(GPIO18)吸合50ms | ok |
| `go_floor` | 继电器按键(2楼/4楼) + 红外移动 | ok（先回ACK，移动异步） |
| `power` | **新增** 继电器5(GPIO19)吸合50ms | ok |
| `status` | 查楼层+温湿度 | ok |
| （主动上报） | `floor_arrived`：楼层移动真实完成上报 | — |

固件已用 ESP-IDF v5.5.5 编译通过（`build/elevator_access_control.bin`，app 分区占用 45%）。

### 1.4 测试脚本（已就绪，待硬件联调）

[test_elevator_new_io.py](../hospital_dashboard_backend/test_elevator_new_io.py)：独立 TCP 服务端测试脚本，不依赖后端业务。

```
测试项：
  1. TCP连通性(status)
  2. 开门 open_door   (GPIO17/继电器3)
  3. 关门 close_door  (GPIO18/继电器4)
  4. 去2楼 go_floor(2) (GPIO9/继电器1)   ← 校验 Floor_Num=2 + floor_arrived
  5. 去4楼 go_floor(4) (GPIO10/继电器2)  ← 校验 Floor_Num=4 + floor_arrived
  6. 电源 power       (GPIO19/继电器5)
```

运行方式（注意 ESP32 是 TCP 客户端，先停掉大屏后端再测）：

```
cd hospital_dashboard_backend
python test_elevator_new_io.py            # 默认监听 0.0.0.0:10833 等 ESP32 连入
python test_elevator_new_io.py --skip-power   # 跳过电源测试
```

---

## 二、开发方向（待办）

按优先级排序，测试跑通后逐项落地：

| # | 待办 | 说明 |
| --- | --- | --- |
| 1 | **烧录固件** | `idf.py flash`（bin 已生成）。烧录后 ESP32 重启自动 UDP 发现后端 |
| 2 | **运行 IO 测试脚本** | 验证 6 项全 PASS（重点听继电器咔哒声、看电梯实际动作） |
| 3 | **后端 .env 目标楼层改为 4** | `ELEVATOR_TARGET_FLOOR=5` → `4`（业务改为 2楼→4楼） |
| 4 | **后端新增 send_power()** | [elevator_control.py](../hospital_dashboard_backend/app/services/elevator_control.py) 增加 power 命令方法（若需要后端业务调电源） |
| 5 | **电梯初始楼层核对** | 固件 `Floor_Num` 初始为 1（[emission.c:40](../elevator_access_control/components/BSP/EMISSION/emission.c#L40)），业务改为 2楼↔4楼后需确认初始楼层语义（如电梯待命层是 2 楼，建议初始值改 2 或开机 go_floor(2)） |
| 6 | **电源键业务时机** | 明确后端在什么节点调 power（如系统启动自检时开电梯电源？流程结束后关电源？） |
| 7 | **回归测试** | 走完整车2配送流程：lift-arrive → 开门 → lift-across → 关门 → go_floor(4) → floor_arrived → lift-open → 护士扫码 → nurse-success |

---

## 三、进度总览

```
[██████████░░░░░░░░░░] 50%

✅ 完成：
  □ 硬件接线（用户完成）
  □ 固件：新 IO 绑定（5路继电器）
  □ 固件：power 命令 + power_press()
  □ 固件：编译通过（v5.5.5，bin 已生成）
  □ 测试脚本 test_elevator_new_io.py

⬜ 待办：
  □ 烧录固件 + 硬件联调（用户执行）
  □ 后端 .env 目标楼层 5→4
  □ 后端 send_power()（视业务需要）
  □ Floor_Num 初始楼层语义确认
  □ 完整业务流程回归测试
```

---

## 四、附：编译环境备忘（Windows）

本项目实际使用 **ESP-IDF v5.5.5**（D:\SoftWare\Espressif），不是 C:\esp 下的 v6.0.1（曾误用导致 build 缓存冲突）。

```powershell
$tools="D:\SoftWare\Espressif\tools"
$env:IDF_PATH="D:\SoftWare\Espressif\frameworks\esp-idf-v5.5.5"
$env:IDF_TOOLS_PATH="D:\SoftWare\Espressif"
$env:PATH="$tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;$tools\cmake\3.30.2\bin;$tools\ninja\1.12.1;$env:PATH"
& "D:\SoftWare\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe" "D:\SoftWare\Espressif\frameworks\esp-idf-v5.5.5\tools\idf.py" build
```

或直接在 ESP-IDF 5.5.5 PowerShell 快捷方式里 `idf.py build flash`。
