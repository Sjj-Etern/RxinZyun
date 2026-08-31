"""
ROS WebSocket 监听服务（多车支持版）

支持多辆ROS小车，每辆车独立WebSocket连接、独立Topic订阅、独立状态管理。
所有配置通过 .env 文件统一管理（CAR1_*, CAR2_* 前缀）。

向后兼容：保留模块级函数（start_ros_listener, get_ros_state 等），默认操作车1。
"""
import asyncio
import json
import math
import socket
import time
import logging
import pymysql
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

try:
    import websockets
except ImportError:
    websockets = None

from app.core.config import settings, get_ros_ws_url
from app.services.elevator_control import get_elevator_controller
from app.services.workflow_event_service import record_event, get_events_for_prescriptions


def _stage1_finalized(prescription_code: str) -> bool:
    """阶段一（N1-N5）是否已因药师扫码完成而强制闭环。

    判定依据：该处方已存在 N5_scanned_outbound 事件（由 workflow.py
    pharmacist-success-trigger 写入）。闭环后 N4 相关的晚到事件
    （arm-* / all_completed）不再写入，避免 N4 节点被"复活"为 active。
    """
    if not prescription_code:
        return False
    try:
        events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
        return any(e["event_key"] == "N5_scanned_outbound" for e in events)
    except Exception:
        return False

logger = logging.getLogger(__name__)

# lift-across 延迟覆盖（调试用，默认 None 使用 config 值）
_lift_across_delay_override: Optional[int] = None


def set_lift_across_delay_override(seconds: int):
    """动态设置 lift-across → 电梯上楼的串行等待延迟（调试用）"""
    global _lift_across_delay_override
    _lift_across_delay_override = seconds


def get_lift_across_delay_override() -> int:
    """获取当前 lift-across → 电梯上楼串行等待延迟"""
    global _lift_across_delay_override
    if _lift_across_delay_override is not None:
        return _lift_across_delay_override
    return settings.elevator_across_to_go_floor_delay


class ROSListenerState(Enum):
    STOPPED = "stopped"
    CHECKING = "checking"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


# ===== 多车实例注册表 =====
_listeners: dict = {}  # {car_id: RosListener}


def check_port_reachable(host: str, port: int, timeout: int = 5) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"端口检测失败: {e}")
        return False


# ===== 消息解析（共享）=====

def parse_ros_message(data: str) -> Dict[str, Any]:
    if data.startswith("{") and data.endswith("}"):
        try:
            msg = json.loads(data)
            return {
                "status": msg.get("status", ""),
                "prescription_code": msg.get("prescription_code"),
                "medicine_id": msg.get("medicine_id")
            }
        except json.JSONDecodeError:
            pass

    if "|" in data:
        parts = data.split("|")
        return {
            "status": parts[0],
            "prescription_code": parts[1] if len(parts) > 1 else None,
            "medicine_id": None
        }

    parts = data.split("_")

    if len(parts) >= 3:
        try:
            medicine_id_candidate = int(parts[0])
            is_medicine_id = len(parts[0]) <= 5

            if is_medicine_id:
                medicine_id = medicine_id_candidate
                prescription_code = parts[1]
                status = "_".join(parts[2:])
                return {
                    "status": status,
                    "prescription_code": prescription_code,
                    "medicine_id": medicine_id
                }
            else:
                prescription_code = parts[0]
                status = "_".join(parts[1:])
                return {
                    "status": status,
                    "prescription_code": prescription_code,
                    "medicine_id": None
                }
        except ValueError:
            prescription_code = parts[0]
            status = "_".join(parts[1:])
            return {
                "status": status,
                "prescription_code": prescription_code,
                "medicine_id": None
            }

    if len(parts) == 2:
        return {
            "status": parts[1],
            "prescription_code": parts[0],
            "medicine_id": None
        }

    return {
        "status": data,
        "prescription_code": None,
        "medicine_id": None
    }


# ===== 数据库更新（共享）=====

def update_prescription_workflow_db(prescription_code: str, status: str, medicine_id: Optional[int] = None) -> bool:
    try:
        from sqlalchemy import text
        from app.db.session import engine as LOCAL_ENGINE

        with LOCAL_ENGINE.connect() as conn:
            node_updates = get_node_updates_from_status(status, medicine_id)

            # MySQL 方言：prescription_code 有 unique 索引，用 ON DUPLICATE KEY UPDATE 实现 upsert
            upsert_sql = text("""
                INSERT INTO prescription_workflow_state
                (prescription_code, current_node, node2_status, node2_desc,
                 node3_status, node3_desc, node4_status, node4_desc, ros_status, updated_at)
                VALUES (:code, :current_node, :node2_status, :node2_desc,
                        :node3_status, :node3_desc, :node4_status, :node4_desc,
                        :ros_status, NOW())
                ON DUPLICATE KEY UPDATE
                    current_node = VALUES(current_node),
                    node2_status = VALUES(node2_status),
                    node2_desc = VALUES(node2_desc),
                    node3_status = VALUES(node3_status),
                    node3_desc = VALUES(node3_desc),
                    node4_status = VALUES(node4_status),
                    node4_desc = VALUES(node4_desc),
                    ros_status = VALUES(ros_status),
                    updated_at = NOW()
            """)
            conn.execute(upsert_sql, {
                "code": prescription_code,
                "current_node": node_updates["current_node"],
                "node2_status": node_updates["node2_status"],
                "node2_desc": node_updates["node2_desc"],
                "node3_status": node_updates["node3_status"],
                "node3_desc": node_updates["node3_desc"],
                "node4_status": node_updates["node4_status"],
                "node4_desc": node_updates["node4_desc"],
                "ros_status": status,
            })
            conn.commit()

            medicine_info = f", 药品ID={medicine_id}" if medicine_id else ""
            print(f"[成功] 更新处方流程状态: {prescription_code}{medicine_info} -> {status}")
            logger.info(f"已更新处方流程状态: {prescription_code}{medicine_info} -> {status}")
            return True

    except Exception as e:
        print(f"[失败] 更新处方流程状态失败: {e}")
        logger.error(f"更新处方流程状态失败: {e}")
        return False


