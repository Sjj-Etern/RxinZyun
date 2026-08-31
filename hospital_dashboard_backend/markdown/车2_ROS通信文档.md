# 系统与 ROS 车2 通信文档

> 更新日期：2026-08-30（依据当前代码 `his_sender.py` / `ros_listener.py` / `.env` 实际实现核对）

## 一、连接配置

| 项 | 值 | 配置来源 |
|----|-----|---------|
| 连接地址 | `ws://192.168.51.16:9090` | `CAR2_WS_HOST` / `CAR2_WS_PORT` |
| 系统订阅 Topic | `/car02_pub`（`std_msgs/String`） | `CAR2_TOPIC` |
| 系统发布 Topic | `/car02_rxzy_msg`（`his_sub`） | `CAR2_SEND_TOPIC` / `CAR2_SEND_MSG_TYPE` |
| 断线重连 | 每 `ROS_CHECK_INTERVAL=30` 秒 | `.env` |

---

## 二、收发职责

| 角色 | 订阅 | 发布 |
|------|------|------|
| 系统（后端） | `/car02_pub` | `/car02_rxzy_msg` |
| 车2 ROS | `/car02_rxzy_msg` | `/car02_pub` |

---

## 三、通信流程（4 信号 + 8 步电梯编排）

### 3.1 信号总览

4 个系统 → 车2 信号均为**连续发送**模式：每 `CAR2_SIGNAL_INTERVAL=2` 秒重发一次，直到收到对应回执（回执驱动停止）或被下一个信号切换。**系统侧无超时保护**。

```
① 系统 → 车2:  {prescription_code}_pharmacist-success   连发，收到 lift-arrive 停
② 车2 → 系统:  {prescription_code}_lift-arrive
③ 系统 → 车2:  {prescription_code}_lift-across           连发，被 lift-open 启动时切换停
④ 延迟 ELEVATOR_ACROSS_TO_GO_FLOOR_DELAY 秒（车2进电梯，串行间隔，可配置）
⑤ 电梯硬件:    关门 → 查层 → go_floor（去目标楼层）
⑥ ESP32 → 系统: {"type":"floor_arrived","floor":4}      楼层真实到达上报（20s 超时兜底）
⑥′ 电梯硬件:   到达4楼后再次 open_door（到站开门，车2 出梯用）
⑦ 系统 → 车2:  {prescription_code}_lift-open             连发，HIS 节点4 扫码确认后停
⑧ 车2 → 系统:  {prescription_code}_nurse_arrive
⑨ 系统 → 车2:  {prescription_code}_nurse-success         固定发 3 次自动停
```

### 3.2 lift-arrive 触发的完整编排（ros_listener.py 9 步）

收到车2 `lift-arrive` 后，系统按以下顺序执行：

| 步骤 | 动作 | 15 节点事件 |
|------|------|------------|
| Step 0 | 停止 ① pharmacist-success 连发；清除护士到达信号 | — |
| Step 1 | 电梯开门（TCP `open_door`，等 ACK + `ELEVATOR_DOOR_OPEN_DELAY=3` 秒） | N8 电梯开门 |
| Step 2 | 启动 ③ lift-across 连发 | N9 跨梯运输 |
| Step 3 | 等待 `ELEVATOR_ACROSS_TO_GO_FLOOR_DELAY` 秒（车2进梯，lift-across → 电梯上楼串行间隔，`.env` 可配置） | — |
| Step 4 | 电梯关门（TCP `close_door`，等 ACK + `ELEVATOR_DOOR_CLOSE_DELAY=3` 秒） | N10 电梯关门 |
| Step 5 | 查询当前楼层（同层跳过）→ `go_floor`（目标 `ELEVATOR_TARGET_FLOOR=4`）→ 等 ESP32 上报 `floor_arrived`（兜底 `ELEVATOR_FLOOR_ARRIVE_TIMEOUT=20` 秒） | N11 楼层到达 |
| Step 5.5 | **到达目标楼层后电梯开门**（TCP `open_door`，等 ACK + `ELEVATOR_DOOR_OPEN_DELAY=3` 秒，确保门已打开再放车2 出梯） | N12 开门送出（流水） |
| Step 6 | 启动 ⑦ lift-open 连发（开门完成后立即发送） | N12 开门送出 |
| Step 7 | 等待 HIS 节点4 扫码确认（`nurse-success-trigger` API 调用 `trigger_nurse_arrive_event()` 解锁；车2 `nurse_arrive` 消息仅触发语音播报，**不**解锁此步骤） | N14 语音播报 |
| Step 8 | 停止 ⑦ lift-open → 启动 ⑨ nurse-success（发 3 次停） | N15 任务完成 |

