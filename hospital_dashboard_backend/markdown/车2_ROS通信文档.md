# 系统与 ROS 车2 通信文档


Set-Location "E:\contest\July_one\hospital\hospital_new_demo_back-test"
.\start-backend.ps1

## 一、连接配置

| 项 | 值 |
|----|-----|
| 连接地址 | `ws://192.168.51.12:9090` |
| 系统订阅 Topic | `/car02_pub` |
| 系统发布 Topic | `/car02_rxzy_msg` |

---

## 二、收发职责

| 角色 | 订阅 | 发布 |
|------|------|------|
| 系统（后端） | `/car02_pub` | `/car02_rxzy_msg` |
| 车2 ROS | `/car02_rxzy_msg` | `/car02_pub` |

---

## 三、通信流程（顺序结构）

```
① 系统 → 车2:  {prescription_code}_pharmacist-success
② 车2 → 系统:  {prescription_code}_lift-arrive
③ 系统 → 车2:  {prescription_code}_lift-across
④ 延迟 60 秒
⑤ 系统 → 车2:  {prescription_code}_lift-open
⑥ 车2 → 系统:  {prescription_code}_nurse_arrive
⑦ 系统 → 车2:  {prescription_code}_nurse-success
```

---

## 四、信号格式

### ① pharmacist-success（系统 → 车2）

**触发**：车1 药师审核完成后

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_pharmacist-success",
        "medicine_id": 1,
        "prescription_code": "{prescription_code}"
    }
}
```

---

### ② lift-arrive（车2 → 系统）

**触发**：车2 电梯到达目标楼层

**发送格式**：`{prescription_code}_lift-arrive`

---

### ③ lift-across（系统 → 车2）

**触发**：收到 lift-arrive 后立即发送

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_lift-across",
        "prescription_code": "{prescription_code}"
    }
}
```

---

### ④ 延迟

**时长**：`LIFT_ACROSS_DELAY=60` 秒（`.env` 配置）

**期间无监听**。

---

### ⑤ lift-open（系统 → 车2）

**触发**：延迟结束后

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_lift-open",
        "prescription_code": "{prescription_code}"
    }
}
```

---

### ⑥ nurse_arrive（车2 → 系统）

**触发**：护士到达后

**发送格式**：`{prescription_code}_nurse_arrive`

**注意**：nurse_arrive 消息**不再触发** nurse-success（仅记录日志，语音播报仍由该消息触发）。nurse-success 改由节点4扫码触发，见 ⑦。

---

### ⑦ nurse-success（系统 → 车2）

**触发**：节点4扫码全部确认（处方所有追溯码扫到 `scanned_confirm`，即每个药品完成第二次扫码：节点3出库一次 + 节点4确认一次）。

链路：HIS 检测全部确认 → `POST /api/v1/workflow/nurse-success-trigger`（幂等，同处方仅一次）→ 延迟 `NURSE_SUCCESS_DELAY` 秒（.env 配置，默认 0）→ 唤醒车2编排 Step7 → 停止 lift-open 连发 → 发送 nurse-success（连发 3 次自动停）

**发送格式**：

```json
{
    "op": "publish",
    "topic": "/car02_rxzy_msg",
    "msg": {
        "data": "{prescription_code}_nurse-success",
        "prescription_code": "{prescription_code}"
    }
}
```

---

## 五、信号汇总

| 步骤 | 方向 | 信号 |
|------|------|------|
| ① | 系统 → 车2 | `{prescription_code}_pharmacist-success` |
| ② | 车2 → 系统 | `{prescription_code}_lift-arrive` |
| ③ | 系统 → 车2 | `{prescription_code}_lift-across` |
| ④ | — | 延迟 `LIFT_ACROSS_DELAY` 秒 |
| ⑤ | 系统 → 车2 | `{prescription_code}_lift-open` |
| ⑥ | 车2 → 系统 | `{prescription_code}_nurse_arrive` |
| ⑦ | 系统 → 车2 | `{prescription_code}_nurse-success` |