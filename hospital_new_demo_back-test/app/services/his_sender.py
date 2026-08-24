"""
HIS 处方自动发送服务（多车支持版）

支持多辆ROS小车，每辆车独立WebSocket连接、独立Topic、独立状态管理。
所有配置通过 .env 文件统一管理（CAR1_*, CAR2_* 前缀）。

向后兼容：保留模块级函数（start_his_sender, stop_his_sender, get_sender_status,
notify_* 等），默认操作车1。
"""
import asyncio
import json
import pymysql
import websockets
from typing import Optional
from app.core.config import settings

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
    从 HIS 数据库获取最新待处理的处方编码
    """
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT prescription_code, id, created_at
                FROM prescriptions
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            result = cursor.fetchone()

            if result:
                prescription_code = result["prescription_code"]
                print(f"[HIS Sender] 获取到最新处方: {prescription_code}")
                return prescription_code
            else:
                return None
    except Exception as e:
        print(f"[HIS Sender] 查询 HIS 数据库失败: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()


def get_prescription_medicine_locations(prescription_code: str) -> list:
    """
    根据处方编码查询该处方开具的所有药品的坐标

    查询路径：prescriptions -> prescription_items -> medicine_locations
    """
    print("=" * 60)
    print(f"[HIS Sender] 开始查询药品坐标")
    print(f"[HIS Sender] 处方编码: {prescription_code}")

    try:
        print(f"[HIS Sender] 正在连接 HIS MySQL...")
        print(f"[HIS Sender] MySQL地址: {settings.his_mysql_host}:{settings.his_mysql_port}")
        print(f"[HIS Sender] MySQL数据库: {settings.his_mysql_db}")

        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        print(f"[HIS Sender] MySQL连接成功")

        with conn.cursor() as cursor:
            sql_query = """
                SELECT
                    ml.medicine_id,
                    MIN(ml.x) as x,
                    MIN(ml.y) as y,
                    MIN(ml.z) as z,
                    MIN(ml.yaw) as yaw
                FROM prescriptions p
                JOIN prescription_items pi ON p.id = pi.prescription_id
                JOIN medicines m ON pi.medicine_id = m.id
                JOIN medicine_locations ml ON m.name = ml.medicine_name
                WHERE p.prescription_code = %s
                GROUP BY ml.medicine_id
                ORDER BY ml.medicine_id ASC
            """
            print(f"[HIS Sender] 执行SQL查询: {sql_query.strip()}")
            print(f"[HIS Sender] 查询参数: prescription_code={prescription_code}")

            cursor.execute(sql_query, (prescription_code,))
            results = cursor.fetchall()

            print(f"[HIS Sender] 查询结果数量: {len(results)}")

            if results:
                medicine_list = []
                for i, row in enumerate(results):
                    print(f"[HIS Sender] 查询结果{i+1}: medicine_id={row['medicine_id']}, x={row['x']}, y={row['y']}, z={row['z']}, yaw={row['yaw']}")

                    medicine_id_value = row["medicine_id"]
                    if medicine_id_value is None or medicine_id_value == 0:
                        print(f"[HIS Sender] WARNING: 药品{i+1} 的 medicine_id 为 NULL 或 0，跳过该药品")
                        continue

                    medicine_list.append({
                        "medicine_id": int(medicine_id_value),
                        "x": float(row["x"]) if row["x"] is not None else 0.0,
                        "y": float(row["y"]) if row["y"] is not None else 0.0,
                        "z": float(row["z"]) if row["z"] is not None else 0.0,
                        "yaw": float(row["yaw"]) if row["yaw"] is not None else 0.0
                    })
                print(f"[HIS Sender] 处方 {prescription_code} 包含 {len(medicine_list)} 个药品")
                for i, med in enumerate(medicine_list):
                    print(f"[HIS Sender]   药品{i+1}: ID={med['medicine_id']}, xyz=({med['x']}, {med['y']}, {med['z']}), yaw={med['yaw']}")
                print("=" * 60)
                return medicine_list
            else:
                print(f"[HIS Sender] 处方 {prescription_code} 未找到药品坐标信息")
                print("=" * 60)
                return []
    except pymysql.Error as e:
        print(f"[HIS Sender] MySQL错误: {e}")
        print("=" * 60)
        return []
    except Exception as e:
        print(f"[HIS Sender] 查询药品坐标失败: {e}")
        print("=" * 60)
        return []
    finally:
        if 'conn' in locals():
            conn.close()
            print(f"[HIS Sender] MySQL连接已关闭")


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

        # 预期上下文
        self.expected_medicine_id = None
        self.expected_prescription_code = None

        # 车2 信号连续发送状态（pharmacist-success / lift-across / lift-open / nurse-success）
        self._continuous_send_task: Optional[asyncio.Task] = None
        self._continuous_stop_event: Optional[asyncio.Event] = None
        self._continuous_signal_name: Optional[str] = None

    def _init_events(self):
        self.started_event = asyncio.Event()
        self.step5_return_event = asyncio.Event()
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
                websockets.connect(self.ws_url),
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
                websockets.connect(self.ws_url),
                timeout=settings.ros_connect_timeout
            )
            await ws.close()
            return True
        except Exception as e:
            print(f"{tag} ROS WebSocket 不可达: {self.ws_url} - {e}")
            return False

    # ===== 车2 信号连续发送 =====
    # 4 个车2 信号（pharmacist-success / lift-across / lift-open / nurse-success）
    # 均改为连续发送：每 car2_signal_interval 秒重发一次，
    # 直到被 stop_current_signal()（收到对应回执）或下一个信号启动（信号改变）停止。
    # nurse-success 是末位信号，无对应回执，发送 3 次后自动停止。

    async def _publish_signal_once(self, message: str) -> bool:
        """发送一次车2 信号（纯字符串 data 载荷，信息拼在 data 内）"""
        tag = self._log_tag()
        try:
            await self._ensure_ws_connection()
            message_dict = {
                "op": "publish",
                "topic": self.send_topic,
                "msg": {"data": message},
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
                                    max_sends: Optional[int] = None) -> None:
        """
        启动一个信号的连续发送。会先停掉当前正在发送的信号（信号改变即停）。
        - max_sends=None：持续发送，直到 stop_current_signal() 或下一个信号切换
        - max_sends=N：发送 N 次后自动停止（用于末位信号 nurse-success）
        """
        tag = self._log_tag()
        await self._stop_continuous_send()

        stop_event = asyncio.Event()
        self._continuous_stop_event = stop_event
        self._continuous_signal_name = signal_name
        self._continuous_send_task = asyncio.create_task(
            self._continuous_send_loop(signal_name, message, stop_event, max_sends)
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
                                   max_sends: Optional[int]) -> None:
        tag = self._log_tag()
        interval = settings.car2_signal_interval
        limit_desc = f"，上限 {max_sends} 次" if max_sends is not None else "，持续至切换/停止"
        print(f"{tag} [连续发送] 启动 {signal_name}: {message}{limit_desc}")
        count = 0
        try:
            while not stop_event.is_set():
                if max_sends is not None and count >= max_sends:
                    break
                count += 1
                ok = await self._publish_signal_once(message)
                print(f"{tag} [连续发送] {signal_name} 第 {count} 次 {'✓' if ok else '✗'}")
                if max_sends is not None and count >= max_sends:
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            print(f"{tag} [连续发送] 停止 {signal_name}（共发送 {count} 次）")

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

            print("=" * 60)
            print(f"{tag} 发送药品坐标消息:")
            print(f"{tag}   data: {data}")
            print(f"{tag}   prescription_code: {prescription_code}")
            print(f"{tag}   medicine_id: {medicine_id}")
            print(f"{tag}   x: {medicine_data['x']}, y: {medicine_data['y']}, z: {medicine_data['z']}, yaw: {medicine_data['yaw']}")
            print(f"{tag}   medicine_total: {medicine_total}, medicine_index: {medicine_index}")
            print(f"{tag}   发送计数: {self.medicine_send_count[medicine_id]}")
            print("=" * 60)

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

                print("=" * 60)
                print(f"{tag} 发送药品完成信号（end）:")
                print(f"{tag}   发送次数: 第{send_count+1}次（共2次）")
                print(f"{tag}   data: end, medicine_id: {medicine_id}")
                print("=" * 60)

                await self.ws_connection.send(message)
                print(f"{tag} end 消息发送成功（第{send_count+1}次）")

                if send_count == 0:
                    await asyncio.sleep(SEND_INTERVAL)

            return True

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

        print(f"{tag} 药品状态已重置:")
        print(f"{tag}   药品总数: {self.medicine_total}")
        print(f"{tag}   当前药品索引: {self.current_medicine_index}")
        print("=" * 60)

    # ===== 电梯跨楼信号 =====

    async def send_lift_across(self, prescription_code: str):
        """启动 lift-across 连续发送（收到 lift-arrive 后调用；启动时自动停①，⑤启动时自动停本信号）"""
        tag = self._log_tag()
        message = f"{prescription_code}_lift-across"
        print(f"{tag} → 启动 lift-across 连续发送: {message}")
        await self._start_continuous_send("lift-across", message, max_sends=None)

    async def send_lift_open(self, prescription_code: str):
        """启动 lift-open 连续发送（延迟后调用；启动时自动停③，收到 nurse_arrive 后由调用方停本信号）"""
        tag = self._log_tag()
        message = f"{prescription_code}_lift-open"
        print(f"{tag} → 启动 lift-open 连续发送: {message}")
        await self._start_continuous_send("lift-open", message, max_sends=None)

    async def send_nurse_success(self, prescription_code: str):
        """启动 nurse-success 连续发送（收到 nurse_arrive 后调用；末位信号，发 3 次自动停）"""
        tag = self._log_tag()
        message = f"{prescription_code}_nurse-success"
        print(f"{tag} → 启动 nurse-success 连续发送: {message}（发 3 次后停止）")
        await self._start_continuous_send("nurse-success", message, max_sends=3)

    # ===== 药师审核通过信号 =====

    async def send_pharmacist_success(self, medicine_id: int, prescription_code: str):
        """启动 pharmacist-success 连续发送（车1 running-step4 时调用；收到 lift-arrive 后由调用方停）"""
        tag = self._log_tag()
        message = f"{prescription_code}_pharmacist-success"
        print("=" * 60)
        print(f"{tag} → 启动 pharmacist-success 连续发送:")
        print(f"{tag}   Topic: {self.send_topic}")
        print(f"{tag}   信号: {message}")
        print(f"{tag}   medicine_id: {medicine_id}")
        print(f"{tag}   prescription_code: {prescription_code}")
        print("=" * 60)
        await self._start_continuous_send("pharmacist-success", message, max_sends=None)

    # ===== 核心：顺序处理单个药品 =====

    async def process_single_medicine(self, medicine_data: dict, prescription_code: str,
                                       medicine_index: int, medicine_total: int):
        tag = self._log_tag()
        medicine_id = medicine_data["medicine_id"]
        self.expected_medicine_id = medicine_id

        print(f"\n{tag} {'='*60}")
        print(f"{tag} 开始处理药品 {medicine_index}/{medicine_total} (ID={medicine_id})")
        print(f"{tag} {'='*60}")

        self.started_event.clear()
        self.step5_return_event.clear()

        # 阶段1：发送 start，等待 running-started
        print(f"{tag} 阶段1：发送 start，等待 running-started")
        send_count = 0
        while not self.started_event.is_set() and self.sender_running:
            send_count += 1
            print(f"{tag} 发送 start（第{send_count}次）")
            await self.send_medicine_to_ros(
                prescription_code, medicine_data, medicine_index, medicine_total, "start"
            )
            try:
                await asyncio.wait_for(self.started_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.sender_running:
            return False

        print(f"{tag} [OK] 收到 running-started（共发送{send_count}次start）")
        self.medicine_started[medicine_id] = True

        # 阶段2：发送 running，等待 running-step5-waiting-end
        print(f"{tag} 阶段2：发送 running，等待 running-step5-waiting-end")
        if self.step5_return_event.is_set():
            print(f"{tag} [OK] step5-return 在阶段1已到达，跳过 running 发送")
        send_count = 0
        while not self.step5_return_event.is_set() and self.sender_running:
            send_count += 1
            print(f"{tag} 发送 running（第{send_count}次）")
            await self.send_medicine_to_ros(
                prescription_code, medicine_data, medicine_index, medicine_total, "running"
            )
            try:
                await asyncio.wait_for(self.step5_return_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.sender_running:
            return False

        print(f"{tag} [OK] 收到 running-step5-waiting-end（共发送{send_count}次running）")

        # 阶段3：发送 end
        print(f"{tag} 阶段3：发送 end（两次，间隔2秒）")
        success = await self.send_medicine_end_to_ros(
            prescription_code, medicine_data, medicine_index, medicine_total
        )

        if not success:
            print(f"{tag} [ERROR] end 消息发送失败")
            return False

        # 阶段4：等待3秒
        print(f"{tag} 阶段4：等待3秒，让ROS端处理end消息...")
        await asyncio.sleep(3)

        print(f"{tag} [OK] 药品 {medicine_index}/{medicine_total} (ID={medicine_id}) 处理完成")
        return True

    # ===== 主循环 =====

    async def sender_loop(self):
        tag = self._log_tag()
        self._init_events()

        print("=" * 60)
        print(f"{tag} 服务启动（顺序结构模式）")
        print(f"{tag} HIS MySQL: {settings.his_mysql_host}:{settings.his_mysql_port}")
        print(f"{tag} ROS WebSocket: {self.ws_url}")
        print(f"{tag} Topic: {self.send_topic}")
        print("=" * 60)

        self.sender_running = True

        while self.sender_running:
            try:
                ros_available = await self.check_ros_ws_available()

                if not ros_available:
                    print(f"{tag} ROS WebSocket 不可达，等待重试...")
                    await asyncio.sleep(settings.ros_check_interval)
                    continue

                new_code = get_latest_pending_prescription()

                print(f"{tag} 主循环状态检查:")
                print(f"{tag}   当前处方编码: {self.current_prescription_code}")
                print(f"{tag}   查询处方编码: {new_code}")
                print(f"{tag}   是否相同: {new_code == self.current_prescription_code}")

                if new_code != self.current_prescription_code:
                    if new_code:
                        print(f"\n{tag} {'='*40}")
                        print(f"{tag} 处方编码更新: {self.current_prescription_code} -> {new_code}")
                        self.current_prescription_code = new_code
                        self.expected_prescription_code = new_code
                        self.reset_medicine_state(new_code)
                        print(f"{tag} {'='*40}")

                        if not self.medicine_list:
                            print(f"{tag} 药品列表为空，等待新处方...")
                            await asyncio.sleep(POLL_INTERVAL)
                            continue
                    else:
                        print(f"{tag} 无待处理处方，等待新处方...")
                        await asyncio.sleep(POLL_INTERVAL)
                        continue

                if self.task_completed:
                    print(f"{tag} 任务已完成，停止发送")
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
                            print(f"{tag} ERROR: 当前药品的 medicine_id 为 0 或 NULL，跳过")
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
                            print(f"{tag} 药品发送失败，退出当前处方处理")
                            break

                    if self.current_medicine_index >= self.medicine_total - 1:
                        print(f"{tag} 所有药品发送完成")
                        self.all_medicines_completed = True
                        self.current_medicine_index = self.medicine_total
                        await asyncio.sleep(POLL_INTERVAL)
                else:
                    if self.current_prescription_code and not self.medicine_list:
                        print(f"{tag} 处方 {self.current_prescription_code} 的药品列表为空，停止发送")
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
                import traceback
                traceback.print_exc()
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
        print("=" * 60)
        print(f"{tag} 收到药品 started 通知:")
        print(f"{tag}   收到的消息: {medicine_id}_{prescription_code}_running-started")
        print(f"{tag}   当前处方编码: {self.current_prescription_code}")
        print(f"{tag}   预期药品ID: {self.expected_medicine_id}")

        if prescription_code != self.current_prescription_code:
            print(f"{tag} [ERROR] 处方编码不匹配！不设置 started 事件")
            print("=" * 60)
            return

        if medicine_id == self.expected_medicine_id:
            print(f"{tag} [OK] 药品ID匹配！设置 started 事件")
            self.medicine_started[medicine_id] = True
            if self.started_event:
                self.started_event.set()
        else:
            print(f"{tag} [ERROR] 药品ID不匹配！收到={medicine_id} 预期={self.expected_medicine_id}")
        print("=" * 60)

    def notify_prescription_step5_return(self, prescription_code: str, medicine_id: int = None):
        tag = self._log_tag()
        print("=" * 60)
        print(f"{tag} 收到药品完成通知（Step5返回）:")
        print(f"{tag}   prescription_code: {prescription_code}, medicine_id: {medicine_id}")
        print(f"{tag}   当前处方编码: {self.current_prescription_code}")
        print(f"{tag}   预期药品ID: {self.expected_medicine_id}")

        if prescription_code != self.current_prescription_code:
            print(f"{tag} [ERROR] 处方编码不匹配！")
            print("=" * 60)
            return

        if medicine_id is None:
            print(f"{tag} [ERROR] 药单级消息缺少 medicine_id！")
            print("=" * 60)
            return

        if medicine_id != self.expected_medicine_id:
            print(f"{tag} [ERROR] 药品ID不匹配！收到={medicine_id} 预期={self.expected_medicine_id}")
            print("=" * 60)
            return

        print(f"{tag} [OK] 处方编码和药品ID都匹配！设置 step5-return 事件")
        if self.step5_return_event:
            self.step5_return_event.set()
        print("=" * 60)

    def notify_medicine_completed(self, medicine_id: int, prescription_code: str):
        tag = self._log_tag()
        print("=" * 60)
        print(f"{tag} 收到药品完成通知（end消息）:")
        print(f"{tag}   {medicine_id}_{prescription_code}_end")
        print(f"{tag}   （顺序结构下由for循环自动切换，无需手动切换）")
        print("=" * 60)

    def notify_all_medicines_completed(self, prescription_code: str):
        tag = self._log_tag()
        print("=" * 60)
        print(f"{tag} 收到所有药品完成信号（all_completed）:")
        print(f"{tag}   prescription_code: {prescription_code}")
        print(f"{tag}   当前: {self.current_prescription_code}")

        if prescription_code != self.current_prescription_code:
            print(f"{tag} [ERROR] 处方编码不匹配！")
            print("=" * 60)
            return

        print(f"{tag} [OK] 处方编码匹配！设置 all_completed 和 task_completed")
        self.all_medicines_completed = True
        self.task_completed = True
        if self.all_completed_event:
            self.all_completed_event.set()
        if self.task_end_event:
            self.task_end_event.set()
        print("=" * 60)

    def notify_task_completed(self, prescription_code: str):
        tag = self._log_tag()
        print(f"{tag} 收到任务完成信号: {prescription_code}")
        if prescription_code == self.current_prescription_code:
            print(f"{tag} [OK] 处方编码匹配")
            self.task_completed = True
            if self.task_end_event:
                self.task_end_event.set()
        else:
            print(f"{tag} [ERROR] end 处方编码不匹配: {prescription_code} != {self.current_prescription_code}")


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