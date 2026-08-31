# -*- coding: utf-8 -*-
"""
车1/车2 端到端通信测试脚本(模拟 ROS 端)
================================================

用途:在不依赖真实小车的情况下,与真实后端(:8080)+ 真实 HIS(:3001)
      + 真实大屏(:5174)+ 真实 ESP32 电梯(:10833)联调,端到端验证
      15 节点工作流。人工在 HIS 界面下单/扫码,脚本自动模拟两车收发。

原理:
  1. 在 127.0.0.1:9090 起 WebSocket 服务器,实现 rosbridge 最小协议子集
     - 响应后端 "op":"subscribe"(记录订阅的 topic)
     - 接收后端 "op":"publish"(start/running/end/lift-across 等命令)并按 topic 路由
     - 模拟车1/车2 状态上报到 /car01_pub、/car02_pub(推给订阅者)
     - 2Hz 推送 pose 到 car01_pose、car02_pose(按业务阶段移动)
  2. 车1:逐药品四阶段握手(start→running-started→running→step5→end→药品级end
     + 末药 arm_end/all_completed/药单级end)
  3. 车2:事件驱动(pharmacist-success→lift-arrive;lift-open→nurse_arrive)
  4. 电梯不模拟(连真实 ESP32);HIS 下单/扫码由人工操作

启动顺序:
  1. 改 hospital_dashboard_backend/.env:CAR1_WS_HOST=127.0.0.1、CAR2_WS_HOST=127.0.0.1
  2. 启本脚本:  python test_ros_e2e.py            (默认全自动)
              python test_ros_e2e.py --step     (暂停版,关键节点等回车)
  3. 启后端:    python app.py
  4. 启 HIS(:3001)+ 大屏(:5174)+ ESP32 上电
  5. HIS 界面下单(:3002)→ 观察脚本自动模拟车1 取药
  6. HIS 界面节点3 扫码 → 观察车2 跨楼 + 电梯8步(真实ESP32)
  7. HIS 界面节点4 扫码 → nurse-success ×3 → 流程结束

参考文档:
  - markdown/车1_ROS通信文档.md(逐药品四阶段握手)
  - markdown/车2_ROS通信文档.md(4信号+8步电梯编排)
  - car01_topic_interface.md(车1 状态消息格式)
"""
import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from collections import defaultdict
from typing import Optional

import websockets

# 屏蔽 websockets 对"裸 TCP 端口探测"的握手失败 traceback(后端 check_port_reachable
# 只用 socket 直连不发 HTTP,websockets 会当作坏连接打 ERROR 栈,纯属噪音)
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)

# ====================================================================
# 常量配置(与后端 config.py:81-96、.env 严格一致)
# ====================================================================

HOST = "127.0.0.1"
PORT = 9090
POSE_HZ = 2.0  # pose 推送频率(与真实 publisher 一致)

# Topic 命名(状态 topic 带斜杠,pose topic 不带斜杠,见 config.py:85-94)
CAR1_STATUS_TOPIC = "/car01_pub"       # 车1 状态上报(后端订阅接收)
CAR1_POSE_TOPIC = "car01_pose"         # 车1 pose(不带斜杠)
CAR1_CMD_TOPIC = "/rxzy_msg"           # 车1 命令(后端发布 start/running/end)
CAR2_STATUS_TOPIC = "/car02_pub"       # 车2 状态上报
CAR2_POSE_TOPIC = "car02_pose"         # 车2 pose
CAR2_CMD_TOPIC = "/car02_rxzy_msg"     # 车2 命令(后端发布 4 信号)

# 业务路径点(复用 ros_listener.py:465-469 MOCK_WAYPOINTS,与前端 CadScene 对齐,不出地图)
# 车1: HOME→药房→病房投放→返回途经→HOME
# 车2: HOME→电梯等待→电梯内→护士站→HOME
CAR1_WAYPOINTS = [(1.56, 0.141), (1.54, -0.39), (0.030, -0.2777), (0.040, 0.227), (1.56, 0.141)]
CAR2_WAYPOINTS = [(0.30284, -0.225737), (-0.105803, -0.941809),
                  (-0.626348, -0.799792), (-0.870578, -1.5837), (0.30284, -0.225737)]
POSE_SPEED = 0.15  # 巡游速度(米/秒)

