# -*- coding: utf-8 -*-
"""
车1 通信独立测试脚本（不依赖大屏后端，topic 与消息格式与正式系统完全一致）
=====================================================================
正式系统对应关系（仅作参照，本脚本不 import 后端代码）：
  - 发送 topic: /rxzy_msg        (msg type: rxzy_msg/his_sub)   ← CAR1_SEND_TOPIC
  - 接收 topic: /car01_pub       (std_msgs/String)              ← CAR1_TOPIC
  - 9 字段消息格式与 his_sender.py send_medicine_to_ros 完全一致：
    data / prescription_code / medicine_id / x / y / z / yaw /
    medicine_total / medicine_index

用法：
  python car1_comm_test.py                # 交互模式（监听 + 菜单发送）
  python car1_comm_test.py --listen       # 仅监听车1上报，不发送
  Ctrl+C 停止

依赖：pip install websockets
"""
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("缺少依赖：pip install websockets")
    sys.exit(1)

# ===== 连接配置（与 hospital_dashboard_backend/.env 车1 一致，topic/格式不变）=====
WS_HOST = "192.168.51.43"
WS_PORT = 9090
SEND_TOPIC = "/rxzy_msg"      # 后端 → 车1
SEND_MSG_TYPE = "rxzy_msg/his_sub"  # ← CAR1_SEND_MSG_TYPE
RECV_TOPIC = "/car01_pub"     # 车1 → 后端
RECV_MSG_TYPE = "std_msgs/String"
SEND_INTERVAL = 2             # 与后端 SEND_INTERVAL 一致（end 发 2 次的间隔）

# ===== 测试参数默认值（菜单 0 可修改）=====
params = {
    "prescription_code": "RX20250907001",
    "medicine_id": 1,
    "x": 1.54,
    "y": -0.39,
    "z": 0.0,
    "yaw": 0.0,
    "medicine_total": 1,
    "medicine_index": 1,
}


def parse_receipt(data: str) -> dict:
    """解析车1 回执（与后端 ros_listener.parse_ros_message 规则一致，仅取所需）"""
    if data.startswith("{") and data.endswith("}"):
        try:
            msg = json.loads(data)
            return {
                "status": msg.get("status", ""),
                "prescription_code": msg.get("prescription_code"),
                "medicine_id": msg.get("medicine_id"),
            }
        except json.JSONDecodeError:
            pass
    if "|" in data:
        parts = data.split("|")
        return {"status": parts[0],
                "prescription_code": parts[1] if len(parts) > 1 else None,
                "medicine_id": None}
    parts = data.split("_")
    if len(parts) >= 3:
        try:
            mid = int(parts[0])
            if len(parts[0]) <= 5:
                return {"status": "_".join(parts[2:]),
                        "prescription_code": parts[1],
                        "medicine_id": mid}
        except ValueError:
            pass
        return {"status": "_".join(parts[1:]),
                "prescription_code": parts[0],
                "medicine_id": None}
    if len(parts) == 2:
        return {"status": parts[1], "prescription_code": parts[0], "medicine_id": None}
    return {"status": data, "prescription_code": None, "medicine_id": None}


def build_publish_msg(data: str, p: dict) -> str:
    """构造 rosbridge publish 消息（9 字段，与后端格式一字不差）"""
    return json.dumps({
        "op": "publish",
        "topic": SEND_TOPIC,
        "msg": {
            "data": data,
            "prescription_code": p["prescription_code"],
            "medicine_id": p["medicine_id"],
            "x": p["x"],
            "y": p["y"],
            "z": p["z"],
            "yaw": p["yaw"],
            "medicine_total": p["medicine_total"],
            "medicine_index": p["medicine_index"],
        },
    })


