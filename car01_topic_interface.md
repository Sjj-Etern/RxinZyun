# Car01 状态 Topic 接口说明

## 1. 目的

本文档用于说明 `car01` 主程序与机械臂模块向外部系统发布状态消息时使用的 ROS Topic、消息格式与状态含义。

接收端系统只需要订阅：

```text
/car01_pub
```

即可接收小车任务状态和机械臂状态。

---

## 2. Topic 基本信息

| 项目 | 值 |
|---|---|
| Topic | `/car01_pub` |
| ROS 消息类型 | `std_msgs/String` |
| 发布方向 | car01 主程序 / 机械臂模块 → 外部业务系统 |
| 推荐用途 | HIS、调度系统、状态显示、任务监控 |

ROS 发布器形式：

```python
pub = rospy.Publisher(
    "car01_pub",
    String,
    queue_size=10,
)
```

---

## 3. 消息统一格式

绝大多数药品级状态统一采用：

```text
{medicine_id}_{prescription_code}_{status}
```

字段含义：

| 字段 | 含义 | 示例 |
|---|---|---|
| `medicine_id` | 当前药品 ID | `1` |
| `prescription_code` | 药单 / 处方编号 | `012026070800127` |
| `status` | 当前状态 | `arm-picking` |

完整示例：

```text
1_012026070800127_arm-picking
```

---

# 4. 机械臂模块状态

机械臂模块 `medicine_arm_controller.py` 发布三类核心状态。

## 4.1 正在抓取

```text
{medicine_id}_{prescription_code}_arm-picking
```

示例：

```text
1_012026070800127_arm-picking
```

含义：

- 已进入机械臂抓药阶段；
- 即将或正在执行对应药品的抓取轨迹；
- 可能包含 `VIEW -> PRE -> CONTACT -> ESCAPE`；
- 该状态不表示抓取已经成功完成。

---

## 4.2 正在放药

```text
{medicine_id}_{prescription_code}_arm-placing
```

示例：

```text
1_012026070800127_arm-placing
```

含义：

- 已进入机械臂放药阶段；
- 正在执行携药到篮筐并返回观察位的流程；
- 可能包含 `ESCAPE -> BASKET -> VIEW`；
- 该状态不表示整个任务已经完成。

---

## 4.3 机械臂错误

```text
{medicine_id}_{prescription_code}_arm-error
```

示例：

```text
1_012026070800127_arm-error
```

含义：

机械臂抓取或放药过程中出现异常，例如：

- MoveIt 规划 / 碰撞检查失败；
- 固定缓存校验失败；
- 真机起点误差超过安全门限；
- 机械臂通信异常；
- FullExecutor 执行失败；
- 终点到位误差超限；
- payload / Planning Scene 安全检查失败；
- 吸泵相关执行异常。

注意：

`arm-error` 只表示机械臂模块发生错误。
具体错误原因应结合 car01 ROS 日志查看。

---

# 5. 主程序原有任务状态

主程序 `more_task_node714.py` 仍会继续发布原有 Step 级状态。

这些状态与机械臂模块状态并存，不冲突。

## 5.1 任务开始

```text
{medicine_id}_{prescription_code}_running-started
```

示例：

```text
1_012026070800127_running-started
```

---

## 5.2 前往药房

```text
{medicine_id}_{prescription_code}_running-step1-navigate-to-pharmacy
```

---

## 5.3 Step 2 抓药

```text
{medicine_id}_{prescription_code}_running-step2-pick
```

进入该 Step 后，机械臂模块还会进一步发布：

```text
{medicine_id}_{prescription_code}_arm-picking
```

因此接收端可能依次看到：

```text
1_012026070800127_running-step2-pick
1_012026070800127_arm-picking
```

---

## 5.4 Step 3 放药

```text
{medicine_id}_{prescription_code}_running-step3-deliver-medicine
```

进入该 Step 后，机械臂模块还会发布：

```text
{medicine_id}_{prescription_code}_arm-placing
```

例如：

```text
1_012026070800127_running-step3-deliver-medicine
1_012026070800127_arm-placing
```

---

## 5.5 Step 4 前往确认点

最后一个药品时：

```text
{medicine_id}_{prescription_code}_running-step4-navigate-doctor
```

非最后一个药品时：

```text
{medicine_id}_{prescription_code}_running-step4-skip-doctor
```

---

## 5.6 等待 HIS End

```text
{medicine_id}_{prescription_code}_running-step5-waiting-end
```

---

## 5.7 返回原点