# 默认时序间隔(秒)
DEFAULT_LIFT_ARRIVE_DELAY = 7.0    # 收到 pharmacist-success → 上报 lift-arrive
DEFAULT_NURSE_ARRIVE_DELAY = 7.0   # 收到 lift-open → 上报 nurse_arrive
START_REPLY_DELAY = 0.3            # 收到 start → 发 running-started
STEP_INTERVAL = 1.0                # 车1 中间步骤间隔(step1/step2/...)
END_REPLY_DELAY = 0.5              # 收到 end×2 → 发药品级 end
LAST_MEDICINE_INTERVAL = 1.0       # 末药 arm_end/all_completed/药单级end 间隔

# .env 路径(脚本同级目录)
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


# ====================================================================
# 彩色日志(终端)
# ====================================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def log(role: str, msg: str, color: str = C.CYAN) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"{C.GRAY}[{ts}]{C.RESET} {color}{C.BOLD}[{role}]{C.RESET} {color}{msg}{C.RESET}")


def log_recv(role: str, topic: str, data: str) -> None:
    log(role, f"← 后端命令: topic={topic} data={str(data)[:80]}", C.YELLOW)


def log_send(role: str, topic: str, data: str) -> None:
    log(role, f"→ 上报状态: topic={topic} data={data}", C.GREEN)


def log_node(node: str, msg: str) -> None:
    log("NODE", f"{C.MAGENTA}{node}{C.RESET} {msg}", C.MAGENTA)


def log_pause(msg: str) -> None:
    print(f"\n{C.YELLOW}{C.BOLD}{'='*60}{C.RESET}")
    print(f"{C.YELLOW}{C.BOLD}[暂停] {msg}{C.RESET}")
    print(f"{C.YELLOW}{'='*60}{C.RESET}")


# ====================================================================
# .env 预检
# ====================================================================

def check_env() -> bool:
    """检查 .env 的 CAR1_WS_HOST/CAR2_WS_HOST 是否为 127.0.0.1。
    非 127.0.0.1 则打印警告并返回 False(不自动改,需手动改后重启后端)。
    """
    if not os.path.exists(ENV_PATH):
        log("ENV", f"未找到 .env({ENV_PATH}),无法预检。请确认后端 .env 配置。", C.RED)
        return False

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    car1 = re.search(r"^CAR1_WS_HOST=(.+)$", content, re.MULTILINE)
    car2 = re.search(r"^CAR2_WS_HOST=(.+)$", content, re.MULTILINE)
    car1_val = car1.group(1).strip() if car1 else None
    car2_val = car2.group(1).strip() if car2 else None

    ok = True
    if car1_val != "127.0.0.1":
        log("ENV", f"CAR1_WS_HOST={car1_val}(应为 127.0.0.1),后端无法连本脚本", C.RED)
        ok = False
    if car2_val != "127.0.0.1":
        log("ENV", f"CAR2_WS_HOST={car2_val}(应为 127.0.0.1),后端无法连本脚本", C.RED)
        ok = False

    if not ok:
        print(f"\n{C.RED}{C.BOLD}{'='*60}{C.RESET}")
        print(f"{C.RED}请修改 {ENV_PATH}{C.RESET}")
        print(f"{C.RED}  CAR1_WS_HOST=127.0.0.1{C.RESET}")
        print(f"{C.RED}  CAR2_WS_HOST=127.0.0.1{C.RESET}")
        print(f"{C.RED}改完后重启后端(python app.py)再跑本脚本。{C.RESET}")
        print(f"{C.RED}{'='*60}{C.RESET}\n")
        return False

    log("ENV", "预检通过:CAR1/CAR2_WS_HOST=127.0.0.1", C.GREEN)
    return True


# ====================================================================
# Pose 移动器(按业务阶段在路径点折线上匀速插值)
# ====================================================================

