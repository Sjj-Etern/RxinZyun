import asyncio
import json
import os
import sys
import time
import pymysql
import websockets
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

HIS_DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "527725",
    "database": "hospital",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

ROS_WS_HOST = "127.0.0.1"
ROS_WS_PORT = 9090
ROS_WS_URL = f"ws://{ROS_WS_HOST}:{ROS_WS_PORT}"

ROS_TOPIC = "/rxzy_msg"
ROS_MSG_TYPE = "his_sub"

ROS_LISTEN_TOPIC = "/car01_pub"

SEND_INTERVAL = 2
POLL_INTERVAL = 2


def get_latest_pending_prescription():
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
                print(f"[测试脚本] 获取到最新pending处方: {result['prescription_code']}")
                return result
            else:
                print("[测试脚本] 没有pending状态的处方")
                return None
    except Exception as e:
        print(f"[测试脚本] 查询HIS数据库失败: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()


def get_prescription_medicine_locations(prescription_code: str) -> list:
    print("=" * 60)
    print(f"[测试脚本] 查询处方 {prescription_code} 的药品坐标")
    print("[测试脚本] 查询逻辑: medicines.name → medicine_locations.medicine_name")
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)
        with conn.cursor() as cursor:
            sql_query = """
                SELECT
                    ml.medicine_id,
                    ml.medicine_name,
                    MIN(ml.x) as x,
                    MIN(ml.y) as y,
                    MIN(ml.z) as z,
                    MIN(ml.yaw) as yaw,
                    m.id as medicines_id,
                    m.name as medicines_name
                FROM prescriptions p
                JOIN prescription_items pi ON p.id = pi.prescription_id
                JOIN medicines m ON pi.medicine_id = m.id
                JOIN medicine_locations ml ON m.name = ml.medicine_name
                WHERE p.prescription_code = %s
                GROUP BY ml.medicine_id, ml.medicine_name, m.id, m.name
                ORDER BY ml.medicine_id ASC
            """
            cursor.execute(sql_query, (prescription_code,))
            results = cursor.fetchall()

            medicine_list = []
            for row in results:
                medicine_id_value = row["medicine_id"]
                if medicine_id_value is None or medicine_id_value == 0:
                    continue
                medicine_list.append({
                    "medicine_id": int(medicine_id_value),
                    "medicine_name": row["medicine_name"] or "未知药品",
                    "medicines_id": row["medicines_id"],
                    "medicines_name": row["medicines_name"],
                    "x": float(row["x"]) if row["x"] is not None else 0.0,
                    "y": float(row["y"]) if row["y"] is not None else 0.0,
                    "z": float(row["z"]) if row["z"] is not None else 0.0,
                    "yaw": float(row["yaw"]) if row["yaw"] is not None else 0.0,
                })

            print(f"[测试脚本] 处方 {prescription_code} 包含 {len(medicine_list)} 个药品")
            for i, med in enumerate(medicine_list):
                print(f"[测试脚本]   药品{i+1}:")
                print(f"[测试脚本]     医生下药: medicines.id={med['medicines_id']}, name=\"{med['medicines_name']}\"")
                print(f"[测试脚本]     坐标来源: medicine_locations.medicine_id={med['medicine_id']}, name=\"{med['medicine_name']}\"")
                print(f"[测试脚本]     发送给ROS: medicine_id={med['medicine_id']}, xyz=({med['x']}, {med['y']}, {med['z']}), yaw={med['yaw']}")
            print("=" * 60)
            return medicine_list
    except Exception as e:
        print(f"[测试脚本] 查询药品坐标失败: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()


async def handle_ros_client(websocket, path=None):
    print(f"\n[模拟ROS] 客户端已连接: {websocket.remote_address}")

    await websocket.send(json.dumps({
        "op": "advertise",
        "topic": ROS_LISTEN_TOPIC,
        "type": "std_msgs/String"
    }))

    try:
        async for raw_message in websocket:
            try:
                msg = json.loads(raw_message)
                op = msg.get("op")
                topic = msg.get("topic")

                if op == "publish" and topic == ROS_TOPIC:
                    msg_data = msg.get("msg", {})
                    data = msg_data.get("data")
                    prescription_code = msg_data.get("prescription_code")
                    medicine_id = msg_data.get("medicine_id")
                    medicine_total = msg_data.get("medicine_total")
                    medicine_index = msg_data.get("medicine_index")

                    print(f"\n[模拟ROS] 收到消息:")
                    print(f"[模拟ROS]   data: {data}")
                    print(f"[模拟ROS]   prescription_code: {prescription_code}")
                    print(f"[模拟ROS]   medicine_id: {medicine_id}")
                    print(f"[模拟ROS]   medicine_index: {medicine_index}/{medicine_total}")
                    print(f"[模拟ROS]   x: {msg_data.get('x')}, y: {msg_data.get('y')}, z: {msg_data.get('z')}, yaw: {msg_data.get('yaw')}")

                    if data == "start":
                        await asyncio.sleep(1)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-started")
                        await asyncio.sleep(0.5)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-step1-navigate-to-pharmacy")
                        await asyncio.sleep(0.5)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-step2-pick")

                    elif data == "running":
                        await asyncio.sleep(1)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-step3-navigate-doctor")
                        await asyncio.sleep(0.5)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-step4-deliver-medicine")
                        await asyncio.sleep(0.5)
                        await send_ros_status(websocket, medicine_id, prescription_code, "running-step5-waiting-end")

                    elif data == "end":
                        print(f"[模拟ROS]   收到end信号（不回复，等待后续处理）")

                elif op == "advertise":
                    print(f"[模拟ROS] 客户端注册Topic: {topic}")
                elif op == "unadvertise":
                    print(f"[模拟ROS] 客户端取消注册Topic: {topic}")

            except json.JSONDecodeError:
                print(f"[模拟ROS] 非JSON消息: {raw_message}")

    except websockets.exceptions.ConnectionClosed:
        print("[模拟ROS] 客户端连接已关闭")
    except Exception as e:
        print(f"[模拟ROS] 处理消息异常: {e}")


async def send_ros_status(websocket, medicine_id, prescription_code, status):
    message_data = f"{medicine_id}_{prescription_code}_{status}"
    ros_message = {
        "op": "publish",
        "topic": ROS_LISTEN_TOPIC,
        "msg": {"data": message_data}
    }
    await websocket.send(json.dumps(ros_message))
    print(f"[模拟ROS] → 已发送状态: {message_data}")


async def send_prescription_level_status(websocket, prescription_code, status):
    message_data = f"{prescription_code}_{status}"
    ros_message = {
        "op": "publish",
        "topic": ROS_LISTEN_TOPIC,
        "msg": {"data": message_data}
    }
    await websocket.send(json.dumps(ros_message))
    print(f"[模拟ROS] → 已发送药单级状态: {message_data}")


async def start_mock_ros_server():
    print(f"\n[模拟ROS] 启动WebSocket服务器: {ROS_WS_URL}")
    print(f"[模拟ROS] 监听Topic（接收HIS Sender消息）: {ROS_TOPIC}")
    print(f"[模拟ROS] 发送Topic（向HIS Listener发送状态）: {ROS_LISTEN_TOPIC}")

    async with websockets.serve(handle_ros_client, ROS_WS_HOST, ROS_WS_PORT):
        print(f"[模拟ROS] 服务器已启动，等待HIS Sender连接...")
        await asyncio.Future()


class MockHISSender:

    def __init__(self):
        self.ws_connection = None
        self.running = False
        self.prescription_code = None
        self.medicine_list = []
        self.medicine_total = 0
        self.current_medicine_index = 0
        self.started_event = asyncio.Event()
        self.step5_return_event = asyncio.Event()
        self.all_completed_event = asyncio.Event()
        self.task_end_event = asyncio.Event()

    async def connect(self):
        print(f"\n[HIS Sender] 连接ROS WebSocket: {ROS_WS_URL}")
        self.ws_connection = await asyncio.wait_for(
            websockets.connect(ROS_WS_URL),
            timeout=5
        )
        print(f"[HIS Sender] 连接成功")

        await self.ws_connection.send(json.dumps({
            "op": "unadvertise",
            "topic": ROS_TOPIC
        }))
        await asyncio.sleep(0.1)

        await self.ws_connection.send(json.dumps({
            "op": "advertise",
            "topic": ROS_TOPIC,
            "type": ROS_MSG_TYPE
        }))
        await asyncio.sleep(0.3)
        print(f"[HIS Sender] Topic注册成功: {ROS_TOPIC} ({ROS_MSG_TYPE})")

    async def listen_ros_messages(self):
        try:
            async for raw_message in self.ws_connection:
                try:
                    msg = json.loads(raw_message)
                    if msg.get("op") == "publish" and msg.get("topic") == ROS_LISTEN_TOPIC:
                        msg_data = msg.get("msg", {})
                        data = msg_data.get("data", "")
                        await self.handle_ros_status(data)
                except json.JSONDecodeError:
                    print(f"[HIS Sender] 非JSON消息: {raw_message}")
        except websockets.exceptions.ConnectionClosed:
            print("[HIS Sender] ROS连接已关闭")
        except Exception as e:
            print(f"[HIS Sender] 监听消息异常: {e}")

    async def handle_ros_status(self, data: str):
        print(f"\n[HIS Sender] ← 收到ROS状态: {data}")

        parts = data.split("_")
        if len(parts) >= 3:
            try:
                medicine_id = int(parts[0])
                is_medicine_id = len(parts[0]) <= 5
                if is_medicine_id:
                    prescription_code = parts[1]
                    status = "_".join(parts[2:])
                else:
                    prescription_code = parts[0]
                    status = "_".join(parts[1:])
                    medicine_id = None
            except ValueError:
                prescription_code = parts[0]
                status = "_".join(parts[1:])
                medicine_id = None
        elif len(parts) == 2:
            prescription_code = parts[0]
            status = parts[1]
            medicine_id = None
        else:
            status = data
            prescription_code = None
            medicine_id = None

        if status == "running-started":
            print(f"[HIS Sender]   → 触发 started_event")
            self.started_event.set()
        elif status == "running-step5-waiting-end":
            print(f"[HIS Sender]   → 触发 step5_return_event")
            self.step5_return_event.set()
        elif status == "all_completed":
            print(f"[HIS Sender]   → 触发 all_completed_event")
            self.all_completed_event.set()
        elif status == "end":
            print(f"[HIS Sender]   → 触发 task_end_event")
            self.task_end_event.set()

    async def send_medicine_to_ros(self, medicine_data, medicine_index, data):
        medicine_id = medicine_data["medicine_id"]
        medicine_name = medicine_data.get("medicine_name", "未知药品")
        medicines_id = medicine_data.get("medicines_id", "未知")
        medicines_name = medicine_data.get("medicines_name", "未知")

        message_dict = {
            "op": "publish",
            "topic": ROS_TOPIC,
            "msg": {
                "data": data,
                "prescription_code": self.prescription_code,
                "medicine_id": medicine_id,
                "x": medicine_data["x"],
                "y": medicine_data["y"],
                "z": medicine_data["z"],
                "yaw": medicine_data["yaw"],
                "medicine_total": self.medicine_total,
                "medicine_index": medicine_index
            }
        }

        print(f"\n[HIS Sender] → 发送药品消息:")
        print(f"[HIS Sender]   data: {data}")
        print(f"[HIS Sender]   prescription_code: {self.prescription_code}")
        print(f"[HIS Sender]   关联路径:")
        print(f"[HIS Sender]     医生下药: medicines.id={medicines_id}, name=\"{medicines_name}\"")
        print(f"[HIS Sender]     → 通过名称关联 medicine_locations.medicine_name=\"{medicine_name}\"")
        print(f"[HIS Sender]     → 最终发送: medicine_id={medicine_id}")
        print(f"[HIS Sender]   medicine_index: {medicine_index}/{self.medicine_total}")
        print(f"[HIS Sender]   坐标: x={medicine_data['x']}, y={medicine_data['y']}, z={medicine_data['z']}, yaw={medicine_data['yaw']}")

        await self.ws_connection.send(json.dumps(message_dict))

    async def send_medicine_end_to_ros(self, medicine_data, medicine_index):
        medicine_id = medicine_data["medicine_id"]

        for send_count in range(2):
            message_dict = {
                "op": "publish",
                "topic": ROS_TOPIC,
                "msg": {
                    "data": "end",
                    "prescription_code": self.prescription_code,
                    "medicine_id": medicine_id,
                    "x": medicine_data["x"],
                    "y": medicine_data["y"],
                    "z": medicine_data["z"],
                    "yaw": medicine_data["yaw"],
                    "medicine_total": self.medicine_total,
                    "medicine_index": medicine_index
                }
            }

            print(f"\n[HIS Sender] → 发送end信号（第{send_count+1}次/共2次）")
            await self.ws_connection.send(json.dumps(message_dict))

            if send_count == 0:
                print(f"[HIS Sender] 等待2秒后发送第二次...")
                await asyncio.sleep(SEND_INTERVAL)

    async def process_single_medicine(self, medicine_data, medicine_index):
        medicine_id = medicine_data["medicine_id"]
        medicine_name = medicine_data.get("medicine_name", "未知药品")
        medicines_id = medicine_data.get("medicines_id", "未知")
        medicines_name = medicine_data.get("medicines_name", "未知")

        print(f"\n[HIS Sender] {'='*60}")
        print(f"[HIS Sender] 开始处理药品 {medicine_index}/{self.medicine_total}")
        print(f"[HIS Sender]   医生下药: medicines.id={medicines_id}, name=\"{medicines_name}\"")
        print(f"[HIS Sender]   坐标来源: medicine_locations.medicine_id={medicine_id}, name=\"{medicine_name}\"")
        print(f"[HIS Sender] {'='*60}")

        self.started_event.clear()
        self.step5_return_event.clear()

        print(f"\n[HIS Sender] 阶段1：发送start，等待running-started")
        send_count = 0
        while not self.started_event.is_set() and self.running:
            send_count += 1
            print(f"[HIS Sender] 发送start（第{send_count}次）")
            await self.send_medicine_to_ros(medicine_data, medicine_index, "start")
            try:
                await asyncio.wait_for(self.started_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.running:
            return False

        print(f"[HIS Sender] [OK] 收到running-started（共发送{send_count}次start）")

        print(f"\n[HIS Sender] 阶段2：发送running，等待running-step5-waiting-end")
        send_count = 0
        while not self.step5_return_event.is_set() and self.running:
            send_count += 1
            print(f"[HIS Sender] 发送running（第{send_count}次）")
            await self.send_medicine_to_ros(medicine_data, medicine_index, "running")
            try:
                await asyncio.wait_for(self.step5_return_event.wait(), timeout=SEND_INTERVAL)
            except asyncio.TimeoutError:
                pass

        if not self.running:
            return False

        print(f"[HIS Sender] [OK] 收到running-step5-waiting-end（共发送{send_count}次running）")

        print(f"\n[HIS Sender] 阶段3：发送end（两次，间隔2秒）")
        await self.send_medicine_end_to_ros(medicine_data, medicine_index)

        print(f"\n[HIS Sender] 阶段4：等待3秒，让ROS端处理end消息...")
        await asyncio.sleep(3)

        print(f"[HIS Sender] [OK] 药品 {medicine_index}/{self.medicine_total} 处理完成")
        print(f"[HIS Sender]   医生下药: medicines.id={medicine_data.get('medicines_id', '未知')}, name=\"{medicine_data.get('medicines_name', '未知')}\"")
        print(f"[HIS Sender]   发送给ROS: medicine_id={medicine_id}, name=\"{medicine_data.get('medicine_name', '未知')}\"")
        return True

    async def run(self):
        print(f"\n{'='*60}")
        print(f"[HIS Sender] 启动模拟HIS Sender")
        print(f"{'='*60}")

        presc = get_latest_pending_prescription()
        if not presc:
            print("[HIS Sender] 没有pending处方，退出")
            return

        self.prescription_code = presc["prescription_code"]
        print(f"[HIS Sender] 处理处方: {self.prescription_code}")

        self.medicine_list = get_prescription_medicine_locations(self.prescription_code)
        if not self.medicine_list:
            print("[HIS Sender] 没有药品坐标，退出")
            return

        self.medicine_total = len(self.medicine_list)

        await self.connect()

        self.running = True
        listen_task = asyncio.create_task(self.listen_ros_messages())

        try:
            for idx, medicine_data in enumerate(self.medicine_list):
                medicine_index = idx + 1
                success = await self.process_single_medicine(medicine_data, medicine_index)
                if not success:
                    break
                if idx < self.medicine_total - 1:
                    print(f"\n[HIS Sender] 等待2秒后处理下一个药品...")
                    await asyncio.sleep(SEND_INTERVAL)

            print(f"\n[HIS Sender] 所有药品已发送完成")
            print(f"[HIS Sender] 模拟ROS端发送药单级状态...")
            await send_prescription_level_status(self.ws_connection, self.prescription_code, "all_completed")
            await asyncio.sleep(1)
            await send_prescription_level_status(self.ws_connection, self.prescription_code, "end")

        finally:
            self.running = False
            listen_task.cancel()
            await self.ws_connection.close()
            print(f"\n[HIS Sender] 测试完成")


async def main():
    print("=" * 60)
    print("ROS互通完整流程测试脚本")
    print("=" * 60)
    print(f"HIS数据库: {HIS_DB_CONFIG['host']}:{HIS_DB_CONFIG['port']}/{HIS_DB_CONFIG['database']}")
    print(f"模拟ROS WebSocket: {ROS_WS_URL}")
    print(f"发送Topic（HIS→ROS）: {ROS_TOPIC}")
    print(f"监听Topic（ROS→HIS）: {ROS_LISTEN_TOPIC}")
    print("=" * 60)

    input("\n按回车键开始测试...")

    ros_server_task = asyncio.create_task(start_mock_ros_server())
    await asyncio.sleep(1)

    sender = MockHISSender()
    await sender.run()

    ros_server_task.cancel()
    print("\n测试完成！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试已中断")
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
    input("\n按回车键退出...")