def update_his_prescription_status(prescription_code: str) -> bool:
    try:
        his_conn = pymysql.connect(
            host=settings.his_mysql_host,
            port=settings.his_mysql_port,
            user=settings.his_mysql_user,
            password=settings.his_mysql_pass,
            database=settings.his_mysql_db,
            charset="utf8mb4",
            connect_timeout=5
        )
        with his_conn.cursor() as his_cursor:
            his_cursor.execute("""
                UPDATE prescriptions
                SET status = 'dispensed'
                WHERE prescription_code = %s AND status IN ('pending', 'approved')
            """, (prescription_code,))
            his_conn.commit()

            affected_rows = his_cursor.rowcount
            if affected_rows > 0:
                print(f"[成功] HIS处方状态更新: {prescription_code} -> dispensed（最后一个药品完成）")
                logger.info(f"HIS处方状态更新: {prescription_code} -> dispensed")
            else:
                print(f"[警告] HIS处方未找到或状态已更新: {prescription_code}")
                logger.warning(f"HIS处方未找到或状态已更新: {prescription_code}")

        his_conn.close()
        return True

    except pymysql.Error as e:
        print(f"[失败] HIS MySQL同步失败: {e}")
        logger.error(f"HIS MySQL同步失败: {e}")
        return False
    except Exception as e:
        print(f"[失败] HIS MySQL同步异常: {e}")
        logger.error(f"HIS MySQL同步异常: {e}")
        return False


def get_node_updates_from_status(status: str, medicine_id: Optional[int] = None) -> Dict[str, Any]:
    medicine_info = ""
    try:
        from app.services.his_sender import _senders
        sender = _senders.get(1)
        if sender and sender.medicine_total > 0:
            current_idx = sender.current_medicine_index + 1
            medicine_info = f"（第{current_idx}/{sender.medicine_total}个药）"
    except Exception:
        pass

    defaults = {
        "current_node": 1,
        "node2_status": "pending",
        "node2_desc": "等待任务启动",
        "node3_status": "pending",
        "node3_desc": "等待扫码复核",
        "node4_status": "pending",
        "node4_desc": "等待站台交互",
    }

    if status == "running-started":
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"任务确认完成{medicine_info}"
    elif status == "running_started":
        defaults["current_node"] = 2
        defaults["node2_status"] = "active"
        defaults["node2_desc"] = f"任务已确认{medicine_info}"
    elif status == "all_completed":
        defaults["current_node"] = 3
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成（所有药品已抓取）"
        defaults["node3_status"] = "active"
        defaults["node3_desc"] = "正在扫码复核"
        defaults["node4_status"] = "pending"
        defaults["node4_desc"] = "等待站台交互"
    elif status in ("running-step1-navigate-to-pharmacy", "running_step1_navigate_to_pharmacy"):
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"任务确认完成{medicine_info}"
    elif status in ("error-step1-cannot-reach-pharmacy", "error_step1_cannot_reach_pharmacy"):
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"任务确认完成{medicine_info}（到达药房失败）"
    elif status in ("running-step2-pick", "running_step2_pick"):
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"任务确认完成{medicine_info}"
    elif status == "arm-picking":
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"机械臂正在抓取{medicine_info}"
    elif status == "arm-placing":
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"机械臂正在放药{medicine_info}"
    elif status == "arm-error":
        defaults["current_node"] = 2
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = f"机械臂执行异常{medicine_info}"
    elif status in ("running-step3-navigate-doctor", "running_step3_navigate_docter"):
        defaults["current_node"] = 3
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "active"
        defaults["node3_desc"] = "前往病房"
    elif status in ("error-step3-cannot-reach-patient-room", "error_step3_cannot_reach_patient_room"):
        defaults["node3_status"] = "active"
        defaults["node3_desc"] = "无法到达病房"
    elif status in ("running-step4-deliver-medicine", "running_step4_deliver_medicine"):
        defaults["current_node"] = 4
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "completed"
        defaults["node3_desc"] = "扫码复合完成"
        defaults["node4_status"] = "active"
        defaults["node4_desc"] = "正在送药"
    elif status in ("running-step5-waiting-end", "running_step5_waiting_end"):
        defaults["current_node"] = 4
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "completed"
        defaults["node3_desc"] = "扫码复合完成"
        defaults["node4_status"] = "active"
        defaults["node4_desc"] = "正在返回起点"
    elif status in ("error-step5-cannot-return-to-home", "error_step5_cannot_return_to_home"):
        defaults["node4_status"] = "active"
        defaults["node4_desc"] = "无法返回起点"
    elif status == "end":
        defaults["current_node"] = 5
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "completed"
        defaults["node3_desc"] = "扫码复合完成"
        defaults["node4_status"] = "completed"
        defaults["node4_desc"] = "站台交互完成"
    elif status == "lift-arrive":
        defaults["current_node"] = 5
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "completed"
        defaults["node3_desc"] = "扫码复合完成"
        defaults["node4_status"] = "completed"
        defaults["node4_desc"] = "电梯已到达目标楼层"
    elif status == "nurse_arrive":
        defaults["current_node"] = 5
        defaults["node2_status"] = "completed"
        defaults["node2_desc"] = "任务确认完成"
        defaults["node3_status"] = "completed"
        defaults["node3_desc"] = "扫码复合完成"
        defaults["node4_status"] = "completed"
        defaults["node4_desc"] = "护士已到达"

    return defaults


# ===== RosListener 类 =====