class PoseMover:
    """每车维护当前位置 + 目标 waypoint,2Hz tick 时按速度向目标移动。"""

    def __init__(self, car_id: int, waypoints: list):
        self.car_id = car_id
        self.waypoints = waypoints
        self.cur = list(waypoints[0])  # 当前坐标 [x, y]
        self.target_idx = 0            # 目标 waypoint 索引

    def set_target(self, idx: int, reason: str = ""):
        """切换目标 waypoint(收到命令时调用)。"""
        if 0 <= idx < len(self.waypoints) and idx != self.target_idx:
            self.target_idx = idx
            log(f"CAR{self.car_id}-POSE", f"目标切换→waypoint[{idx}]{self.waypoints[idx]} {reason}", C.BLUE)

    def tick(self):
        """2Hz 调用:向目标移动一步(距离不足则到达)。"""
        tx, ty = self.waypoints[self.target_idx]
        dx = tx - self.cur[0]
        dy = ty - self.cur[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return  # 已到达
        step = POSE_SPEED / POSE_HZ  # 单 tick 移动距离
        if dist <= step:
            self.cur[0] = tx
            self.cur[1] = ty
        else:
            self.cur[0] += dx / dist * step
            self.cur[1] += dy / dist * step

    def pose_msg(self) -> str:
        """构造 pose 消息(格式与 mock_rosbridge.py:50-54 一致)。"""
        topic = CAR1_POSE_TOPIC if self.car_id == 1 else CAR2_POSE_TOPIC
        return json.dumps({
            "op": "publish",
            "topic": topic,
            "msg": {"data": f"{self.cur[0]:.3f},{self.cur[1]:.3f}"},
        })


# ====================================================================
# 车1 状态机(逐药品四阶段握手)
# ====================================================================

class Car1StateMachine:
    """处理车1 命令(start/running/end),上报状态到 /car01_pub。

    时序(参考 car01_topic_interface.md 第10节示例完整状态流):
      收到 start → running-started [N2] → step1 → step2+arm-picking →
      step3 → step4+arm-placing → (等 running) → step5-waiting-end →
      (等 end×2) → 药品级 end → [末药] arm_end [N4] → all_completed → 药单级 end
    """

    def __init__(self, step_mode: bool, pause_fn, send_fn, pose_mover: PoseMover):
        self.step_mode = step_mode
        self.pause = pause_fn        # async pause(node, msg, timeout_warn)
        self.send = send_fn          # async send(status_str) → 推给 /car01_pub 订阅者
        self.pose = pose_mover
        # 每药品状态: (medicine_id, code) -> {started, step5, ended}
        self.medicine_state = {}
        # 处方级状态: code -> {total, current_index, finalized_codes}
        self.prescription_state = {}
        # 已见过的车1 pharmacist-success(幂等去重,无限连发)
        self.seen_pharmacist_success = set()
        self._lock = asyncio.Lock()

    def _med_key(self, med_id: int, code: str):
        return (med_id, code)

    async def handle_command(self, msg: dict):
        """处理 /rxzy_msg 上的命令(msg 是 publish 消息的 msg 字段)。"""
        data = msg.get("data", "")
        code = msg.get("prescription_code", "")
        med_id = msg.get("medicine_id")
        med_total = msg.get("medicine_total", 0)
        med_index = msg.get("medicine_index", 0)

        if data == "pharmacist-success":
            # 车1 也收 pharmacist-success(结构化9字段,无限连发),只日志一次,不触发流程
            if code not in self.seen_pharmacist_success:
                self.seen_pharmacist_success.add(code)
                log("CAR1", f"收到 pharmacist-success(车1,结构化格式),仅日志不触发流程 "
                    f"(后端会持续连发,已幂等去重)", C.YELLOW)
            return

        if data == "start":
            await self._handle_start(med_id, code, med_total, med_index)
        elif data == "running":
            await self._handle_running(med_id, code, med_total, med_index)
        elif data == "end":
            await self._handle_end(med_id, code, med_total, med_index)
        else:
            log("CAR1", f"未知命令 data={data},忽略", C.GRAY)

    async def _handle_start(self, med_id: int, code: str, med_total: int, med_index: int):
        async with self._lock:
            self.prescription_state.setdefault(code, {"total": med_total, "current_index": med_index})
            self.prescription_state[code]["total"] = med_total
            key = self._med_key(med_id, code)
            st = self.medicine_state.setdefault(key, {"started": False, "step5": False, "ended": False})
            if st["started"]:
                log("CAR1", f"药品{med_id} running-started 已发,跳过(后端重发start,幂等)", C.GRAY)
                return

        log_recv("CAR1", CAR1_CMD_TOPIC, f"start (med_id={med_id}, code={code}, {med_index}/{med_total})")
        # pose: 前往药房(waypoint[1])
        self.pose.set_target(1, "(前往药房)")

        await asyncio.sleep(START_REPLY_DELAY)
        # N2 暂停点:即将上报 running-started(触发 N2_task_confirmed + 语音 car_can_go)
        await self.pause("N2", f"{med_id}_{code}_running-started",
                         "后端等 running-started 最多 30s(15次×2s),请及时继续")
        await self.send(f"{med_id}_{code}_running-started")
        log_node("N2", f"任务确认(药品{med_id},处方{code})")
        st["started"] = True

    async def _handle_running(self, med_id: int, code: str, med_total: int, med_index: int):
        async with self._lock:
            key = self._med_key(med_id, code)
            st = self.medicine_state.setdefault(key, {"started": False, "step5": False, "ended": False})
            if st["step5"]:
                log("CAR1", f"药品{med_id} step5-waiting-end 已发,跳过(后端重发running,幂等)", C.GRAY)
                return

        log_recv("CAR1", CAR1_CMD_TOPIC, f"running (med_id={med_id})")
        is_last = (med_index == med_total) and med_total > 0

        # 中间步骤(每步 STEP_INTERVAL 秒,后端仅展示/记录,不阻塞握手)
        # step1: 前往药房(已在 start 时切 pose)
        await self.send(f"{med_id}_{code}_running-step1-navigate-to-pharmacy")
        await asyncio.sleep(STEP_INTERVAL)

        # step2 + arm-picking: 抓药(触发 N4 抓取中)
        await self.send(f"{med_id}_{code}_running-step2-pick")
        await self.send(f"{med_id}_{code}_arm-picking")
        log_node("N4", f"机械臂抓取中(药品{med_id})")
        await asyncio.sleep(STEP_INTERVAL)

        # step3: 前往病房(pose 切病房 waypoint[2])
        self.pose.set_target(2, "(前往病房)")
        await self.send(f"{med_id}_{code}_running-step3-navigate-doctor")
        await asyncio.sleep(STEP_INTERVAL)

        # step4 + arm-placing: 送药/放药
        await self.send(f"{med_id}_{code}_running-step4-deliver-medicine")
        await self.send(f"{med_id}_{code}_arm-placing")
        await asyncio.sleep(STEP_INTERVAL)

        # step5-waiting-end: 解锁后端阶段3(发 end)
        await self.send(f"{med_id}_{code}_running-step5-waiting-end")
        log("CAR1", f"药品{med_id} 流程执行完毕,已上报 step5-waiting-end(等待后端发 end)", C.CYAN)
        st["step5"] = True

    async def _handle_end(self, med_id: int, code: str, med_total: int, med_index: int):
        async with self._lock:
            key = self._med_key(med_id, code)
            st = self.medicine_state.setdefault(key, {"started": False, "step5": False, "ended": False})
            if st["ended"]:
                # 后端发 end×2,第二次幂等跳过
                return

        log_recv("CAR1", CAR1_CMD_TOPIC, f"end (med_id={med_id})")
        await asyncio.sleep(END_REPLY_DELAY)
        # 药品级 end: 触发 notify_medicine_completed(后端 for 循环取下一药)
        await self.send(f"{med_id}_{code}_end")
        st["ended"] = True

        is_last = (med_index == med_total) and med_total > 0
        if is_last:
            # 末药:发药单级 3 条(arm_end → all_completed → 药单级 end)
            # pose: 返回 HOME(waypoint[4] 经 waypoint[3])
            self.pose.set_target(3, "(返回途经)")
            await asyncio.sleep(LAST_MEDICINE_INTERVAL)

            # N4 暂停点:即将上报 arm_end(触发 N4 完成 + N5 进行中)
            await self.pause("N4", f"{code}_arm_end",
                             "后端等 step5-waiting-end 最多 30s(本步不受超时约束,但请勿久留)")
            await self.send(f"{code}_arm_end")
            log_node("N4", f"取药完成(处方{code}) → N5 扫码出库进行中")
            await asyncio.sleep(LAST_MEDICINE_INTERVAL)

            await self.send(f"{code}_all_completed")
            log_node("N4", f"所有药品已抓取(处方{code})+ 语音 car_already_arrive ×2")
            await asyncio.sleep(LAST_MEDICINE_INTERVAL)

            # pose: 回 HOME
            self.pose.set_target(4, "(回 HOME)")
            await self.send(f"{code}_end")
            log("CAR1", f"处方{code} 药单级 end 已上报 → HIS 处方置 dispensed,车1 阶段完成", C.GREEN)
            log("CAR1", f"等待人工在 HIS 节点3 扫码出库(触发 pharmacist-success → 车2 启动)...", C.CYAN)
        else:
            log("CAR1", f"药品{med_id} 完成,等待后端发下一药 start...", C.CYAN)


# ====================================================================
# 车2 状态机(事件驱动 4 信号)
# ====================================================================

class Car2StateMachine:
    """处理车2 命令,上报 lift-arrive / nurse_arrive。

    脚本在车2 是被动接收 + 2 处主动上报:
      pharmacist-success → 延迟 → lift-arrive
      lift-open → 延迟 → nurse_arrive
      nurse-success×3 → 仅日志(后端发,触发条件是人工节点4扫码)
    """

    def __init__(self, step_mode: bool, pause_fn, send_fn, pose_mover: PoseMover,
                 lift_arrive_delay: float, nurse_arrive_delay: float):
        self.step_mode = step_mode
        self.pause = pause_fn
        self.send = send_fn
        self.pose = pose_mover
        self.lift_arrive_delay = lift_arrive_delay
        self.nurse_arrive_delay = nurse_arrive_delay
        # 处方级状态: code -> {lift_arrive_sent, nurse_arrive_sent, nurse_success_count}
        self.state = defaultdict(lambda: {"lift_arrive_sent": False,
                                          "nurse_arrive_sent": False,
                                          "nurse_success_count": 0,
                                          "lift_arrive_task": None})
        # 已提示过的车1式命令回声处方(用于静默去重)
        self._ignored_echo_codes = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_code(data: str, suffix: str) -> Optional[str]:
        """从 '{code}_pharmacist-success' 等纯字符串提取 code。"""
        if data.endswith(suffix):
            return data[:-len(suffix)]
        return None

    async def handle_command(self, msg: dict):
        """处理 /car02_rxzy_msg 上的命令(msg 是 publish 消息的 msg 字段)。"""
        data = msg.get("data", "")

        # 后端 main.py:71-79 给每辆车都启动了 sender_loop,车2 的 sender 也会轮询
        # approved 处方并发送 start/running/end(结构化车1式命令)。真实车2 ROS 忽略
        # 这些命令,脚本同样静默忽略(每处方仅提示一次,避免每 2s 刷屏)。
        if data in ("start", "running", "end"):
            code = msg.get("prescription_code", "")
            if code and code not in self._ignored_echo_codes:
                self._ignored_echo_codes.add(code)
                log("CAR2", f"车2 sender 主循环轮询回声(处方{code} 的 start/running/end,"
                    f"真实车2 ROS 会忽略,后续静默)", C.GRAY)
            return

        # 4 信号都是纯字符串 {code}_xxx
        if data.endswith("_pharmacist-success"):
            code = self._parse_code(data, "_pharmacist-success")
            await self._handle_pharmacist_success(code)
        elif data.endswith("_lift-across"):
            code = self._parse_code(data, "_lift-across")
            log_recv("CAR2", CAR2_CMD_TOPIC, data)
            log("CAR2", f"收到 lift-across(车2 进梯中,仅日志)", C.YELLOW)
            # pose: 进电梯内(waypoint[2])
            self.pose.set_target(2, "(进电梯)")
        elif data.endswith("_lift-open"):
            code = self._parse_code(data, "_lift-open")
            await self._handle_lift_open(code)
        elif data.endswith("_nurse-success"):
            code = self._parse_code(data, "_nurse-success")
            await self._handle_nurse_success(code)
        else:
            log("CAR2", f"未知命令 data={data},忽略", C.GRAY)

    async def _handle_pharmacist_success(self, code: str):
        if not code:
            return
        async with self._lock:
            st = self.state[code]
            if st["lift_arrive_sent"]:
                # 后端连发期间重复收到,幂等跳过(后端收到 lift-arrive 后会 stop)
                return
            if st["lift_arrive_task"] is not None:
                return  # 已有待执行的延迟任务
            log_recv("CAR2", CAR2_CMD_TOPIC, f"{code}_pharmacist-success")
            log_node("N5→N6", f"药师扫码出库完成(处方{code})→ pharmacist-success 已收到")
            # pose: 前往电梯等待点(waypoint[1])
            self.pose.set_target(1, "(前往电梯)")
            # 启动延迟上报 lift-arrive 的任务
            st["lift_arrive_task"] = asyncio.create_task(self._delayed_lift_arrive(code))

    async def _delayed_lift_arrive(self, code: str):
        try:
            log("CAR2", f"模拟车2 前往电梯,延迟 {self.lift_arrive_delay}s 后上报 lift-arrive...", C.CYAN)
            # N8 暂停点:即将上报 lift-arrive(触发 N7 + 电梯8步编排,连真实ESP32)
            await self.pause("N8", f"{code}_lift-arrive",
                             "即将触发电梯8步编排(真实ESP32开关门/go_floor),请确保 ESP32 已上电")
            await asyncio.sleep(self.lift_arrive_delay)
            async with self._lock:
                self.state[code]["lift_arrive_sent"] = True
            await self.send(f"{code}_lift-arrive")
            log_node("N7", f"车2 已抵达电梯(处方{code})→ 触发后端电梯8步编排")
            log("CAR2", f"等待后端执行电梯8步(开门→关门→go_floor→floor_arrived→到站开门)...", C.CYAN)
        except asyncio.CancelledError:
            pass

    async def _handle_lift_open(self, code: str):
        if not code:
            return
        async with self._lock:
            st = self.state[code]
            if st["nurse_arrive_sent"]:
                return  # 幂等
        log_recv("CAR2", CAR2_CMD_TOPIC, f"{code}_lift-open")
        log_node("N12", f"电梯到站开门,已通知车2 lift-open → 车2 出梯送达中")
        # pose: 前往护士站(waypoint[3])
        self.pose.set_target(3, "(前往护士站)")
        asyncio.create_task(self._delayed_nurse_arrive(code))

    async def _delayed_nurse_arrive(self, code: str):
        try:
            log("CAR2", f"模拟车2 出梯送达,延迟 {self.nurse_arrive_delay}s 后上报 nurse_arrive...", C.CYAN)
            # N12 暂停点(在 lift-open 收到时已记节点),这里再暂停即将上报 nurse_arrive
            await self.pause("N14", f"{code}_nurse_arrive",
                             "即将触发 N14 语音'药物已送达请您确认'×2")
            await asyncio.sleep(self.nurse_arrive_delay)
            async with self._lock:
                self.state[code]["nurse_arrive_sent"] = True
            await self.send(f"{code}_nurse_arrive")
            log_node("N14", f"车2 已抵达护士站(处方{code})→ 语音'药物已送达请您确认'×2")
            log("CAR2", f"等待人工在 HIS 节点4 扫码确认(触发 nurse-success ×3)...", C.CYAN)
        except asyncio.CancelledError:
            pass

    async def _handle_nurse_success(self, code: str):
        if not code:
            return
        async with self._lock:
            st = self.state[code]
            st["nurse_success_count"] += 1
            count = st["nurse_success_count"]
        log_recv("CAR2", CAR2_CMD_TOPIC, f"{code}_nurse-success (第{count}/3次)")
        if count >= 3:
            log_node("N15", f"护士已确认,任务完成(处方{code})")
            # pose: 回 HOME(waypoint[4])
            self.pose.set_target(4, "(回 HOME)")
            log("CAR2", f"处方{code} 车2 全流程完成 ✓", C.GREEN)
            log("", f"{'='*60}", C.GREEN)
            log("", f"  端到端流程完成:处方 {code}", C.GREEN)
            log("", f"{'='*60}", C.GREEN)


# ====================================================================
# rosbridge 服务器(协议骨架 + 4 连接路由 + pose 广播)
# ====================================================================

# subscribers[topic] -> set[ws]:谁订阅了什么(状态消息只推给订阅者)
subscribers: dict = defaultdict(set)
pose_movers = {1: PoseMover(1, CAR1_WAYPOINTS), 2: PoseMover(2, CAR2_WAYPOINTS)}
# 状态机(在 main 中创建)
car1_sm: Optional[Car1StateMachine] = None
car2_sm: Optional[Car2StateMachine] = None


async def publish_to_subscribers(topic: str, data: str):
    """把状态消息推给订阅了该 topic 的所有连接(模拟 rosbridge 订阅过滤)。"""
    msg = json.dumps({"op": "publish", "topic": topic, "msg": {"data": data}})
    targets = list(subscribers.get(topic, set()))
    for ws in targets:
        try:
            await ws.send(msg)
        except Exception:
            pass


async def pause_fn(node: str, msg_to_send: str, timeout_warn: str):
    """暂停模式:关键节点前等回车。全自动模式直接返回。"""
    if not car1_sm or not car1_sm.step_mode:
        return
    log_pause(f"即将上报 {msg_to_send} → 触发 {node}\n⚠️  {timeout_warn}")
    # 用 to_thread 避免阻塞事件循环(input 是同步阻塞)
    user_input = await asyncio.to_thread(input, f"{C.YELLOW}回车继续, q 退出 > {C.RESET}")
    if user_input.strip().lower() == "q":
        log("", "用户退出", C.RED)
        os._exit(0)


async def handler(ws):
    """rosbridge 连接处理:解析 subscribe/publish/advertise。

    注意:后端每轮轮询前会用 check_ros_ws_available() 探活(连上→立即断开,
    不发任何消息),这类探活连接不打印日志,避免刷屏。
    只有发生协议活动(subscribe/advertise/publish)的连接才打印。
    """
    peer = f"{ws.remote_address[0]}:{ws.remote_address[1]}" if ws.remote_address else "?"
    has_activity = False  # 是否发生过协议活动(区分探活连接与真实连接)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                log("ROSBRIDGE", f"非 JSON 消息,忽略: {str(raw)[:80]}", C.GRAY)
                continue

            op = msg.get("op")
            topic = msg.get("topic", "")
            if not has_activity:
                has_activity = True
                log("ROSBRIDGE", f"客户端已连接: {peer}", C.CYAN)

            if op == "subscribe":
                subscribers[topic].add(ws)
                log("ROSBRIDGE", f"{peer} 订阅: {topic}", C.CYAN)
            elif op == "unsubscribe":
                subscribers.get(topic, set()).discard(ws)
            elif op == "advertise":
                log("ROSBRIDGE", f"{peer} advertise: {topic}(sender 连接)", C.CYAN)
            elif op == "publish":
                await _route_publish(topic, msg.get("msg", {}))
            else:
                # 后端连接关闭时会发 unadvertise,静默处理
                pass
    except websockets.ConnectionClosed:
        pass
    finally:
        # 清理该连接的所有订阅
        for topic in list(subscribers.keys()):
            subscribers[topic].discard(ws)
            if not subscribers[topic]:
                subscribers.pop(topic, None)
        if has_activity:
            log("ROSBRIDGE", f"客户端断开: {peer}", C.GRAY)


async def _route_publish(topic: str, msg: dict):
    """按 publish 的 topic 路由命令到对应车状态机。"""
    data = msg.get("data", "")
    if topic == CAR1_CMD_TOPIC:
        # 车1 命令:start/running/end/pharmacist-success(结构化9字段)
        log_recv("CAR1", topic, data)
        if car1_sm:
            await car1_sm.handle_command(msg)
    elif topic == CAR2_CMD_TOPIC:
        # 车2 命令:4 信号(纯字符串,车2 状态机内部打印)
        if car2_sm:
            await car2_sm.handle_command(msg)
    else:
        log("ROSBRIDGE", f"未路由的 publish topic={topic},忽略", C.GRAY)


async def pose_broadcaster():
    """全局 2Hz 推送:向订阅了 pose topic 的连接发送车1/车2 当前坐标。"""
    interval = 1.0 / POSE_HZ
    tick = 0
    while True:
        for car_id, mover in pose_movers.items():
            mover.tick()
            pose_topic = CAR1_POSE_TOPIC if car_id == 1 else CAR2_POSE_TOPIC
            msg = mover.pose_msg()
            targets = list(subscribers.get(pose_topic, set()))
            for ws in targets:
                try:
                    await ws.send(msg)
                except Exception:
                    pass
        tick += 1
        if tick % int(POSE_HZ * 10) == 0:  # 每 10 秒打印一次状态
            log("POSE", f"已推送 {tick} 轮 pose,订阅: "
                f"car01_pose={len(subscribers.get(CAR1_POSE_TOPIC, set()))} "
                f"car02_pose={len(subscribers.get(CAR2_POSE_TOPIC, set()))} "
                f"/car01_pub={len(subscribers.get(CAR1_STATUS_TOPIC, set()))} "
                f"/car02_pub={len(subscribers.get(CAR2_STATUS_TOPIC, set()))}", C.GRAY)
        await asyncio.sleep(interval)


# ====================================================================
# 命令行参数 + main
# ====================================================================

def parse_args():
    p = argparse.ArgumentParser(description="车1/车2 端到端通信测试脚本(模拟 ROS 端)")
    p.add_argument("--step", action="store_true",
                   help="暂停模式:关键节点(N2/N4/N8/N12/N14)前等回车")
    p.add_argument("--auto", action="store_true", default=True,
                   help="全自动模式(默认):各阶段按时序自动推进")
    p.add_argument("--lift-arrive-delay", type=float, default=DEFAULT_LIFT_ARRIVE_DELAY,
                   help=f"收到 pharmacist-success → 上报 lift-arrive 的延迟(秒,默认 {DEFAULT_LIFT_ARRIVE_DELAY})")
    p.add_argument("--nurse-arrive-delay", type=float, default=DEFAULT_NURSE_ARRIVE_DELAY,
                   help=f"收到 lift-open → 上报 nurse_arrive 的延迟(秒,默认 {DEFAULT_NURSE_ARRIVE_DELAY})")
    return p.parse_args()


async def main():
    args = parse_args()
    step_mode = args.step

    print(f"\n{C.CYAN}{C.BOLD}{'='*60}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}  车1/车2 端到端通信测试脚本(模拟 ROS 端){C.RESET}")
    print(f"{C.CYAN}{'='*60}{C.RESET}")
    print(f"{C.CYAN}  模式: {'暂停(关键节点等回车)' if step_mode else '全自动'}{C.RESET}")
    print(f"{C.CYAN}  lift-arrive 延迟: {args.lift_arrive_delay}s{C.RESET}")
    print(f"{C.CYAN}  nurse_arrive 延迟: {args.nurse_arrive_delay}s{C.RESET}")
    print(f"{C.CYAN}  电梯: 连真实 ESP32(脚本不模拟){C.RESET}")
    print(f"{C.CYAN}  HIS 下单/扫码: 人工在 HIS 界面操作{C.RESET}")
    print(f"{C.CYAN}{'='*60}{C.RESET}\n")

    # .env 预检
    if not check_env():
        sys.exit(1)

    # 创建状态机(共享 pause_fn / send_fn)
    global car1_sm, car2_sm

    async def send_car1(status: str):
        log_send("CAR1", CAR1_STATUS_TOPIC, status)
        await publish_to_subscribers(CAR1_STATUS_TOPIC, status)

    async def send_car2(status: str):
        log_send("CAR2", CAR2_STATUS_TOPIC, status)
        await publish_to_subscribers(CAR2_STATUS_TOPIC, status)

    car1_sm = Car1StateMachine(step_mode, pause_fn, send_car1, pose_movers[1])
    car2_sm = Car2StateMachine(step_mode, pause_fn, send_car2, pose_movers[2],
                               args.lift_arrive_delay, args.nurse_arrive_delay)

    log("ROSBRIDGE", f"模拟 rosbridge 启动: ws://{HOST}:{PORT}", C.GREEN)
    log("ROSBRIDGE", "等待后端连接(4 条:车1/车2 各 listener + sender)...", C.CYAN)
    log("ROSBRIDGE", "后端连入后会订阅 /car01_pub、/car02_pub、car01_pose、car02_pose", C.GRAY)
    log("ROSBRIDGE", "并 advertise /rxzy_msg、/car02_rxzy_msg(发送命令)", C.GRAY)
    print()
    log("", "启动后请在 HIS 界面(:3002)下单,脚本将自动模拟车1 取药流程", C.CYAN)
    print()

    async with websockets.serve(handler, HOST, PORT):
        await pose_broadcaster()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[ROSBRIDGE] 已停止{C.RESET}")
