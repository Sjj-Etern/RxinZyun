"""
HIS 处方自动发送服务（多车支持版）

支持多辆ROS小车，每辆车独立WebSocket连接、独立Topic、独立状态管理。
所有配置通过 .env 文件统一管理（CAR1_*, CAR2_* 前缀）。

向后兼容：保留模块级函数（start_his_sender, stop_his_sender, get_sender_status,
notify_* 等），默认操作车1。

【通信工程师负责】HIS 处方/坐标查询、ROS WebSocket Topic 生命周期、
任务信号发布，以及机器人回执驱动的重发与同步。
"""
import asyncio
import json
import time
import pymysql
import websockets
from typing import Optional
from app.core.config import settings
from app.services.workflow_event_service import record_event, get_events_for_prescriptions

# HIS 数据库连接配置（共享）
HIS_DB_CONFIG = {
    "host": settings.his_mysql_host,
    "port": settings.his_mysql_port,
    "user": settings.his_mysql_user,
    "password": settings.his_mysql_pass,
    "database": settings.his_mysql_db,
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

SEND_INTERVAL = 2  # 发送间隔（秒）
POLL_INTERVAL = 2  # 轮询间隔（秒）

# ===== 多车实例注册表 =====
_senders: dict = {}  # {car_id: HisSender}


# ===== 数据库查询函数（共享，不依赖小车实例）=====

def get_latest_pending_prescription():
    """
    从 HIS 数据库获取最新待处理的处方编码（附下单时间，用于删除重下自愈判定）
    返回 (prescription_code, created_at) 或 None
    """
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT prescription_code, id, created_at
                FROM prescriptions
                WHERE status = 'approved'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            """)
            result = cursor.fetchone()

            if result:
                prescription_code = result["prescription_code"]
                return prescription_code, result["created_at"]
            else:
                return None, None
    except Exception as e:
        print(f"[HIS Sender] 查询 HIS 数据库失败: {e}")
        return None, None
    finally:
        if 'conn' in locals():
            conn.close()


def check_prescription_exists(prescription_code: str) -> bool:
    """检查指定处方是否仍在 HIS 数据库中（任意状态）。

    用于发送循环中定期检查药单是否被删除，防止药单删除后持续发送信号。
    查询失败时保守返回 True，避免网络抖动误停发送。
    """
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM prescriptions WHERE prescription_code = %s LIMIT 1",
                (prescription_code,)
            )
            return cursor.fetchone() is not None
    except Exception as e:
        print(f"[HIS Sender] [WARN] 检查处方存在性失败: {e}，默认继续发送")
        return True
    finally:
        if 'conn' in locals():
            conn.close()


def purge_stale_events_if_reordered(prescription_code: str, created_at) -> int:
    """删除重下自愈：处方码复用时自动清理上一轮的旧节点事件。

    判定：该处方在 workflow_events 已有事件，但 HIS 中该处方的 created_at（本轮下单时间）
    晚于全部旧事件的最大 created_at → 说明旧事件属于"删除前"的上一轮，本轮是同号新单。
    自动清空旧事件（含 prescription_workflow_state 旧表记录与幂等集合），
    避免大屏显示"全部完成"且重入防护误判"阶段一已闭环"而不发 start。
    返回删除的事件条数（0 表示无需清理）。
    """
    try:
        from app.services.workflow_event_service import (
            get_events_for_prescriptions, delete_events_for_prescription
        )
        events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
        if not events or created_at is None:
            return 0
        max_event_time = max(e["created_at"] for e in events)
        if created_at <= max_event_time:
            # 旧事件不早于本轮下单时间 → 同一轮的正常事件（后端重启恢复场景），保留
            return 0
        print(f"[HIS Sender] 检测到处方 {prescription_code} 为删除后重下（下单时间晚于旧事件），"
              f"自动清理旧节点事件 {len(events)} 条")
        return delete_events_for_prescription(prescription_code)
    except Exception as e:
        print(f"[HIS Sender] [警告] 删除重下自愈检查失败（不影响发送）: {e}")
        return 0


def get_prescription_medicine_locations(prescription_code: str) -> list:
    """
    根据处方编码查询该处方开具的所有药品的坐标

    查询路径：prescriptions -> prescription_items -> medicine_locations
    """
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        with conn.cursor() as cursor:
            sql_query = """
                SELECT
                    pi.medicine_id,
                    MIN(ml.x) as x,
                    MIN(ml.y) as y,
                    MIN(ml.z) as z,
                    MIN(ml.yaw) as yaw
                FROM prescriptions p
                JOIN prescription_items pi ON p.id = pi.prescription_id
                JOIN medicine_locations ml ON pi.medicine_id = ml.medicine_id
                WHERE p.prescription_code = %s
                GROUP BY pi.medicine_id
                ORDER BY pi.medicine_id ASC
            """
            cursor.execute(sql_query, (prescription_code,))
            results = cursor.fetchall()

            if results:
                medicine_list = []
                for row in results:
                    medicine_id_value = row["medicine_id"]
                    if medicine_id_value is None or medicine_id_value == 0:
                        continue

                    medicine_list.append({
                        "medicine_id": int(medicine_id_value),
                        "x": float(row["x"]) if row["x"] is not None else 0.0,
                        "y": float(row["y"]) if row["y"] is not None else 0.0,
                        "z": float(row["z"]) if row["z"] is not None else 0.0,
                        "yaw": float(row["yaw"]) if row["yaw"] is not None else 0.0
                    })
                return medicine_list
            else:
                return []
    except Exception as e:
        print(f"[HIS Sender] 查询药品坐标失败: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()


# ===== HisSender 类 =====

class HisSender:
    """
    HIS 处方发送器（每辆ROS小车一个实例）

    每个实例维护独立的：
    - WebSocket 连接
    - 发送Topic
    - 药品发送状态
    - 事件通知
    """

    def __init__(self, car_id: int, ws_host: str, ws_port: int, send_topic: str, send_msg_type: str):
        self.car_id = car_id
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.send_topic = send_topic
        self.send_msg_type = send_msg_type
        self.ws_url = f"ws://{ws_host}:{ws_port}"

        # 事件
        self.started_event = None
        self.step5_return_event = None
        self.medicine_completed_event = None
        self.all_completed_event = None
        self.task_end_event = None

        # 状态
        self.current_prescription_code = None
        self.last_sent_code = None
        self.sender_running = False
        self.ws_connection = None

        # 药品发送相关
        self.medicine_list = []
        self.current_medicine_index = 0
        self.medicine_total = 0
        self.medicine_send_count = {}
        self.medicine_started = {}
        self.all_medicines_completed = False
        self.task_completed = False

        # 发送失败已放弃的处方集合（内存级；后端重启后清空，重入防护改由 DB 事件兜底）
        self._failed_prescriptions = set()
        # 当前处方的 HIS 下单时间（datetime，用于"删除后同单号重下"检测）
        self._prescription_taken_at = None
        self._prescription_taken_at_str = "-"

        # 预期上下文
        self.expected_medicine_id = None
        self.expected_prescription_code = None

        # 车2 信号发送状态（pharmacist-success / lift-across 连发；lift-open / nurse-success 限次发送）
        self._continuous_send_task: Optional[asyncio.Task] = None
        self._continuous_stop_event: Optional[asyncio.Event] = None
        self._continuous_signal_name: Optional[str] = None

    def _init_events(self):
        self.started_event = asyncio.Event()
        self.step5_return_event = asyncio.Event()
        self.medicine_completed_event = asyncio.Event()
        self.all_completed_event = asyncio.Event()
        self.task_end_event = asyncio.Event()

    def _log_tag(self):
        return f"[HIS Sender 车{self.car_id}]"

    # ===== WebSocket 连接管理 =====

    async def _ensure_ws_connection(self):
        tag = self._log_tag()
        need = False
        if self.ws_connection is None:
            need = True
        else:
            try:
                if hasattr(self.ws_connection, 'open') and not self.ws_connection.open:
                    need = True
                elif hasattr(self.ws_connection, 'closed') and self.ws_connection.closed:
                    need = True
            except:
                need = True

        if need:
            if self.ws_connection is not None:
                try:
                    await self.ws_connection.close()
                except:
                    pass

            self.ws_connection = await asyncio.wait_for(
                websockets.connect(self.ws_url, proxy=None),
                timeout=settings.ros_connect_timeout
            )

            await self.ws_connection.send(json.dumps({
                "op": "unadvertise",
                "topic": self.send_topic
            }))
            await asyncio.sleep(0.1)

            await self.ws_connection.send(json.dumps({
                "op": "advertise",
                "topic": self.send_topic,
                "type": self.send_msg_type
            }))
            await asyncio.sleep(0.3)
            print(f"{tag} Topic 注册成功: {self.send_topic} ({self.send_msg_type})")

    async def check_ros_ws_available(self):
        tag = self._log_tag()
        try:
            ws = await asyncio.wait_for(
                websockets.connect(self.ws_url, proxy=None),
                timeout=settings.ros_connect_timeout
            )
            await ws.close()
            return True
        except Exception as e:
            print(f"{tag} ROS WebSocket 不可达: {self.ws_url} - {e}")
            return False

    # ===== 车2 信号连续发送 =====
    # 4 个车2信号共用发送循环，每 car2_signal_interval 秒重发一次。
    # pharmacist-success / lift-across 由回执或信号切换停止；
    # lift-open / nurse-success 无直接回执，最多发送 3 次，避免等待人工扫码期间无限发送。

    async def _publish_signal_once(self, message: str, msg_fields: Optional[dict] = None) -> bool:
        """发送一次信号。
        - msg_fields=None：纯字符串 data 载荷（信息拼在 data 内，车2 4 信号用）
        - msg_fields=dict：结构化载荷（data + prescription_code，车1 pharmacist-success 用，格式参考 start）
        """
        tag = self._log_tag()
        try:
            await self._ensure_ws_connection()
            if msg_fields is not None:
                # 自定义格式（参考 start 消息）：msg 内含 data + prescription_code
                msg_payload = {"data": message}
                msg_payload.update(msg_fields)
            else:
                msg_payload = {"data": message}
            message_dict = {
                "op": "publish",
                "topic": self.send_topic,
                "msg": msg_payload,
            }
            await self.ws_connection.send(json.dumps(message_dict))
            return True
        except Exception as e:
            print(f"{tag} [连续发送] 发送失败: {e}")
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                except:
                    pass
                self.ws_connection = None
            return False

    async def _start_continuous_send(self, signal_name: str, message: str,
                                    max_sends: Optional[int] = None,
                                    msg_fields: Optional[dict] = None) -> None:
        """
        启动一个信号的连续发送。会先停掉当前正在发送的信号（信号改变即停）。
        - max_sends=None：持续发送，直到 stop_current_signal() 或下一个信号切换
        - max_sends=N：发送 N 次后自动停止（用于末位信号 nurse-success）
        - msg_fields=dict：使用结构化载荷（车1 pharmacist-success 自定义格式）
        """
        tag = self._log_tag()
        await self._stop_continuous_send()

        stop_event = asyncio.Event()
        self._continuous_stop_event = stop_event
        self._continuous_signal_name = signal_name
        self._continuous_send_task = asyncio.create_task(
            self._continuous_send_loop(signal_name, message, stop_event, max_sends, msg_fields)
        )

    async def _stop_continuous_send(self) -> None:
        """停止当前连续发送的信号，并清理状态"""
        if self._continuous_stop_event is not None:
            self._continuous_stop_event.set()
        task = self._continuous_send_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
            except Exception:
                pass
        self._continuous_send_task = None
        self._continuous_stop_event = None
        self._continuous_signal_name = None

    async def _continuous_send_loop(self, signal_name: str, message: str,
                                   stop_event: asyncio.Event,
                                   max_sends: Optional[int],
                                   msg_fields: Optional[dict] = None) -> None:
        tag = self._log_tag()
        interval = settings.car2_signal_interval
        count = 0
        try:
            while not stop_event.is_set():
                if max_sends is not None and count >= max_sends:
                    break
                count += 1
                ok = await self._publish_signal_once(message, msg_fields)
                print(f"{tag} [发送] {signal_name} 第{count}次 {'✓' if ok else '✗'}")
                if max_sends is not None and count >= max_sends:
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            print(f"{tag} [停止] {signal_name}（共发送{count}次）")

    async def stop_current_signal(self) -> None:
        """停止当前正在连续发送的车2 信号（对外接口，用于收到对应回执时立即停）"""
        await self._stop_continuous_send()

    # ===== 消息发送 =====

    async def send_medicine_to_ros(self, prescription_code: str, medicine_data: dict,
                                    medicine_index: int, medicine_total: int, data: str = None):
        tag = self._log_tag()
        try:
            medicine_id = medicine_data["medicine_id"]

            if data is None:
                is_started = self.medicine_started.get(medicine_id, False)
                data = "running" if is_started else "start"

            self.medicine_send_count[medicine_id] = self.medicine_send_count.get(medicine_id, 0) + 1

            await self._ensure_ws_connection()

            message_dict = {
                "op": "publish",
                "topic": self.send_topic,
                "msg": {
                    "data": data,
                    "prescription_code": prescription_code,
                    "medicine_id": medicine_id,
                    "x": medicine_data["x"],
                    "y": medicine_data["y"],
                    "z": medicine_data["z"],
                    "yaw": medicine_data["yaw"],
                    "medicine_total": medicine_total,
                    "medicine_index": medicine_index
                }
            }
            message = json.dumps(message_dict)

            print(f"{tag} [发送] {data} | 处方={prescription_code} | 药品ID={medicine_id} | 坐标=({medicine_data['x']},{medicine_data['y']},{medicine_data['z']},{medicine_data['yaw']})")

            await self.ws_connection.send(message)
            return True

        except Exception as e:
            print(f"{tag} 发送失败: {e}")
            import traceback
            traceback.print_exc()
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                except:
                    pass
                self.ws_connection = None
            return False

    async def send_medicine_end_to_ros(self, prescription_code: str, medicine_data: dict,
                                        medicine_index: int, medicine_total: int):
        tag = self._log_tag()
        try:
            medicine_id = medicine_data["medicine_id"]
            await self._ensure_ws_connection()
            ack_event = (
                self.all_completed_event
                if medicine_index == medicine_total
                else self.medicine_completed_event
            )
            ack_event.clear()

            for send_count in range(2):
                message_dict = {
                    "op": "publish",
                    "topic": self.send_topic,
                    "msg": {
                        "data": "end",
                        "prescription_code": prescription_code,
                        "medicine_id": medicine_id,
                        "x": medicine_data["x"],
                        "y": medicine_data["y"],
                        "z": medicine_data["z"],
                        "yaw": medicine_data["yaw"],
                        "medicine_total": medicine_total,
                        "medicine_index": medicine_index
                    }
                }
                message = json.dumps(message_dict)

                print(f"{tag} [发送] end | 处方={prescription_code} | 药品ID={medicine_id}")

                await self.ws_connection.send(message)
                try:
                    await asyncio.wait_for(ack_event.wait(), timeout=SEND_INTERVAL)
                    return True
                except asyncio.TimeoutError:
                    if send_count == 0:
                        print(f"{tag} [超时] 未收到 end 回执，重发一次")

            print(f"{tag} [错误] end 重发后仍未收到回执")
            return False

        except Exception as e:
            print(f"{tag} 发送 end 消息失败: {e}")
            import traceback
            traceback.print_exc()
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                except:
                    pass
                self.ws_connection = None
            return False

    # ===== 状态管理 =====

    def reset_medicine_state(self, prescription_code: str):
        tag = self._log_tag()
        print("=" * 60)
        print(f"{tag} 重置药品发送状态")
        print(f"{tag} 处方编码: {prescription_code}")

        self.medicine_list = get_prescription_medicine_locations(prescription_code)
        self.medicine_total = len(self.medicine_list)

        if self.medicine_total == 0:
            print(f"{tag} WARNING: 处方 {prescription_code} 的药品列表为空")
            print("=" * 60)
            return

        self.current_medicine_index = 0
        self.medicine_send_count = {}
        for medicine in self.medicine_list:
            self.medicine_send_count[medicine["medicine_id"]] = 0

        self.medicine_started = {}
        for medicine in self.medicine_list:
            self.medicine_started[medicine["medicine_id"]] = False

        self.all_medicines_completed = False
        self.task_completed = False

    # ===== 电梯跨楼信号 =====

    async def send_lift_across(self, prescription_code: str):
        """启动 lift-across 连续发送（收到 lift-arrive 后调用；启动时自动停①，⑤启动时自动停本信号）"""
        tag = self._log_tag()
        message = f"{prescription_code}_lift-across"
        print(f"{tag} [发送] lift-across | 处方={prescription_code}")
        await self._start_continuous_send("lift-across", message, max_sends=None)

    async def send_lift_open(self, prescription_code: str):
        """发送 lift-open 3 次（到站开门后调用；启动时自动停止 lift-across）"""
        tag = self._log_tag()
        message = f"{prescription_code}_lift-open"
        print(f"{tag} [发送] lift-open | 处方={prescription_code}")
        await self._start_continuous_send("lift-open", message, max_sends=3)

    async def send_nurse_success(self, prescription_code: str):
        """启动 nurse-success 连续发送（收到 nurse_arrive 后调用；末位信号，发 3 次自动停）"""
        tag = self._log_tag()
        message = f"{prescription_code}_nurse-success"
        print(f"{tag} [发送] nurse-success | 处方={prescription_code}")
        await self._start_continuous_send("nurse-success", message, max_sends=3)

    # ===== 药师审核通过信号 =====

    async def send_pharmacist_success(self, medicine_id: int, prescription_code: str):
        """
        发送 pharmacist-success。
        - 车2：纯字符串 data（信息拼在 data 内），连续发送（2s 间隔），收到 lift-arrive 后由调用方停
        - 车1：格式与 start 消息完全一致（9 字段一个不少），
               data="pharmacist-success"，药品字段取当前处理中的药品上下文，无上下文时填 0；
               只发一遍（无回执停止机制，连发会无限刷屏），失败时重试，最多 3 次
        """
        tag = self._log_tag()
        if self.car_id == 1:
            # 车1：单发+失败重试（最多 3 次，间隔 2s），成功即停
            message = "pharmacist-success"
            md = None
            if 0 <= self.current_medicine_index < len(self.medicine_list):
                md = self.medicine_list[self.current_medicine_index]
            msg_fields = {
                "prescription_code": prescription_code,
                "medicine_id": (md or {}).get("medicine_id", 0),
                "x": (md or {}).get("x", 0.0),
                "y": (md or {}).get("y", 0.0),
                "z": (md or {}).get("z", 0.0),
                "yaw": (md or {}).get("yaw", 0.0),
                "medicine_total": self.medicine_total,
                "medicine_index": self.current_medicine_index + 1 if md else 0,
            }
            for attempt in range(1, 4):
                ok = await self._publish_signal_once(message, msg_fields)
                print(f"{tag} [发送] pharmacist-success 第{attempt}次 {'✓' if ok else '✗'}")
                if ok:
                    return
                if attempt < 3:
                    await asyncio.sleep(settings.car2_signal_interval)
            print(f"{tag} [错误] pharmacist-success 发送3次均失败")
            return
        # 车2：纯字符串 data（信息拼在 data 内），连续发送，收到 lift-arrive 后由调用方停
        message = f"{prescription_code}_pharmacist-success"
        print(f"{tag} [发送] pharmacist-success | 处方={prescription_code}")
        await self._start_continuous_send("pharmacist-success", message, max_sends=None)

    async def _wait_receipt_silently(self, event: asyncio.Event, timeout: int,
                                      desc: str, prescription_code: str = None) -> bool:
        """重发上限后停止发送，静默等待回执（每30s打印一次等待心跳）。

        解耦"重发上限"与"回执等待时长"：真实车1 从 running 到 step5 耗时可能超过
        重发窗口（15次×2s=30s），重发上限只防无限发送，不应截断等待。
        重发上限到达后停止发送、继续等待；回执到达返回 True，超时返回 False。
        """
        tag = self._log_tag()
        start = time.time()
        deadline = start + timeout
        last_beat = start
        check_count = 0
        while not event.is_set() and self.sender_running:
            if time.time() >= deadline:
                print(f"{tag} [ERROR] 静默等待 {desc} 超时（{timeout}s），放弃本处方")
                return False
            await asyncio.sleep(1)
            # 每30秒检查一次药单是否被删除
            check_count += 1
            if prescription_code and check_count % 30 == 0:
                if not check_prescription_exists(prescription_code):
                    print(f"{tag} [停止] 处方 {prescription_code} 已删除，结束本次任务")
                    return False
            now = time.time()
            if now - last_beat >= 30:
                print(f"{tag} 静默等待回执: {desc}（已等待 {int(now - start)}s/{timeout}s）")
                last_beat = now
        return event.is_set() and self.sender_running

    # ===== 核心：顺序处理单个药品 =====

    async def process_single_medicine(self, medicine_data: dict, prescription_code: str,
                                       medicine_index: int, medicine_total: int):
        tag = self._log_tag()
        medicine_id = medicine_data["medicine_id"]
        self.expected_medicine_id = medicine_id

        self.started_event.clear()
        self.step5_return_event.clear()

        # 阶段1：发送 start，等待 running-started（重发上限后停止发送、静默等待回执）
        max_attempts = settings.medicine_send_max_attempts
        receipt_wait_timeout = settings.medicine_receipt_wait_timeout
        send_count = 0
        PRESCRIPTION_CHECK_INTERVAL = 3  # 每发送3次检查一次药单是否仍存在
        while not self.started_event.is_set() and self.sender_running:
            if send_count >= max_attempts:
                print(f"{tag} [警告] start重发超过上限{max_attempts}次，转入静默等待")
                break
            # 每隔 N 次发送检查药单是否被删除
            if send_count > 0 and send_count % PRESCRIPTION_CHECK_INTERVAL == 0:
                if not check_prescription_exists(prescription_code):
                    print(f"{tag} [停止] 处方{prescription_code}已删除，停止发送start")
                    return False
            send_count += 1
            await self.send_medicine_to_ros(
                prescription_code, medicine_data, medicine_index, medicine_total, "start"
            )
            try:
                await asyncio.wait_for(self.started_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.sender_running:
            return False

        if not self.started_event.is_set():
            # 重发上限已到但回执未达：停止发送，静默等待回执（真实车1 到达时间可能远超重发窗口）
            if not await self._wait_receipt_silently(
                    self.started_event, receipt_wait_timeout,
                    f"running-started（处方={prescription_code}, 药品ID={medicine_id}）",
                    prescription_code=prescription_code):
                return False

        self.medicine_started[medicine_id] = True

        # 阶段2：发送 running，等待 running-step5-waiting-end（重发上限后停止发送、静默等待回执）
        if self.step5_return_event.is_set():
            print(f"{tag} [收到] step5-waiting-end（阶段1已到达，跳过running发送）")
        send_count = 0
        while not self.step5_return_event.is_set() and self.sender_running:
            if send_count >= max_attempts:
                print(f"{tag} [警告] running重发超过上限{max_attempts}次，转入静默等待")
                break
            # 每隔 N 次发送检查药单是否被删除
            if send_count > 0 and send_count % PRESCRIPTION_CHECK_INTERVAL == 0:
                if not check_prescription_exists(prescription_code):
                    print(f"{tag} [停止] 处方{prescription_code}已删除，停止发送running")
                    return False
            send_count += 1
            await self.send_medicine_to_ros(
                prescription_code, medicine_data, medicine_index, medicine_total, "running"
            )
            try:
                await asyncio.wait_for(self.step5_return_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.sender_running:
            return False

        if not self.step5_return_event.is_set():
            # 重发上限已到但 step5 回执未达：停止发送，静默等待回执
            # （真实车1 从 running 到 step5 含导航+抓药+放药，耗时可能远超 30s 重发窗口）
            if not await self._wait_receipt_silently(
                    self.step5_return_event, receipt_wait_timeout,
                    f"running-step5-waiting-end（处方={prescription_code}, 药品ID={medicine_id}）",
                    prescription_code=prescription_code):
                return False

        # 阶段3：发送 end（收到 step5 回执后直接发送，与旧版一致，不依赖药师扫码）
        success = await self.send_medicine_end_to_ros(
            prescription_code, medicine_data, medicine_index, medicine_total
        )

        if not success:
            print(f"{tag} [错误] end 消息发送失败")
            return False

        return True

    # ===== 主循环 =====

    async def sender_loop(self):
        tag = self._log_tag()
        self._init_events()

        print(f"{tag} 服务启动")

        self.sender_running = True

        while self.sender_running:
            try:
                ros_available = await self.check_ros_ws_available()

                if not ros_available:
                    await asyncio.sleep(settings.ros_check_interval)
                    continue

                new_code, new_created_at = get_latest_pending_prescription()

                if new_code == self.current_prescription_code and new_code:
                    # 同单号：检测是否为删除后重下的新单（created_at 变化）
                    # 内存态 _prescription_taken_at 可能因重启丢失，降级查 DB
                    old_created_at = self._prescription_taken_at
                    if old_created_at is None and new_created_at:
                        # 重启后内存丢失，查 workflow_events 最旧事件时间作为"旧下单时间"近似
                        try:
                            _evts = get_events_for_prescriptions([new_code]).get(new_code, [])
                            if _evts:
                                old_created_at = min(e.get("created_at") for e in _evts if e.get("created_at"))
                        except Exception:
                            pass
                    if (new_created_at and old_created_at
                            and new_created_at != old_created_at):
                        print(f"{tag} [状态] 检测到同单号重新下单: {new_code}，重置流程")
                        purge_stale_events_if_reordered(new_code, new_created_at)
                        self._failed_prescriptions.discard(new_code)
                        self.reset_medicine_state(new_code)
                        self.task_completed = False
                        self._prescription_taken_at = new_created_at
                        self._prescription_taken_at_str = str(new_created_at)
                        if self.car_id == 1:
                            record_event(new_code, "N1_prescription_created", "his", "处方已开具，任务开始")
                        if not self.medicine_list:
                            print(f"{tag} 药品列表为空，等待新处方...")
                            await asyncio.sleep(POLL_INTERVAL)
                            continue

                if new_code != self.current_prescription_code:
                    if new_code:
                        print(f"{tag} [状态] 新处方: {new_code}")
                        # 删除重下自愈：同单号重新下单时清理上一轮旧节点事件
                        # （HIS 删除联动失败时的兜底，防止重入防护误判"阶段一已闭环"不发 start）
                        purge_stale_events_if_reordered(new_code, new_created_at)
                        self.current_prescription_code = new_code
                        self.expected_prescription_code = new_code
                        self._prescription_taken_at = new_created_at
                        self._prescription_taken_at_str = str(new_created_at)
                        # 新处方（含失败后换新单）：从失败集合中移除，允许重新处理
                        self._failed_prescriptions.discard(new_code)
                        self.reset_medicine_state(new_code)
                        if self.car_id == 1:
                            record_event(new_code, "N1_prescription_created", "his", "处方已开具，任务开始")

                        if not self.medicine_list:
                            await asyncio.sleep(POLL_INTERVAL)
                            continue
                    else:
                        await asyncio.sleep(POLL_INTERVAL)
                        continue

                # ===== 重入防护（DB 事件兜底）=====
                # 阶段一已闭环的处方（arm_end 到达，N5 事件已存在）不再重复发送。
                # 后端重启后内存进度丢失，以 workflow_events 为准，避免从药1 重新发送。
                if self.current_prescription_code:
                    try:
                        _events = get_events_for_prescriptions([self.current_prescription_code]).get(
                            self.current_prescription_code, [])
                        if any(e["event_key"] == "N5_scanned_outbound" for e in _events):
                            await asyncio.sleep(POLL_INTERVAL)
                            continue
                    except Exception:
                        pass

                # 发送失败已放弃的处方：跳过，直到新处方到来（防止持续重试刷屏）
                if self.current_prescription_code and self.current_prescription_code in self._failed_prescriptions:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                if self.task_completed:
                    await asyncio.sleep(SEND_INTERVAL)
                    continue

                if self.medicine_list and self.medicine_total > 0:
                    for idx in range(self.current_medicine_index, self.medicine_total):
                        if not self.sender_running:
                            break

                        self.current_medicine_index = idx
                        current_medicine = self.medicine_list[idx]

                        medicine_id_check = current_medicine.get("medicine_id", 0)
                        if medicine_id_check == 0 or medicine_id_check is None:
                            continue

                        medicine_index_display = self.current_medicine_index + 1

                        success = await self.process_single_medicine(
                            current_medicine,
                            self.current_prescription_code,
                            medicine_index_display,
                            self.medicine_total
                        )

                        if success:
                            self.last_sent_code = self.current_prescription_code
                        else:
                            self._failed_prescriptions.add(self.current_prescription_code)
                            break

                    if self.current_medicine_index >= self.medicine_total - 1:
                        self.all_medicines_completed = True
                        self.current_medicine_index = self.medicine_total
                        await asyncio.sleep(POLL_INTERVAL)
                else:
                    if self.current_prescription_code and not self.medicine_list:
                        self.current_prescription_code = None
                        self.expected_prescription_code = None
                        self.medicine_list = []
                        self.medicine_total = 0
                        self.current_medicine_index = 0
                        self.all_medicines_completed = False
                        self.task_completed = False
                    await asyncio.sleep(POLL_INTERVAL)

            except asyncio.CancelledError:
                print(f"{tag} 服务停止")
                break
            except Exception as e:
                print(f"{tag} 主循环异常: {e}")
                await asyncio.sleep(5)

    async def start(self):
        await self.sender_loop()

    async def stop(self):
        self.sender_running = False
        # 停止车2 信号连续发送
        try:
            await self._stop_continuous_send()
        except Exception:
            pass
        if self.started_event:
            self.started_event.set()
        if self.step5_return_event:
            self.step5_return_event.set()
        if self.medicine_completed_event:
            self.medicine_completed_event.set()
        if self.all_completed_event:
            self.all_completed_event.set()
        if self.task_end_event:
            self.task_end_event.set()
        if self.ws_connection:
            try:
                await self.ws_connection.close()
            except:
                pass
            self.ws_connection = None
        print(f"{self._log_tag()} 服务已停止")

    def get_status(self):
        return {
            "car_id": self.car_id,
            "running": self.sender_running,
            "current_prescription_code": self.current_prescription_code,
            "last_sent_code": self.last_sent_code,
            "medicine_list": self.medicine_list,
            "medicine_total": self.medicine_total,
            "current_medicine_index": self.current_medicine_index + 1 if self.medicine_total > 0 else 0,
            "medicine_send_count": self.medicine_send_count,
            "all_medicines_completed": self.all_medicines_completed,
            "task_completed": self.task_completed,
            "ros_ws_url": self.ws_url,
            "ros_topic": self.send_topic,
        }

    # ===== 外部通知接口 =====

    def notify_medicine_started(self, medicine_id: int, prescription_code: str):
        tag = self._log_tag()
        if prescription_code != self.current_prescription_code:
            print(f"{tag} [收到] running-started | 处方={prescription_code} | 药品ID={medicine_id} | 处方不匹配，忽略")
            return False

        if medicine_id == self.expected_medicine_id:
            print(f"{tag} [收到] running-started | 处方={prescription_code} | 药品ID={medicine_id}")
            self.medicine_started[medicine_id] = True
            if self.started_event:
                self.started_event.set()
            return True
        else:
            print(f"{tag} [收到] running-started | 处方={prescription_code} | 药品ID={medicine_id} | 药品ID不匹配，忽略")
            return False

    def notify_prescription_step5_return(self, prescription_code: str, medicine_id: int = None):
        tag = self._log_tag()
        if prescription_code != self.current_prescription_code:
            print(f"{tag} [收到] step5-waiting-end | 处方={prescription_code} | 药品ID={medicine_id} | 处方不匹配，忽略")
            return

        if medicine_id is None or medicine_id != self.expected_medicine_id:
            print(f"{tag} [收到] step5-waiting-end | 处方={prescription_code} | 药品ID={medicine_id} | 药品ID不匹配，忽略")
            return

        print(f"{tag} [收到] step5-waiting-end | 处方={prescription_code} | 药品ID={medicine_id}")
        if self.step5_return_event:
            self.step5_return_event.set()

    def notify_medicine_completed(self, medicine_id: int, prescription_code: str):
        tag = self._log_tag()
        if prescription_code != self.current_prescription_code:
            print(f"{tag} [收到] end | 处方={prescription_code} | 处方不匹配，忽略")
            return False
        if medicine_id != self.expected_medicine_id:
            print(f"{tag} [收到] end | 处方={prescription_code} | 药品ID={medicine_id} | 药品ID不匹配，忽略")
            return False

        print(f"{tag} [收到] end | 处方={prescription_code} | 药品ID={medicine_id}")
        if self.medicine_completed_event:
            self.medicine_completed_event.set()
        return True

    def notify_all_medicines_completed(self, prescription_code: str):
        tag = self._log_tag()
        if prescription_code != self.current_prescription_code:
            print(f"{tag} [收到] all_completed | 处方={prescription_code} | 处方不匹配，忽略")
            return

        print(f"{tag} [收到] all_completed | 处方={prescription_code}")
        self.all_medicines_completed = True
        self.task_completed = True
        if self.all_completed_event:
            self.all_completed_event.set()
        if self.task_end_event:
            self.task_end_event.set()

    def notify_task_completed(self, prescription_code: str):
        tag = self._log_tag()
        if prescription_code == self.current_prescription_code:
            print(f"{tag} [收到] end(药单级) | 处方={prescription_code}")
            self.task_completed = True
            if self.task_end_event:
                self.task_end_event.set()
        else:
            print(f"{tag} [收到] end(药单级) | 处方={prescription_code} | 处方不匹配，忽略")


# ===== 工厂函数：创建并注册小车实例 =====

def create_sender(car_id: int, ws_host: str, ws_port: int, send_topic: str, send_msg_type: str) -> HisSender:
    """创建并注册一个 HIS Sender 实例"""
    sender = HisSender(car_id, ws_host, ws_port, send_topic, send_msg_type)
    _senders[car_id] = sender
    return sender


def get_sender(car_id: int = 1) -> HisSender:
    """获取指定小车的 HIS Sender 实例"""
    return _senders.get(car_id)


def get_all_senders() -> dict:
    """获取所有已注册的 HIS Sender 实例"""
    return _senders


# ===== 向后兼容的模块级函数（默认操作车1）=====

async def start_his_sender():
    """启动 HIS 处方发送服务（车1，向后兼容）"""
    car_configs = settings.get_car_configs()
    car1 = car_configs[0]
    sender = create_sender(
        car_id=1,
        ws_host=car1["ws_host"],
        ws_port=car1["ws_port"],
        send_topic=car1["send_topic"],
        send_msg_type=car1["send_msg_type"],
    )
    await sender.start()


async def stop_his_sender():
    """停止 HIS 处方发送服务（所有车）"""
    for sender in _senders.values():
        await sender.stop()


def get_sender_status(car_id: int = 1):
    """获取发送服务状态（向后兼容）"""
    sender = _senders.get(car_id)
    if sender:
        return sender.get_status()
    return {"running": False, "error": f"Car {car_id} not found"}


# ===== 向后兼容的模块级通知接口（默认通知车1）=====

def notify_medicine_started(medicine_id: int, prescription_code: str):
    sender = _senders.get(1)
    if sender:
        sender.notify_medicine_started(medicine_id, prescription_code)


def notify_prescription_step5_return(prescription_code: str, medicine_id: int = None):
    sender = _senders.get(1)
    if sender:
        sender.notify_prescription_step5_return(prescription_code, medicine_id)


def notify_medicine_completed(medicine_id: int, prescription_code: str):
    sender = _senders.get(1)
    if sender:
        sender.notify_medicine_completed(medicine_id, prescription_code)


def notify_all_medicines_completed(prescription_code: str):
    sender = _senders.get(1)
    if sender:
        sender.notify_all_medicines_completed(prescription_code)


def notify_task_completed(prescription_code: str):
    sender = _senders.get(1)
    if sender:
        sender.notify_task_completed(prescription_code)


# ===== 向后兼容的全局状态引用（供 ros_listener 使用）=====

# 这些属性通过车1实例暴露，兼容 ros_listener 中的 from his_sender import _medicine_total 等
@property
def _medicine_total():
    sender = _senders.get(1)
    return sender.medicine_total if sender else 0


@property
def _current_medicine_index():
    sender = _senders.get(1)
    return sender.current_medicine_index if sender else 0
