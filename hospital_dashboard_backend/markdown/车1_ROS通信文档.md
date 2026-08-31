# 系统与 ROS 车1 通信文档

> 更新日期：2026-08-31（依据当前代码 `his_sender.py` / `ros_listener.py` / `.env` 实际实现核对）
>
> 车1 通信与车2 不同：车2 是"事件驱动的 4 信号"，车1 是**逐药品三阶段握手（start → running → end）** 的顺序结构；
> 药师扫码完成后系统会向车1 额外发送 `pharmacist-success` 信号（格式与 start 完全一致）。

## 一、连接配置

| 项 | 值 | 配置来源 |
|----|-----|---------|
| 连接地址 | `ws://192.168.51.43:9090` | `CAR1_WS_HOST` / `CAR1_WS_PORT` |
| 系统订阅 Topic | `/car01_pub`（`std_msgs/String`） | `CAR1_TOPIC` |
| 系统发布 Topic | `/rxzy_msg`（`rxzy_msg/his_sub`） | `CAR1_SEND_TOPIC` / `CAR1_SEND_MSG_TYPE` |
| 断线重连 | 每 `ROS_CHECK_INTERVAL=30` 秒 | `.env` |
| 处方轮询间隔 | `POLL_INTERVAL=2` 秒 | 代码常量 |
| 信号重发间隔 | `SEND_INTERVAL=2` 秒 | 代码常量 |
| start/running 重发上限 | `MEDICINE_SEND_MAX_ATTEMPTS=15` 次（超限停止发送） | `.env` |
| 回执静默等待时长 | `MEDICINE_RECEIPT_WAIT_TIMEOUT=300` 秒（重发上限后停止发送、仅等待，超时才放弃本处方） | `.env` |

---

## 二、收发职责

| 角色 | 订阅 | 发布 |
|------|------|------|
| 系统（后端） | `/car01_pub` | `/rxzy_msg` |
| 车1 ROS | `/rxzy_msg` | `/car01_pub` |

---

## 三、任务启动条件（处方从哪来）