---

## 四、信号格式

### ① pharmacist-success（系统 → 车2，连发）

**触发**：HIS 节点3扫码出库完成（处方所有追溯码完成第一次扫码，判定 `status IN ('scanned_outbound','scanned_confirm')`，防药师重复扫码破坏计数 [medicineTraceCodes.ts:287]；第2次扫码分支亦有兜底补检 [medicineTraceCodes.ts:756]）→ HIS 调 `POST /api/v1/workflow/pharmacist-success-trigger` → 延迟 `PHARMACIST_SUCCESS_DELAY` 秒（默认 0）→ 启动连发。

**停止**：收到车2 `lift-arrive`（Step 0）。

**发送格式**（`data` 纯字符串，信息拼在 data 内）：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_pharmacist-success"
    }
}
```

---

### ② lift-arrive（车2 → 系统）

**触发**：车2 抵达电梯（进入跨楼流程的起点）。

**发送格式**：`{prescription_code}_lift-arrive`

---

### ③ lift-across（系统 → 车2，连发）

**触发**：lift-arrive 编排 Step 2（开门后）。

**停止**：lift-open 启动时自动切换停止（Step 6）。

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_lift-across"
    }
}
```

---

### ④ 延迟（串行间隔）

**时长**：`ELEVATOR_ACROSS_TO_GO_FLOOR_DELAY` 秒（`.env` 配置，当前 5 秒）

**语义**：发 lift-across 后 → 触发电梯上楼（Step 5）之间的**串行等待**，给车2 进梯留时间。期间无监听，超时后进入 Step 4 关门。调试可用 `/api/v1/elevator/debug/delay` 动态覆盖。

---

### ⑤ lift-open（系统 → 车2，连发）

**触发**：电梯真实到达目标楼层（收到 ESP32 `floor_arrived` 上报或 20s 兜底超时）→ **先执行到站开门**（TCP `open_door` + 等 `ELEVATOR_DOOR_OPEN_DELAY` 秒，见编排 Step 5.5）→ 门开后立即发送。

**停止**：HIS 节点4 扫码确认 API 触发 `trigger_nurse_arrive_event()` → Step 7 解锁 → Step 8 停止（**非**车2 `nurse_arrive` 消息触发）。

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_lift-open"
    }
}
```

---

### ⑥ nurse_arrive（车2 → 系统）

**触发**：车2 到达护士站。

**发送格式**：`{prescription_code}_nurse_arrive`

**系统动作**：仅记录日志 + 触发语音播报"药物已送达请您确认"（连播2次，每处方1轮）+ 记录 N14 事件。**不** set `_nurse_arrive_event`，**不**解锁 Step 7，**不**触发 nurse-success。

> **与直觉不同**：Step 7 的解锁条件不是车2 nurse_arrive 消息，而是 HIS 节点4 扫码全部确认后调用 `POST /nurse-success-trigger` → `trigger_nurse_arrive_event()` 设置 event。这是为了避免依赖车2 ROS 消息的可靠性，改用 HIS 扫码确认作为确定性触发源。

---

### ⑦ nurse-success（系统 → 车2，固定发 3 次）

**触发**：节点4扫码全部确认（处方所有追溯码扫到 `scanned_confirm`）。

链路：HIS 检测全部确认 → `POST /api/v1/workflow/nurse-success-trigger`（**阶段校验**：流程须已到 N12 开门送出之后，防药师阶段重复扫码提前误触发 [workflow.py:528]；幂等，同处方仅一次）→ 延迟 `NURSE_SUCCESS_DELAY` 秒（默认 0）→ 唤醒编排 Step 8。

**停止**：无外部回执依赖，固定发送 3 次后自动停止。

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_nurse-success"
    }
}
```