class Car1Tester:
    def __init__(self):
        self.send_ws = None          # 发送连接（按需建立）
        self.listen_task = None
        self.running = True

    async def ensure_send_ws(self):
        """与后端 _ensure_ws_connection 逻辑一致：
        新连接建立后必须先注册 topic（unadvertise → advertise），否则 rosbridge 丢弃 publish"""
        need = self.send_ws is None
        if not need:
            try:
                if hasattr(self.send_ws, "open") and not self.send_ws.open:
                    need = True
            except Exception:
                need = True

        if not need:
            return self.send_ws

        url = f"ws://{WS_HOST}:{WS_PORT}"
        if self.send_ws is not None:
            try:
                await self.send_ws.close()
            except Exception:
                pass
        self.send_ws = await asyncio.wait_for(
            websockets.connect(url, proxy=None), timeout=5
        )
        print(f"[连接] 发送通道已建立: {url}")

        # 注册发送 topic（与 his_sender.py:269-280 完全一致）
        await self.send_ws.send(json.dumps({
            "op": "unadvertise",
            "topic": SEND_TOPIC,
        }))
        await asyncio.sleep(0.1)
        await self.send_ws.send(json.dumps({
            "op": "advertise",
            "topic": SEND_TOPIC,
            "type": SEND_MSG_TYPE,
        }))
        await asyncio.sleep(0.3)
        print(f"[连接] Topic 注册成功: {SEND_TOPIC} ({SEND_MSG_TYPE})")
        return self.send_ws

    async def close_send_ws(self):
        if self.send_ws is not None:
            try:
                await self.send_ws.close()
            except Exception:
                pass
            self.send_ws = None
            print("[连接] 发送通道已关闭")

    # ===== 监听车1 上报 =====

    async def listen_loop(self):
        url = f"ws://{WS_HOST}:{WS_PORT}"
        while self.running:
            try:
                async with websockets.connect(url, proxy=None) as ws:
                    await ws.send(json.dumps({
                        "op": "subscribe",
                        "topic": RECV_TOPIC,
                        "type": RECV_MSG_TYPE,
                    }))
                    print(f"[监听] 已订阅 {RECV_TOPIC}，等待车1 上报...")
                    while self.running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            await ws.ping()
                            continue
                        try:
                            msg_data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if msg_data.get("op") != "publish":
                            continue
                        if msg_data.get("topic", "") != RECV_TOPIC:
                            continue
                        data = (msg_data.get("msg") or {}).get("data", "")
                        r = parse_receipt(data)
                        print(f"[收到] {r['status']} | 处方={r['prescription_code']} "
                              f"| 药品ID={r['medicine_id']} | 原始: {data}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    print(f"[监听] 连接失败: {e}，5 秒后重试...")
                    await asyncio.sleep(5)

    # ===== 发送信号 =====

    async def send_once(self, data: str):
        try:
            ws = await self.ensure_send_ws()
            msg = build_publish_msg(data, params)
            await ws.send(msg)
            print(f"[发送] {data} | 处方={params['prescription_code']} "
                  f"| 药品ID={params['medicine_id']} "
                  f"| 坐标=({params['x']},{params['y']},{params['z']},{params['yaw']})")
            return True
        except Exception as e:
            print(f"[错误] 发送失败: {e}")
            await self.close_send_ws()
            return False

    async def send_start(self, repeat: int = 1):
        """start：与后端一致——未收到回执前可重复发送（data 固定 start）"""
        for i in range(repeat):
            if not await self.send_once("start"):
                return
            if i < repeat - 1:
                await asyncio.sleep(SEND_INTERVAL)

    async def send_running(self):
        """running：药品已启动过的重发形态（后端在收到 running-started 回执后使用）"""
        await self.send_once("running")

    async def send_end(self):
        """end：与后端一致——连发 2 次，间隔 SEND_INTERVAL"""
        for i in range(2):
            if not await self.send_once("end"):
                return
            if i == 0:
                await asyncio.sleep(SEND_INTERVAL)

    async def send_pharmacist_success(self):
        """pharmacist-success：车1 单发（格式与 start 完全一致，仅 data 不同）"""
        await self.send_once("pharmacist-success")

    # ===== 参数编辑 =====

    def edit_params(self):
        print("\n----- 修改测试参数（直接回车保持原值）-----")
        for key, hint in [
            ("prescription_code", "处方编码"),
            ("medicine_id", "药品ID"),
            ("x", "坐标 x"), ("y", "坐标 y"), ("z", "坐标 z"), ("yaw", "朝向 yaw"),
            ("medicine_total", "药品总数"), ("medicine_index", "当前第几个药品"),
        ]:
            raw = input(f"{hint}[{params[key]}]: ").strip()
            if not raw:
                continue
            if key == "prescription_code":
                params[key] = raw
            elif key in ("medicine_id", "medicine_total", "medicine_index"):
                try:
                    params[key] = int(raw)
                except ValueError:
                    print("  需为整数，已忽略")
            else:
                try:
                    params[key] = float(raw)
                except ValueError:
                    print("  需为数字，已忽略")
        print(f"当前参数: {params}\n")

    # ===== 交互菜单 =====

    async def menu_loop(self):
        while self.running:
            print("\n========== 车1 通信测试 ==========")
            print(f"目标: ws://{WS_HOST}:{WS_PORT} | 发送 {SEND_TOPIC} | 监听 {RECV_TOPIC}")
            print(f"处方={params['prescription_code']} 药品ID={params['medicine_id']} "
                  f"({params['medicine_index']}/{params['medicine_total']})")
            print("----------------------------------")
            print("1. 发送 start")
            print("2. 发送 running（已启动重发形态）")
            print("3. 发送 end（自动连发 2 次）")
            print("4. 发送 pharmacist-success")
            print("5. start 连发 5 次（模拟重发，2s 间隔）")
            print("0. 修改测试参数")
            print("q. 退出")
            choice = (await asyncio.to_thread(input, "选择: ")).strip()

            if choice == "1":
                await self.send_start()
            elif choice == "2":
                await self.send_running()
            elif choice == "3":
                await self.send_end()
            elif choice == "4":
                await self.send_pharmacist_success()
            elif choice == "5":
                await self.send_start(repeat=5)
            elif choice == "0":
                self.edit_params()
            elif choice.lower() == "q":
                self.running = False
            else:
                print("无效选择")

    async def run(self):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("=" * 50)
        print("车1 通信独立测试脚本")
        print(f"发送 topic: {SEND_TOPIC} | 监听 topic: {RECV_TOPIC}")
        print("消息格式与正式系统完全一致（9 字段）")
        print("=" * 50)
        self.listen_task = asyncio.create_task(self.listen_loop())
        try:
            await self.menu_loop()
        finally:
            self.running = False
            if self.listen_task:
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    pass
            await self.close_send_ws()
            print("[退出] 测试结束")


if __name__ == "__main__":
    tester = Car1Tester()
    if "--listen" in sys.argv:
        # 仅监听模式
        async def _listen_only():
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            print(f"仅监听模式：{RECV_TOPIC} @ ws://{WS_HOST}:{WS_PORT}，Ctrl+C 停止")
            await tester.listen_loop()
        asyncio.run(_listen_only())
    else:
        asyncio.run(tester.run())