后端主循环每 2 秒轮询 HIS MySQL（[his_sender.py:38-65](../app/services/his_sender.py#L38-L65)）：

```sql
SELECT prescription_code FROM prescriptions
WHERE status = 'approved'          -- 医生已开方、待配送
ORDER BY created_at DESC LIMIT 1
```

查询到新处方编码（与当前处理的不一致）时：

1. 重置药品状态，按 `medicine_id` 升序查询该处方所有药品坐标（`prescriptions → prescription_items → medicines → medicine_locations`，[his_sender.py:68-147](../app/services/his_sender.py#L68-L147)）；
2. 记录 15 节点事件 **N1 开具处方**；
3. 首**个**药品发送前记录 **N3 前往药房**（仅 idx=0 时）；
4. 进入逐药品 for 循环。

无待处理处方或药品列表为空时休眠等待。

**处方重入防护（DB 事件兜底）**：主循环每轮检查 `workflow_events`，若该处方已存在 **N5 扫码出库**事件（arm_end 已到，阶段一闭环），则跳过药品发送（[his_sender.py:824-833](../app/services/his_sender.py#L824-L833)）。作用：后端重启后内存进度丢失，不再从药1 重新发送 start——此前若车1 已完成任务不回执，会造成无限重发药1 start、药2 永远发不出。

**删除重下自愈（同单号复用兜底）**：HIS 删除处方→重新下单可能复用同一单号，若删除联动（DELETE `/workflow/prescription-events`）失败，上一轮旧事件残留会导致：大屏节点"全部完成"、重入防护误判"阶段一已闭环"而不发 start。自愈机制：sender 取单时比对 HIS 处方 `created_at` 与内存/DB 中记录的下单时间，**created_at 不一致 → 判定为删除重下的新单，自动清空旧事件**（含 state 表与幂等集合）后正常发 start（[his_sender.py:70-95](../app/services/his_sender.py#L70-L95)、主循环同码重下分支 [his_sender.py:774-798](../app/services/his_sender.py#L774-L798)）。重启后内存态 `_prescription_taken_at` 丢失，自动降级查 workflow_events 旧事件时间作为比较基准，无需依赖内存态。

---

## 四、单药品四阶段握手（核心）

每个药品依次执行 4 个阶段（[process_single_medicine](../app/services/his_sender.py)），前 2 阶段均带**回执驱动 + 2 秒重发 + 超限静默等待**：

```
阶段1  系统 → 车1:  data="start"（2s重发，上限15次）   等待回执: running-started
阶段2  系统 → 车1:  data="running"（2s重发，上限15次） 等待回执: running-step5-waiting-end
阶段3  系统 → 车1:  data="end"（固定2次，间隔2s，不等回执）   ← step5回执后立即发送
阶段4  等待3秒（让 ROS 处理 end）
```

> **重发上限 ≠ 等待上限**：真实车1 从收到 running 到 step5 含导航+抓药+放药，耗时可能远超 15次×2s=30s 的重发窗口。重发上限到达后系统**停止发送但继续静默等待回执**（最长 `MEDICINE_RECEIPT_WAIT_TIMEOUT=300` 秒，每 30s 打印等待心跳），期间回执到达照常推进（发 end / 下一药品 start）；仅静默等待超时才放弃本处方。

### 阶段1：发送 start

- **时机**：该药品开始处理时。
- **发送方式**：每 2 秒重发一次，直到收到回执；**重发上限 `MEDICINE_SEND_MAX_ATTEMPTS=15` 次（约30秒），超限停止发送**（[his_sender.py:617-636](../app/services/his_sender.py#L617-L636)）。
- **超限后**：停止发送、转入静默等待回执（最长 `MEDICINE_RECEIPT_WAIT_TIMEOUT=300` 秒，[his_sender.py:641-646](../app/services/his_sender.py#L641-L646)）。
- **最终超时后果**：静默等待超时打印 ERROR 日志，处方加入内存失败集合，主循环跳过该处方直到新处方到来（[his_sender.py:728-732](../app/services/his_sender.py#L728-L732)）。
- **回执条件**：`{medicine_id}_{prescription_code}_running-started` 且**处方编码 + 预期药品 ID 双重匹配**，任一不匹配仅打 ERROR 日志、不置事件、继续重发。
- **回执到达后**：置 `medicine_started[id]=True`，记 15 节点 **N2 任务确认**，触发语音播报"car_can_go"（每处方仅一次）。

### 阶段2：发送 running

- **时机**：收到 running-started 之后。
- **发送方式**：每 2 秒重发，直到收到回执；同样受 `MEDICINE_SEND_MAX_ATTEMPTS=15` 上限保护（超限停止发送），超限后静默等待回执最长 `MEDICINE_RECEIPT_WAIT_TIMEOUT=300` 秒（[his_sender.py:651-681](../app/services/his_sender.py#L651-L681)）——本阶段等待最关键：真实车1 从 running 到 step5 含导航+抓药+放药，实测超过 43s，远超 30s 重发窗口。
- **回执条件**：`{medicine_id}_{prescription_code}_running-step5-waiting-end`，同样双重校验。
- **特殊**：若 step5 回执在阶段1 期间已提前到达（事件已 set），直接跳过 running 发送。

### 阶段3：发送 end

- **时机**：收到 step5-waiting-end 回执后**立即发送**（无需等待药师扫码）。
- **发送方式**：**固定发送 2 次，间隔 2 秒，不等待回执**（与 start/running 的连发模式不同）。
- **消息体**：含完整药品坐标上下文（与 start/running 相同结构）。

### 阶段4：等待 3 秒

固定 `await asyncio.sleep(3)`，给 ROS 端处理 end 的时间，然后进入下一个药品（或结束循环）。

---

## 五、药师扫码 → pharmacist-success 信号（★车1 新增）

### 5.1 触发条件（与车2 完全同一判定点）

```
药师扫码（HIS 节点3）：处方所有追溯码完成第一次扫码
  判定 total>0 && outbound==total，outbound 统计 status IN ('scanned_outbound','scanned_confirm')
  [medicineTraceCodes.ts:287]（防药师重复扫码把状态推到 scanned_confirm 后计数归零）；
  第2次扫码分支另有兜底补检 [medicineTraceCodes.ts:756]
→ HIS 调 POST /api/v1/workflow/pharmacist-success-trigger
→ 后端 workflow.py 同一触发点：
     ① 车2 发送 pharmacist-success（纯字符串 data）
     ② 车1 发送 pharmacist-success（结构化格式，与 start 完全一致）
```

### 5.2 发送方式

**单发 + 失败重试**：只发 1 次，成功即停；发送失败（如 WebSocket 瞬时断连）时自动重试，最多 3 次（间隔 `CAR2_SIGNAL_INTERVAL=2` 秒），3 次均失败打印 ERROR 后放弃（[his_sender.py:539-578](../app/services/his_sender.py#L539-L578)）。

> 与车2 连发模式的区别：车1 无回执停止机制（车1 上报侧不监听该信号的回执），连发会无限刷屏，故采用单发。车2 维持连发（收到 lift-arrive 停）不变。

### 5.3 消息格式（与 start 完全一致，字段零删减）

```json
{
    "op": "publish",
    "topic": "/rxzy_msg",
    "msg": {
        "data": "pharmacist-success",
        "prescription_code": "012026082700129",
        "medicine_id": 1,
        "x": 1.5, "y": 2.0, "z": 0.0, "yaw": 0.0,
        "medicine_total": 2,
        "medicine_index": 1
    }
}
```

| 字段 | 取值说明 |
|------|---------|
| `data` | 固定 `pharmacist-success` |
| `prescription_code` | 触发接口传入的处方码 |
| `medicine_id` / `x` / `y` / `z` / `yaw` | 触发那一刻车1 正在处理的药品上下文（无药品时 medicine_id=0、坐标=0.0，字段保留不删减） |
| `medicine_total` / `medicine_index` | 当前处方药品总数 / 当前序号（无上下文时为 0） |

---

## 六、系统 → 车1 消息格式汇总

`start` / `running` / `end` 三种命令共用同一结构，仅 `data` 字段不同；`pharmacist-success` 同结构（见第五节）：

```json
{
    "op": "publish",
    "topic": "/rxzy_msg",
    "msg": {
        "data": "start | running | end",
        "prescription_code": "012026082700129",
        "medicine_id": 1,
        "x": 1.5, "y": 2.0, "z": 0.0, "yaw": 0.0,
        "medicine_total": 2,
        "medicine_index": 1
    }
}
```

| 字段 | 说明 |
|------|------|
| `data` | 命令：start（开始取该药）/ running（继续执行）/ end（该药完成）/ pharmacist-success（药师扫码完成） |
| `x/y/z/yaw` | 该药品在药房的抓取坐标（来自 medicine_locations 表） |
| `medicine_total` | 本处方药品总数（车1 用于判断是否最后一个药品） |
| `medicine_index` | 当前药品序号（从 1 开始） |

---

## 七、车1 → 系统消息（状态上报）

统一格式 `{medicine_id}_{prescription_code}_{status}`（药单级消息无 medicine_id 前缀），解析见 [parse_ros_message](../app/services/ros_listener.py#L76-L140)。`medicine_id=0` 的消息被"去0机制"直接忽略。

### 7.1 驱动握手流程的消息（改变系统行为）

| 消息 | 系统动作 | 15 节点 |
|------|---------|---------|
| `{id}_{code}_running-started` | 双重校验通过 → 置 started 事件，解锁阶段2 | N2 任务确认 + 语音 car_can_go |
| `{id}_{code}_running-step5-waiting-end` | 双重校验通过 → 置 step5 事件，解锁阶段3（发 end） | — |
| `{code}_all_completed`（**无 medicine_id 前缀**） | 处方码匹配 → 置 all_completed + task_completed，停止发送；连播2次语音 | N4 所有药品已抓取 + 语音 |
| `{id}_{code}_end` | 仅记日志（顺序结构由 for 循环切换） | — |
| `{code}_end`（药单级，无 id） | 置 task_end 事件 + **HIS 处方状态 → dispensed**（[update_his_prescription_status](../app/services/ros_listener.py#L196-L233)） | — |

### 7.2 机械臂消息（N4 节点过程 + ★arm_end 驱动节点切换）

| 消息 | 含义 | 系统动作 | 15 节点 |
|------|------|---------|---------|
| `{id}_{code}_arm-picking` | 机械臂正在抓取（VIEW→PRE→CONTACT→ESCAPE） | 记事件 | N4 detail: 机械臂正在抓取（药品ID=X） |
| `{id}_{code}_arm-placing` | 机械臂正在放药（ESCAPE→BASKET→VIEW） | 记事件 | N4 detail: 机械臂正在放药（药品ID=X） |
| `{id}_{code}_arm-error` | 机械臂模块错误（规划失败/起点误差/吸泵异常等） | 记事件 + warning 日志 | N4 detail: 机械臂执行异常 |
| **`{code}_arm_end`**（**药单级，无 id 前缀**） | **机械臂流程结束（整张药单）** | 补记缺失 N1-N3（system）→ N4 置完成 → N5 置进行中（[ros_listener.py:750-775](../app/services/ros_listener.py#L750-L775)） | **N4 completed + N5 active"扫码出库进行中（等待药师扫码）"** |

**arm_end 切换规则**：

- 幂等：阶段一已闭环（N5 已有正式事件）→ 忽略，不复活 N4
- arm_end 到达后，晚到的 arm-* / all_completed 事件同样被拦截（`_stage1_finalized` 防护），N4 保持 completed
- 药师全部扫码完成后，N5 的 detail 更新为"药师扫码出库完成"（pharmacist-success-trigger 闭环逻辑），N6 变 active

### 7.3 过程状态消息（仅更新大屏展示/旧4节点表）

| 消息 | 展示语义 |
|------|---------|
| `running-step1-navigate-to-pharmacy` | 前往药房中 |
| `running-step2-pick` | 抓药中（机械臂阶段） |
| `running-step3-deliver-medicine` | 放药/送药中 |
| `running-step4-navigate-doctor` / `skip-doctor` | 前往确认点（最后一个药品）/ 跳过 |
| `running-step5-return` / `skip-return` | 返回原点（最后一个药品）/ 跳过 |
| `error-step1-cannot-reach-pharmacy` | 无法到达药房 |
| `error-step2-arm-pick` / `error-step3-arm-place` | 机械臂抓/放药失败 |
| `error-step4-cannot-reach-patient-room` | 无法到达确认点 |
| `error-step5-cannot-return-to-home` | 无法返回原点 |

⚠️ 注意：error-* 消息**只更新展示**，不中断握手流程、不进 15 节点事件（时间线上表现为节点停滞）。

---

## 八、一单两药的切换逻辑（重点）

处方含 2 个药品（A、B）时，主循环 for **严格串行**处理：

```
药品A（idx=0）
  阶段1 start ──重发──▶ A_running-started
  阶段2 running ──重发──▶ A_running-step5-waiting-end
  阶段3 end ×2次（step5回执后立即发送）──▶ 阶段4 等3秒
        │
        ▼  for 循环 idx+1，回执事件在下个药品开始时 clear() 后重新等待
药品B（idx=1）
  阶段1 start（携带 B 的坐标）──重发──▶ B_running-started
  阶段2 running ──重发──▶ B_running-step5-waiting-end
  阶段3 end ×2次 ──▶ 阶段4 等3秒
        │
        ▼  idx 到达 total-1，循环结束
（等待车1 上报 arm_end / all_completed / 药单级 end 收尾）
```

**切换要点**：

| 环节 | 机制 |
|------|------|
| 药品间切换时机 | 上一药品 end 发完 + 3 秒等待后，for 循环取下一个药品；**不依赖药师扫码**（扫码只发 success 信号，不参与切换） |
| 事件隔离 | `started_event` / `step5_return_event` 在**每个药品处理开始时 clear()**，保证 B 的 start 不会误吃 A 的旧回执 |
| 回执匹配 | A 处理期间若收到 B 的 running-started（乱序），药品 ID 不匹配 → 忽略，A 的 start 继续重发 |
| 坐标切换 | 每个 start/running/end 消息携带当前药品各自的 x/y/z/yaw，B 阶段发 B 的坐标 |
| 失败退出 | 任一药品任一阶段失败（发送异常）→ `break` 退出 for 循环，本处方处理终止，回到主循环 |
| medicine_id=0/NULL | 该药品直接 `continue` 跳过（不发送、不算失败） |

**结束条件**：车1 在最后一个药品 end 后上报 `{code}_arm_end`（机械臂流程结束，N4→N5 切换）、`{code}_all_completed`（所有药品抓取完，触发语音+停止发送）和 `{code}_end`（药单级，HIS 处方置 `dispensed`，任务彻底完成）。

---

## 九、信号汇总（截至药师扫码 pharmacist-success）

| 阶段 | 方向 | data/消息 | 发送方式 | 解锁条件 |
|------|------|----------|---------|---------|
| 阶段1 | 系统 → 车1 | `start`（含坐标） | 2s 重发，上限 15 次（超限停止发送、静默等待最长 300s） | 收到该药品 running-started |
| 阶段2 | 系统 → 车1 | `running`（含坐标） | 2s 重发，上限 15 次（超限停止发送、静默等待最长 300s） | 收到该药品 step5-waiting-end |
| 阶段3 | 系统 → 车1 | `end`（含坐标） | 固定 2 次 | 不等回执 |
| 阶段4 | — | 等 3 秒 | 固定 | — |
| 收尾 | 车1 → 系统 | `{code}_arm_end` | 单次 | N4 完成 + N5 进行中 |
| 收尾 | 车1 → 系统 | `{code}_all_completed` | 单次 | 停止发送 + 语音×2 |
| 收尾 | 车1 → 系统 | `{code}_end` | 单次 | HIS 处方 → dispensed |
| **扫码完成** | **系统 → 车1** | **`pharmacist-success`（start 同构格式）** | **单发（失败重试最多 3 次）** | **HIS 节点3 全部扫码完成（pharmacist-success-trigger）** |

---

## 十、关键实现位置

| 内容 | 代码位置 |
|------|---------|
| 处方轮询 SQL（approved 最新一单） | `his_sender.py:38-65` |
| 药品坐标查询（4 表联查） | `his_sender.py:68-147` |
| 单药品四阶段握手（阶段1-4） | `his_sender.py` process_single_medicine |
| 阶段1/2 重发上限（超限停止发送） | `his_sender.py:617-636, 651-670` |
| 回执静默等待（超限后等待，超时放弃） | `his_sender.py` _wait_receipt_silently |
| 失败处方集合（跳过直到新处方） | `his_sender.py:728-732, 768-770` |
| 处方重入防护（N5 事件存在即跳过） | `his_sender.py:824-833` |
| 删除重下自愈（同单号复用时清理旧事件，含 DB 级降级） | `his_sender.py:70-95, 774-798` |
| start/running/end 消息构造 | `his_sender.py:361-451` |
| pharmacist-success 车1 发送（start 同构格式，单发+失败重试3次） | `his_sender.py:539-578` |
| arm_end → N4/N5 切换 | `ros_listener.py:750-775` |
| 阶段一闭环防护（_stage1_finalized） | `ros_listener.py:30-43` |
| 回执校验（双重匹配） | `notify_*` 系列 |
| 消息解析（`_` 前缀 + 后缀匹配） | `ros_listener.py:76-140` |
| 药单级 end → HIS dispensed | `ros_listener.py:196-233` |
| 语音播报（car_can_go / 完成播报） | `ros_listener.py:563-635` |
| 车1 topic 接口原始文档 | `../../car01_topic_interface.md` |