---

## 五、电梯硬件联动（TCP，非 ROS）

编排中 Step 1/4/5 通过 TCP 与 ESP32 电梯门禁交互（详见 `elevator_control.py` 与 `markdown/电梯功能测试报告.md`）：

| 命令 | 格式 | 说明 |
|------|------|------|
| 开门 | `{"cmd":"open_door","seq":N}\n` | 继电器3 @ GPIO17 |
| 关门 | `{"cmd":"close_door","seq":N}\n` | 继电器4 @ GPIO18 |
| 楼层查询 | `{"cmd":"status","seq":N}\n` | 返回当前楼层 |
| 去楼层 | `{"cmd":"go_floor","floor":4,"seq":N}\n` | 2楼→继电器1@GPIO9，4楼→继电器2@GPIO10 + 红外驱动 |
| 到达上报 | `{"type":"floor_arrived","floor":4}\n` | ESP32 完成移动后主动上报（20s 兜底） |
| 开机 | `{"cmd":"power_on","seq":N}\n` | 继电器5 @ GPIO19 持续吸合（方案A） |
| 关机 | `{"cmd":"power_off","seq":N}\n` | 继电器5 释放断电 |

---

## 六、信号汇总

| 步骤 | 方向 | 信号 | 发送方式 | 停止条件 |
|------|------|------|---------|---------|
| ① | 系统 → 车2 | `{prescription_code}_pharmacist-success` | 连发（2s/次） | 收到 lift-arrive |
| ② | 车2 → 系统 | `{prescription_code}_lift-arrive` | 单次 | — |
| ③ | 系统 → 车2 | `{prescription_code}_lift-across` | 连发（2s/次） | lift-open 启动（信号切换） |
| ④ | — | 延迟 `ELEVATOR_ACROSS_TO_GO_FLOOR_DELAY` 秒 | — | — |
| ⑤ | ESP32 → 系统 | `{"type":"floor_arrived","floor":4}` | 单次 | 20s 兜底超时 |
| ⑥′ | 系统 → ESP32 | `{"cmd":"open_door"}` 到站开门 | 单次 | 等 `ELEVATOR_DOOR_OPEN_DELAY` 秒后放行 lift-open |
| ⑥ | 系统 → 车2 | `{prescription_code}_lift-open` | 连发（2s/次） | HIS 节点4 扫码确认 → trigger_nurse_arrive_event() |
| ⑦ | 车2 → 系统 | `{prescription_code}_nurse_arrive` | 单次 | —（仅触发语音+N14，不解锁 Step 7） |
| ⑧ | 系统 → 车2 | `{prescription_code}_nurse-success` | 固定 3 次 | 发满 3 次自动停 |

---

## 七、关键实现位置

| 内容 | 代码位置 |
|------|---------|
| 连续发送框架（启动/停止/循环） | `his_sender.py:268-357` |
| 4 个信号入口方法 | `his_sender.py:503-537` |
| lift-arrive 9 步编排（含 Step 5.5 到站开门） | `ros_listener.py`（lift-arrive 分支） |
| 到站开门（Step 5.5） | `ros_listener.py`（`send_open_door` 第二处调用点） |
| 电梯 TCP 协议与命令 | `elevator_control.py` |
| 15 节点事件记录 | `ros_listener.py`（record_event 调用点） |
| 触发 API（HIS → 后端） | `api/v1/routers/workflow.py`（pharmacist-success-trigger / nurse-success-trigger） |