class RosListener:
    """
    ROS 监听器（每辆ROS小车一个实例）

    每个实例维护独立的：
    - WebSocket 连接
    - 订阅Topic
    - 机器人状态
    - 语音播报状态
    """

    def __init__(self, car_id: int, ws_host: str, ws_port: int, topic: str,
                 send_topic: str, send_msg_type: str,
                 pose_topic: str = ""):
        self.car_id = car_id
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.topic = topic
        self.pose_topic = pose_topic  # 实时坐标 Topic（pose publisher 发布 "x,y"）
        self.send_topic = send_topic
        self.send_msg_type = send_msg_type
        self.ws_url = f"ws://{ws_host}:{ws_port}"

        # 机器人状态
        self.ros_state: Dict[str, Any] = {
            "listener_state": ROSListenerState.STOPPED.value,
            "ws_reachable": False,
            "last_check_time": None,
            "last_message_time": None,
            "current_robot_status": None,
            "current_prescription_code": None,
            "current_medicine_id": None,
            "current_step": 1,
            "steps": [
                {"id": 1, "name": "开具处方", "status": "pending", "desc": "等待处方开具"},
                {"id": 2, "name": "任务确认", "status": "pending", "desc": "等待任务启动"},
                {"id": 3, "name": "扫码复合", "status": "pending", "desc": "等待扫码复核"},
                {"id": 4, "name": "站台交互", "status": "pending", "desc": "等待站台交互"},
            ]
        }

        # 语音播报状态
        self.audio_state: Dict[str, Any] = {
            "car_can_go_triggered": False,
            "car_already_arrive_triggered": False,
            "nurse_arrive_audio_triggered": False,
            "current_prescription_code": None,
        }

        self._nurse_arrive_event = asyncio.Event()

        # 实时坐标缓存（由 pose publisher 通过 rosbridge 推送，2Hz）
        self.latest_pose: Dict[str, Any] = {
            "x": None,
            "y": None,
            "ts": None,                # 最后更新时间（ISO 字符串）
            "listener_state": "stopped",  # stopped / connecting / connected / disconnected
        }

    def _log_tag(self):
        return f"[ROS Listener 车{self.car_id}]"

    def trigger_nurse_arrive_event(self, prescription_code: str = "") -> None:
        """
        由节点4扫码全部确认（POST /workflow/nurse-success-trigger）调用：
        唤醒 8 步编排的 Step7 等待 → 停 lift-open → Step8 发送 nurse-success。
        替代原先车2 nurse_arrive ROS 消息的触发职责。
        """
        tag = self._log_tag()
        print(f"{tag} 节点4扫码全部确认: {prescription_code or '(无处方码)'} → 触发 nurse-success 流程")
        self._nurse_arrive_event.set()

    def get_state(self) -> Dict[str, Any]:
        return self.ros_state.copy()

    # ===== 实时坐标处理 =====

    def get_pose(self) -> Dict[str, Any]:
        """
        返回当前实时坐标缓存（供 /api/v1/robot/pose 使用）。

        小车 WebSocket 未连接（stopped/connecting/disconnected）时，
        自动降级为模拟坐标：沿真实业务路径点匀速巡游（保证不出地图范围），
        并标记 source="mock"；真实车连上后自动恢复 source="real"。
        """
        pose = self.latest_pose.copy()
        if pose.get("listener_state") == "connected" and pose.get("x") is not None:
            pose.setdefault("source", "real")
            return pose
        return self._mock_pose()

    # ===== 模拟坐标兜底（小车不可达时前端地图仍有移动展示）=====

    # 路径点与前端 CadScene .env 的真实业务路径一致（ROS 坐标，米）：
    # 车1: HOME→药房→病房投放→返回途经→HOME；车2: HOME→电梯等待→电梯内→护士站→HOME
    MOCK_WAYPOINTS: Dict[int, list] = {
        1: [(1.56, 0.141), (1.54, -0.39), (0.030, -0.2777), (0.040, 0.227), (1.56, 0.141)],
        2: [(0.30284, -0.225737), (-0.105803, -0.941809),
            (-0.626348, -0.799792), (-0.870578, -1.5837), (0.30284, -0.225737)],
    }
    MOCK_SPEED = 0.15  # 巡游速度（米/秒）
    _mock_t0 = time.monotonic()  # 类属性会被实例读取，起点用首次访问时间近似即可

    def _mock_pose(self) -> Dict[str, Any]:
        """按时间在路径折线上匀速插值，循环巡游。坐标取自真实路径点，不会出图。"""
        waypoints = self.MOCK_WAYPOINTS.get(self.car_id) or [(0.0, 0.0), (0.5, 0.5), (0.0, 0.0)]
        # 各段长度与累计弧长
        seg_lens = [
            math.hypot(waypoints[i + 1][0] - waypoints[i][0],
                       waypoints[i + 1][1] - waypoints[i][1])
            for i in range(len(waypoints) - 1)
        ]
        total = sum(seg_lens) or 1.0
        dist = ((time.monotonic() - self._mock_t0) * self.MOCK_SPEED) % total

        x, y = waypoints[0]
        acc = 0.0
        for i, seg in enumerate(seg_lens):
            if acc + seg >= dist:
                ratio = (dist - acc) / seg if seg else 0.0
                x = waypoints[i][0] + (waypoints[i + 1][0] - waypoints[i][0]) * ratio
                y = waypoints[i][1] + (waypoints[i + 1][1] - waypoints[i][1]) * ratio
                break
            acc += seg

        return {
            "x": round(x, 4),
            "y": round(y, 4),
            "ts": datetime.now().isoformat(),
            "listener_state": self.latest_pose.get("listener_state", "stopped"),
            "source": "mock",
        }

    def handle_pose_message(self, data: str) -> None:
        """
        解析 pose publisher 发来的 "x.xxx,y.yyy" 字符串。
        失败时不覆盖已有坐标（保留上次有效值），仅记录警告。
        """
        tag = self._log_tag()
        try:
            parts = data.split(",")
            if len(parts) != 2:
                logger.warning(f"{tag} pose 数据格式错误（非 x,y）: {data}")
                return
            x = float(parts[0])
            y = float(parts[1])
            self.latest_pose["x"] = x
            self.latest_pose["y"] = y
            self.latest_pose["ts"] = datetime.now().isoformat()
            self.latest_pose["listener_state"] = "connected"
            logger.info(f"{tag} pose 更新: x={x:.3f}, y={y:.3f}")
        except (ValueError, IndexError) as e:
            logger.warning(f"{tag} pose 解析失败: {data}, err={e}")

    # ===== 机器人状态处理 =====

    def handle_robot_status(self, data: str) -> None:
        tag = self._log_tag()
        parsed_msg = parse_ros_message(data)
        status = parsed_msg["status"]
        prescription_code = parsed_msg["prescription_code"]
        medicine_id = parsed_msg.get("medicine_id")

        medicine_info = f", 药品ID={medicine_id}" if medicine_id else ""
        logger.info(f"{tag} 收到 ROS 状态: {status}, 药单编码: {prescription_code}{medicine_info}")

        self.ros_state["last_message_time"] = datetime.now().isoformat()
        self.ros_state["current_robot_status"] = status
        self.ros_state["current_prescription_code"] = prescription_code
        self.ros_state["current_medicine_id"] = medicine_id

        steps = self.ros_state["steps"]

        for step in steps:
            if step["status"] != "completed":
                step["status"] = "pending"

        if status == "running-started":
            self.ros_state["current_step"] = 2
            steps[1]["status"] = "completed"
            steps[1]["desc"] = "任务确认完成"
        elif status == "all_completed":
            self.ros_state["current_step"] = 3
            steps[1]["status"] = "completed"
            steps[1]["desc"] = "任务确认完成（所有药品已抓取）"
            steps[2]["status"] = "active"
            steps[2]["desc"] = "正在扫码复核"
        elif status in ("running-step5-waiting-end", "running_step5_waiting_end"):
            self.ros_state["current_step"] = 4
            steps[1]["status"] = "completed"
            steps[1]["desc"] = "任务确认完成"
            steps[2]["status"] = "completed"
            steps[2]["desc"] = "扫码复合完成"
            steps[3]["status"] = "active"
            steps[3]["desc"] = "正在返回起点"
        elif status == "end":
            self.ros_state["current_step"] = 5
            steps[1]["status"] = "completed"
            steps[1]["desc"] = "任务确认完成"
            steps[2]["status"] = "completed"
            steps[2]["desc"] = "扫码复合完成"
            steps[3]["status"] = "completed"
            steps[3]["desc"] = "站台交互完成"

        if prescription_code:
            update_prescription_workflow_db(prescription_code, status, medicine_id)

    # ===== 语音播报处理 =====

    async def handle_audio_broadcast(self, status: str, prescription_code: str,
                                      medicine_id: Optional[int]) -> None:
        tag = self._log_tag()
        from app.services.audio_service import play_audio_async

        if status in ("running-started", "running_started"):
            if medicine_id is not None and prescription_code:
                if self.audio_state["current_prescription_code"] != prescription_code:
                    self.audio_state["current_prescription_code"] = prescription_code
                    self.audio_state["car_can_go_triggered"] = False
                    self.audio_state["car_already_arrive_triggered"] = False
                    self.audio_state["nurse_arrive_audio_triggered"] = False
                    print(f"{tag} 新单子开始，重置语音播报状态")

                if not self.audio_state["car_can_go_triggered"]:
                    print(f"{tag} 触发语音播报：单子开始（car_can_go）")
                    try:
                        await play_audio_async(settings.audio_id_start)
                        self.audio_state["car_can_go_triggered"] = True
                        print(f"{tag} 语音播报成功：car_can_go")
                    except Exception as audio_err:
                        logger.error(f"语音播报失败: {audio_err}")
                        print(f"{tag} 语音播报失败: {audio_err}")
                else:
                    print(f"{tag} car_can_go 已触发过，不重复播放")
            else:
                logger.info("任务确认 - 触发语音播报")
                try:
                    from app.services.audio_service import trigger_audio_on_task_confirm
                    await trigger_audio_on_task_confirm()
                except Exception as audio_err:
                    logger.error(f"语音播报失败: {audio_err}")

        elif status == "all_completed":
            if prescription_code:
                if not self.audio_state["car_already_arrive_triggered"]:
                    print(f"{tag} 触发语音播报：药单完成（收到 all_completed）")
                    try:
                        print(f"{tag} 播放 audio_id={settings.audio_id_end} (car_already_arrive) - 第1次")
                        await play_audio_async(settings.audio_id_end)
                        print(f"{tag} 等待2秒...")
                        await asyncio.sleep(2)
                        print(f"{tag} 播放 audio_id={settings.audio_id_end} (car_already_arrive) - 第2次")
                        await play_audio_async(settings.audio_id_end)
                        self.audio_state["car_already_arrive_triggered"] = True
                        print(f"{tag} 语音播报成功：car_already_arrive")
                    except Exception as audio_err:
                        logger.error(f"语音播报失败: {audio_err}")
                        print(f"{tag} 语音播报失败: {audio_err}")
                else:
                    print(f"{tag} car_already_arrive 已触发过，不重复播放")

        elif status == "nurse_arrive":
            # 车2到达护士站 → 播报"药物已送达，请您确认"（连播2次，间隔2秒，每处方1轮）
            # 判定逻辑与 all_completed 分支完全一致：要求 prescription_code 非空 + 独立幂等锁
            if prescription_code:
                if not self.audio_state["nurse_arrive_audio_triggered"]:
                    print(f"{tag} 触发语音播报：护士到达（收到 nurse_arrive）")
                    try:
                        print(f"{tag} 播放 audio_id={settings.audio_id_end} (car_already_arrive) - 第1次")
                        await play_audio_async(settings.audio_id_end)
                        print(f"{tag} 等待2秒...")
                        await asyncio.sleep(2)
                        print(f"{tag} 播放 audio_id={settings.audio_id_end} (car_already_arrive) - 第2次")
                        await play_audio_async(settings.audio_id_end)
                        self.audio_state["nurse_arrive_audio_triggered"] = True
                        record_event(prescription_code, "N14_voice_broadcast", "car2", "已播报\"药物已送达，请您确认\"")
                        print(f"{tag} 语音播报成功：nurse_arrive 到达播报")
                    except Exception as audio_err:
                        logger.error(f"语音播报失败: {audio_err}")
                        print(f"{tag} 语音播报失败: {audio_err}")
                else:
                    print(f"{tag} nurse_arrive 播报已触发过，不重复播放")

    # ===== 获取关联的 HIS Sender =====

    def _get_sender(self):
        from app.services.his_sender import _senders
        return _senders.get(self.car_id)

    def _on_msg_task_done(self, task: asyncio.Task) -> None:
        """异步消息处理任务完成回调，用于捕获未处理异常，避免静默失败"""
        tag = self._log_tag()
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"{tag} [错误] 消息处理任务异常（不中断连接）: {e}")
            logger.error(f"消息处理任务异常: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

    # ===== ROS 消息处理 =====

    async def handle_ros_message(self, data: str) -> None:
        tag = self._log_tag()
        parsed_msg = parse_ros_message(data)
        status = parsed_msg["status"]
        prescription_code = parsed_msg["prescription_code"]
        medicine_id = parsed_msg.get("medicine_id")

        if medicine_id == 0:
            print(f"\n{tag} [去0机制] 忽略 medicine_id=0 的消息: {data}")
            return

        self.handle_robot_status(data)

        print(f"\n{tag} 收到消息解析结果:")
        print(f"{tag}   原始消息: {data}")
        print(f"{tag}   status: {status}")
        print(f"{tag}   prescription_code: {prescription_code}")
        print(f"{tag}   medicine_id: {medicine_id}")

        sender = self._get_sender()

        # 通知 HIS Sender
        if status in ("running-started", "running_started"):
            if medicine_id is not None and prescription_code and sender:
                logger.info(f"药品任务启动: ID={medicine_id}, 处方={prescription_code}")
                print(f"{tag} 药品任务启动: ID={medicine_id}, 处方={prescription_code}")
                if self.car_id == 1:
                    record_event(prescription_code, "N2_task_confirmed", "car1", "车1任务已确认")
                try:
                    sender.notify_medicine_started(medicine_id, prescription_code)
                except Exception as sender_err:
                    logger.error(f"通知 HIS Sender 失败: {sender_err}")

        elif status == "all_completed":
            if sender:
                logger.info(f"所有药品完成抓取: {prescription_code}")
                if self.car_id == 1:
                    if _stage1_finalized(prescription_code):
                        logger.info("阶段一已闭环（扫码出库完成），跳过 N4 事件写入")
                    else:
                        record_event(prescription_code, "N4_picking_medicine", "car1", "所有药品已抓取")
                try:
                    sender.notify_all_medicines_completed(prescription_code)
                except Exception as sender_err:
                    logger.error(f"通知 HIS Sender 失败: {sender_err}")

        # 机械臂模块状态（arm-*）：绑定前端 N4 抓取药品节点（过程细分，不驱动业务流程）
        # 文档参考: car01_topic_interface.md 第4节
        # 注意：阶段一闭环（N5 已存在）后不再写入 N4 事件，避免节点被晚到事件"复活"
        elif status == "arm-picking":
            if prescription_code and self.car_id == 1:
                if _stage1_finalized(prescription_code):
                    logger.info(f"阶段一已闭环，忽略机械臂抓取事件: ID={medicine_id}")
                else:
                    logger.info(f"机械臂正在抓取: ID={medicine_id}, 处方={prescription_code}")
                    record_event(prescription_code, "N4_picking_medicine", "car1_arm",
                                 f"机械臂正在抓取（药品ID={medicine_id}）")

        elif status == "arm-placing":
            if prescription_code and self.car_id == 1:
                if _stage1_finalized(prescription_code):
                    logger.info(f"阶段一已闭环，忽略机械臂放药事件: ID={medicine_id}")
                else:
                    logger.info(f"机械臂正在放药: ID={medicine_id}, 处方={prescription_code}")
                    record_event(prescription_code, "N4_picking_medicine", "car1_arm",
                                 f"机械臂正在放药（药品ID={medicine_id}）")

        elif status == "arm-error":
            if prescription_code and self.car_id == 1:
                if _stage1_finalized(prescription_code):
                    logger.info(f"阶段一已闭环，忽略机械臂异常事件: ID={medicine_id}")
                else:
                    logger.warning(f"机械臂执行异常: ID={medicine_id}, 处方={prescription_code}")
                    record_event(prescription_code, "N4_picking_medicine", "car1_arm",
                                 f"机械臂执行异常（药品ID={medicine_id}），详情见车1日志")

        # 机械臂流程结束（药单级）：N4 抓药节点结束，切换至 N5 扫码出库（进行中）
        # 消息格式: {prescription_code}_arm_end（无 medicine_id 前缀，药单级信号）
        elif status == "arm_end":
            if prescription_code and self.car_id == 1:
                logger.info(f"机械臂流程结束（药单级）: 处方={prescription_code}")
                print(f"{tag} 机械臂流程结束（药单级）: {prescription_code}")
                if _stage1_finalized(prescription_code):
                    logger.info("阶段一已闭环（扫码出库完成），忽略 arm_end 事件")
                else:
                    events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
                    existing = {e["event_key"] for e in events}
                    # N1-N3 缺失补记（arm_end 到达即视为前序流程已过）
                    backfill = {
                        "N1_prescription_created": "处方已开具（arm_end 时补记）",
                        "N2_task_confirmed": "任务已确认（arm_end 时补记）",
                        "N3_navigate_pharmacy": "已前往药房（arm_end 时补记）",
                    }
                    for key, detail in backfill.items():
                        if key not in existing:
                            record_event(prescription_code, key, "system", detail)
                    # N4 置为已完成
                    record_event(prescription_code, "N4_picking_medicine", "car1_arm",
                                 "机械臂流程已结束（arm_end）")
                    # N5 置为进行中（等待药师扫码）
                    record_event(prescription_code, "N5_scanned_outbound", "car1_arm",
                                 "扫码出库进行中（等待药师扫码）")

        # 注意：pharmacist-success 不再监听 running-step4-deliver-medicine 节点触发，
        # 改由 HIS 节点3扫码复核完成（所有追溯码出库）后通过
        # POST /api/v1/workflow/pharmacist-success-trigger 通知后端延迟发送。

        elif status == "lift-arrive":
            if prescription_code:
                logger.info(f"电梯到达目标楼层: {prescription_code}")
                print("=" * 60)
                print(f"{tag} 电梯到达目标楼层: {prescription_code}")
                print("=" * 60)
                record_event(prescription_code, "N7_arrived_elevator", "car2", "车2已抵达电梯")

                from app.services.his_sender import _senders as his_senders
                car2_sender = his_senders.get(2)
                if not car2_sender:
                    print(f"{tag} [警告] 车2未注册，无法发送电梯信号")
                    return

                elevator = get_elevator_controller()

                # 在流程开始时清除护士到达信号，避免与 nurse_arrive 的 set() 产生竞态
                # （不能放在 Step 7，否则会清除流程中已 set 的 event 导致死锁）
                self._nurse_arrive_event.clear()

                # 收到 lift-arrive → 立即停止 ① pharmacist-success 连续发送
                await car2_sender.stop_current_signal()
                print(f"{tag} [车2] 已停止 pharmacist-success（收到 lift-arrive）")

                # ===== Step 1: 开门（电梯硬件）=====
                if elevator.is_connected():
                    print(f"{tag} [电梯] 发送开门命令...")
                    try:
                        await elevator.send_open_door()
                        record_event(prescription_code, "N8_elevator_door_open", "elevator", "电梯门已打开")
                        print(f"{tag} [电梯] ✓ 开门完成，等待 {settings.elevator_door_open_delay} 秒...")
                        await asyncio.sleep(settings.elevator_door_open_delay)
                    except Exception as e:
                        print(f"{tag} [电梯] [警告] 开门失败: {e}")
                else:
                    print(f"{tag} [电梯] [警告] ESP32 未连接，跳过开门")

                # ===== Step 2: 通知车2 跨楼（lift-across）=====
                await car2_sender.send_lift_across(prescription_code)
                record_event(prescription_code, "N9_crossing_elevator", "car2", "车2跨梯运输中")
                print(f"{tag} → 车2: lift-across")

                # ===== Step 3: 串行等待（车2进入电梯），时长 .env 可配置 =====
                across_delay = settings.elevator_across_to_go_floor_delay
                print(f"{tag} 等待 {across_delay} 秒（车2进梯，lift-across → 电梯上楼 串行间隔）...")
                await asyncio.sleep(across_delay)

                # ===== Step 4: 关门（电梯硬件）=====
                if elevator.is_connected():
                    print(f"{tag} [电梯] 发送关门命令...")
                    try:
                        await elevator.send_close_door()
                        record_event(prescription_code, "N10_elevator_door_close", "elevator", "电梯门已关闭")
                        print(f"{tag} [电梯] ✓ 关门完成，等待 {settings.elevator_door_close_delay} 秒...")
                        await asyncio.sleep(settings.elevator_door_close_delay)
                    except Exception as e:
                        print(f"{tag} [电梯] [警告] 关门失败: {e}")
                else:
                    print(f"{tag} [电梯] [警告] ESP32 未连接，跳过关门")

                # ===== Step 5: 去目标楼层（电梯硬件），到达后立即发送 lift-open =====
                target_floor = settings.elevator_target_floor
                # 先查询当前楼层，避免重复移动
                if elevator.is_connected():
                    try:
                        status_ack = await elevator.send_status_query()
                        current_floor = status_ack.get("floor", 0)
                        print(f"{tag} [电梯] 当前楼层={current_floor}, 目标楼层={target_floor}")
                        if current_floor != target_floor:
                            print(f"{tag} [电梯] 发送去{target_floor}楼命令...")
                            await elevator.send_go_floor(target_floor)
                            print(f"{tag} [电梯] ✓ 去{target_floor}楼命令已发送")
                            # 监听 ESP32 上报楼层到达（真实时序反馈，非 sleep 估算）
                            print(f"{tag} [电梯] 等待楼层到达上报 (兜底超时 {settings.elevator_floor_arrive_timeout} 秒)...")
                            arrived = await elevator.wait_floor_arrived(settings.elevator_floor_arrive_timeout)
                            if arrived:
                                record_event(prescription_code, "N11_floor_arrived", "elevator", f"电梯已到达{target_floor}楼")
                                print(f"{tag} [电梯] ✓ 已收到楼层到达上报")
                            else:
                                print(f"{tag} [电梯] [警告] 等待楼层到达超时（{settings.elevator_floor_arrive_timeout} 秒），兜底继续流程")
                        else:
                            print(f"{tag} [电梯] 已在{target_floor}楼，无需移动")
                    except Exception as e:
                        print(f"{tag} [电梯] [警告] 楼层移动失败: {e}")
                else:
                    print(f"{tag} [电梯] [警告] ESP32 未连接，跳过楼层移动")

                # ===== Step 5.5: 到达目标楼层后触发电梯开门（硬件）=====
                if elevator.is_connected():
                    print(f"{tag} [电梯] 到达{target_floor}楼，发送开门命令...")
                    try:
                        await elevator.send_open_door()
                        record_event(prescription_code, "N12_lift_open_sent", "elevator",
                                     f"电梯已到{target_floor}楼并开门")
                        print(f"{tag} [电梯] ✓ 开门完成，等待 {settings.elevator_door_open_delay} 秒...")
                        await asyncio.sleep(settings.elevator_door_open_delay)
                    except Exception as e:
                        print(f"{tag} [电梯] [警告] 到楼开门失败: {e}")
                else:
                    print(f"{tag} [电梯] [警告] ESP32 未连接，跳过到楼开门")

                # ===== Step 6: 通知车2 电梯开门（lift-open，到达后无延迟立即发送）=====
                await car2_sender.send_lift_open(prescription_code)
                record_event(prescription_code, "N12_lift_open_sent", "car2", "已通知车2开门送出")
                print(f"{tag} → 车2: lift-open")

                # ===== Step 7: 等待护士到达信号 =====
                print(f"{tag} 等待护士到达信号...")
                await self._nurse_arrive_event.wait()

                # 收到 nurse_arrive → 立即停止 ⑤ lift-open 连续发送
                await car2_sender.stop_current_signal()
                print(f"{tag} [车2] 已停止 lift-open（收到 nurse_arrive）")

                # ===== Step 8: 通知车2 护士确认 =====
                await car2_sender.send_nurse_success(prescription_code)
                record_event(prescription_code, "N15_task_completed", "car2", "护士已确认，任务完成")
                print(f"{tag} → 车2: nurse-success")
                print("=" * 60)

        elif status == "nurse_arrive":
            # 注意：nurse-success 触发条件已改为"节点4扫码全部确认"（HIS 通过
            # POST /workflow/nurse-success-trigger 通知后端），车2 的 nurse_arrive
            # 消息不再触发 Step7/Step8，仅记录日志（语音播报仍由该消息触发）
            if prescription_code:
                logger.info(f"护士已到达: {prescription_code}")
                print(f"{tag} 护士已到达: {prescription_code}（不再触发 nurse-success，由节点4扫码触发）")

        elif status in ("running-step5-waiting-end", "running_step5_waiting_end"):
            if medicine_id is not None and prescription_code and sender:
                print(f"{tag} 进入【药品级消息分支】- 药品完成，触发发送end")
                try:
                    sender.notify_prescription_step5_return(prescription_code, medicine_id)
                except Exception as sender_err:
                    logger.error(f"通知 HIS Sender 失败: {sender_err}")
            elif medicine_id is None and prescription_code:
                print(f"{tag} 收到药单级running-step5-waiting-end，缺少medicine_id，不触发end发送")

        elif status == "end":
            if medicine_id is not None and prescription_code and sender:
                print(f"{tag} 进入【药品级end消息分支】- 药品完成，触发切换")
                try:
                    sender.notify_medicine_completed(medicine_id, prescription_code)
                except Exception as sender_err:
                    logger.error(f"通知 HIS Sender 失败: {sender_err}")
            elif medicine_id is None and prescription_code and sender:
                print(f"{tag} 收到药单级end消息，任务完成")
                try:
                    sender.notify_task_completed(prescription_code)
                except Exception as sender_err:
                    logger.error(f"通知 HIS Sender 失败: {sender_err}")
                print(f"{tag} 所有节点完成，更新HIS处方状态为dispensed")
                update_his_prescription_status(prescription_code)

        await self.handle_audio_broadcast(status, prescription_code, medicine_id)

    # ===== 主循环 =====

    async def listener_loop(self) -> None:
        tag = self._log_tag()
        logger.info(f"{tag} 启动 ROS WebSocket 监听服务，目标: {self.ws_url}")

        while True:
            try:
                ws_reachable = await asyncio.to_thread(check_port_reachable, self.ws_host, self.ws_port, 5)
                self.ros_state["ws_reachable"] = ws_reachable
                self.ros_state["last_check_time"] = datetime.now().isoformat()

                if not ws_reachable:
                    self.ros_state["listener_state"] = ROSListenerState.DISCONNECTED.value
                    self.latest_pose["listener_state"] = "disconnected"
                    logger.warning(f"{tag} ROS WebSocket 端口不可达: {self.ws_url}")
                    await asyncio.sleep(settings.ros_check_interval)
                    continue

                self.ros_state["listener_state"] = ROSListenerState.CONNECTING.value
                logger.info(f"{tag} 正在连接 ROS WebSocket: {self.ws_url}")

                try:
                    async with websockets.connect(self.ws_url) as ws:
                        self.ros_state["listener_state"] = ROSListenerState.CONNECTED.value
                        self.latest_pose["listener_state"] = "connected"
                        logger.info(f"{tag} 已连接 Ros WebSocket: {self.ws_url}")
                        print(f"[成功] {tag} 已连接 Ros WebSocket: {self.ws_url}")

                        subscribe_msg = json.dumps({
                            "op": "subscribe",
                            "topic": self.topic,
                            "type": "std_msgs/String"
                        })
                        await ws.send(subscribe_msg)
                        print(f"{tag} [订阅] 已发送订阅请求: topic={self.topic}, type=std_msgs/String")

                        # 订阅 pose topic（实时坐标，如果有配置）
                        if self.pose_topic:
                            pose_subscribe_msg = json.dumps({
                                "op": "subscribe",
                                "topic": self.pose_topic,
                                "type": "std_msgs/String"
                            })
                            await ws.send(pose_subscribe_msg)
                            print(f"{tag} [订阅] 已发送 pose 订阅请求: topic={self.pose_topic}")

                        try:
                            confirm = await asyncio.wait_for(ws.recv(), timeout=3)
                            print(f"{tag} [订阅] rosbridge 确认: {confirm}")
                        except asyncio.TimeoutError:
                            print(f"{tag} [订阅] 等待确认超时（3秒），继续监听消息...")
                        except Exception as e:
                            print(f"{tag} [订阅] 读取确认异常: {e}，继续监听消息...")

                        while True:
                            try:
                                message = await asyncio.wait_for(
                                    ws.recv(),
                                    timeout=settings.ros_check_interval
                                )
                                msg_data = json.loads(message)
                                print(f"{tag} 收到原始消息: {message[:200]}")

                                if "msg" in msg_data and "data" in msg_data["msg"]:
                                    data = msg_data["msg"]["data"]
                                    msg_topic = msg_data.get("topic", "")

                                    # 按 topic 分流：pose 消息同步解析（轻量），状态消息异步处理
                                    if self.pose_topic and msg_topic == self.pose_topic:
                                        print(f"{tag} [收到] pose 消息: {data}")
                                        self.handle_pose_message(data)
                                    else:
                                        print(f"{tag} [收到] ROS 状态消息: {data}")
                                        try:
                                            # 异步处理消息，避免 lift-arrive 的 Step 7 等待 nurse_arrive 时
                                            # 阻塞主循环，导致 nurse_arrive 消息无法被接收（死锁）
                                            task = asyncio.create_task(self.handle_ros_message(data))
                                            task.add_done_callback(self._on_msg_task_done)
                                        except Exception as msg_err:
                                            print(f"{tag} [错误] 创建消息处理任务失败（不中断连接）: {msg_err}")
                                            logger.error(f"创建消息处理任务失败: {msg_err}", exc_info=True)
                                else:
                                    print(f"{tag} [警告] 消息格式不符合预期，已跳过")

                            except asyncio.TimeoutError:
                                try:
                                    await ws.ping()
                                except Exception as ping_err:
                                    print(f"{tag} [警告] WebSocket ping 失败: {ping_err}")
                                    logger.warning(f"WebSocket ping 失败: {ping_err}")
                                    break

                            except websockets.exceptions.ConnectionClosed as close_err:
                                print(f"{tag} [警告] WebSocket 连接已关闭: {close_err}")
                                logger.warning(f"WebSocket 连接已关闭: {close_err}")
                                break

                except Exception as conn_err:
                    self.ros_state["listener_state"] = ROSListenerState.RECONNECTING.value
                    print(f"{tag} [错误] WebSocket 连接失败: {conn_err}")
                    logger.error(f"WebSocket 连接失败: {conn_err}")

                print(f"{tag} 等待 {settings.ros_check_interval} 秒后重连...")
                logger.info(f"{tag} 等待 {settings.ros_check_interval} 秒后重连...")
                await asyncio.sleep(settings.ros_check_interval)

            except asyncio.CancelledError:
                logger.info(f"{tag} ROS WebSocket 监听任务被取消")
                self.ros_state["listener_state"] = ROSListenerState.STOPPED.value
                break

            except Exception as e:
                logger.error(f"{tag} ROS 监听异常: {e}")
                self.ros_state["listener_state"] = ROSListenerState.RECONNECTING.value
                await asyncio.sleep(settings.ros_check_interval)

    async def start(self) -> None:
        tag = self._log_tag()
        print("=" * 60)
        print(f"{tag} ROS WebSocket 监听服务启动中...")
        print(f"{tag} 支持消息格式：{{medicine_id}}_{{prescription_code}}_{{status}}")
        print(f"{tag} 订阅Topic: {self.topic}")
        print("=" * 60)
        logger.info(f"{tag} 启动 ROS WebSocket 监听服务...")
        await self.listener_loop()


# ===== 工厂函数 =====

def create_listener(car_id: int, ws_host: str, ws_port: int, topic: str,
                    send_topic: str, send_msg_type: str,
                    pose_topic: str = "") -> RosListener:
    listener = RosListener(car_id, ws_host, ws_port, topic,
                           send_topic, send_msg_type, pose_topic=pose_topic)
    _listeners[car_id] = listener
    return listener


def get_listener(car_id: int = 1) -> RosListener:
    return _listeners.get(car_id)


# ===== 向后兼容的模块级函数 =====

# 全局状态（向后兼容，映射到车1）
_ros_state: Dict[str, Any] = {
    "listener_state": ROSListenerState.STOPPED.value,
    "ws_reachable": False,
    "last_check_time": None,
    "last_message_time": None,
    "current_robot_status": None,
    "current_prescription_code": None,
    "current_medicine_id": None,
    "current_step": 1,
    "steps": [
        {"id": 1, "name": "开具处方", "status": "pending", "desc": "等待处方开具"},
        {"id": 2, "name": "任务确认", "status": "pending", "desc": "等待任务启动"},
        {"id": 3, "name": "扫码复合", "status": "pending", "desc": "等待扫码复核"},
        {"id": 4, "name": "站台交互", "status": "pending", "desc": "等待站台交互"},
    ]
}

_audio_state: Dict[str, Any] = {
    "car_can_go_triggered": False,
    "car_already_arrive_triggered": False,
    "current_prescription_code": None,
}


def get_ros_state() -> Dict[str, Any]:
    listener = _listeners.get(1)
    if listener:
        return listener.get_state()
    return _ros_state.copy()


async def start_ros_listener() -> None:
    """启动 ROS 监听服务（车1，向后兼容）"""
    car_configs = settings.get_car_configs()
    car1 = car_configs[0]
    listener = create_listener(
        car_id=1,
        ws_host=car1["ws_host"],
        ws_port=car1["ws_port"],
        topic=car1["topic"],
        send_topic=car1["send_topic"],
        send_msg_type=car1["send_msg_type"],
    )
    await listener.start()