最后一个药品：

```text
{medicine_id}_{prescription_code}_running-step5-return
```

非最后一个药品：

```text
{medicine_id}_{prescription_code}_running-step5-skip-return
```

---

# 6. 主程序错误状态

## 6.1 无法到达药房

```text
{medicine_id}_{prescription_code}_error-step1-cannot-reach-pharmacy
```

## 6.2 机械臂抓药失败

```text
{medicine_id}_{prescription_code}_error-step2-arm-pick
```

发生机械臂内部异常时，一般还会同时出现：

```text
{medicine_id}_{prescription_code}_arm-error
```

示例：

```text
1_012026070800127_arm-error
1_012026070800127_error-step2-arm-pick
```

区别：

- `arm-error`：机械臂模块自身错误；
- `error-step2-arm-pick`：主任务确认 Step 2 失败。

---

## 6.3 机械臂放药失败

```text
{medicine_id}_{prescription_code}_error-step3-arm-place
```

可能同时出现：

```text
{medicine_id}_{prescription_code}_arm-error
```

---

## 6.4 无法到达确认点

```text
{medicine_id}_{prescription_code}_error-step4-cannot-reach-patient-room
```

---

## 6.5 无法返回原点

```text
{medicine_id}_{prescription_code}_error-step5-cannot-return-to-home
```

---

# 7. End 回执

收到 HIS Sender 的 `end` 后，car01 会回执。

## 7.1 非最后一个药品

格式：

```text
{medicine_id}_{prescription_code}_end
```

示例：

```text
1_012026070800127_end
```

## 7.2 最后一个药品

格式：

```text
{prescription_code}_all_completed
```

示例：

```text
012026070800127_all_completed
```

注意：

这是当前协议中少数不带 `medicine_id` 前缀的消息。

---

# 8. 接收端建议解析方式

由于状态字符串本身使用 `-`，建议不要简单按所有下划线无限拆分。

对于普通药品级消息：

```text
1_012026070800127_arm-picking
```

可理解为：

```text
medicine_id       = 1
prescription_code = 012026070800127
status            = arm-picking
```

推荐接收端优先按已知状态后缀匹配。

例如已知状态集合：

```text
arm-picking
arm-placing
arm-error
running-started
running-step1-navigate-to-pharmacy
running-step2-pick
running-step3-deliver-medicine
running-step4-navigate-doctor
running-step4-skip-doctor
running-step5-waiting-end
running-step5-return
running-step5-skip-return
error-step1-cannot-reach-pharmacy
error-step2-arm-pick
error-step3-arm-place
error-step4-cannot-reach-patient-room
error-step5-cannot-return-to-home
end
all_completed
```

---

# 9. ROS 调试

监听 car01 发布：

```bash
rostopic echo /car01_pub
```

查看 Topic 类型：

```bash
rostopic type /car01_pub
```

正常应返回：

```text
std_msgs/String
```

查看连接情况：

```bash
rostopic info /car01_pub
```

---

# 10. 示例完整状态流

以：

```text
medicine_id = 1
prescription_code = 012026070800127
```

为例，一次正常任务可能出现：

```text
1_012026070800127_running-started

1_012026070800127_running-step1-navigate-to-pharmacy

1_012026070800127_running-step2-pick
1_012026070800127_arm-picking

1_012026070800127_running-step3-deliver-medicine
1_012026070800127_arm-placing

1_012026070800127_running-step4-navigate-doctor

1_012026070800127_running-step5-waiting-end

012026070800127_all_completed

1_012026070800127_running-step5-return
```

如果抓药过程中出现机械臂错误：

```text
1_012026070800127_running-step2-pick
1_012026070800127_arm-picking
1_012026070800127_arm-error
1_012026070800127_error-step2-arm-pick
```

---

# 11. 当前模块职责划分

```text
more_task_node714.py
    │
    ├── HIS / rxzy_msg
    ├── 导航
    ├── Step1 ~ Step5
    ├── 发布任务级 car01_pub 状态
    │
    ├── arm_pick(...)
    │       ↓
    │   medicine_arm_controller.py
    │       └── 发布 arm-picking / arm-error
    │
    └── arm_place(...)
            ↓
        medicine_arm_controller.py
            └── 发布 arm-placing / arm-error
```

主程序负责“任务进行到哪一步”。

机械臂模块负责“机械臂当前在抓、在放、还是发生错误”。

两者统一发布到：

```text
/car01_pub
```

由接收系统统一订阅即可。
