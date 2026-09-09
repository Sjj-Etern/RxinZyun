# -*- coding: utf-8 -*-
"""
车2 通信独立测试脚本（根据 car1_comm_test.py 重写，不依赖大屏后端与数据库）
=====================================================================
正式系统对应关系（仅作参照，本脚本不 import 后端代码）：
  - 发送 topic: /car02_rxzy_msg   (msg type: std_msgs/String)    ← CAR2_SEND_TOPIC
  - 接收 topic: /car02_pub        (std_msgs/String)              ← CAR2_TOPIC

与车1脚本的三点关键差异（复刻 his_sender.py 车分支）：
  1. 连接对象不同：车2 rosbridge ws://192.168.51.16:9090（车1 是 192.168.51.43）
  2. 消息类型与格式不同：车2 用字符串消息 std_msgs/String + 纯 data 载荷
     （his_sender._publish_signal_once 的 msg_fields=None 分支），
     信息全拼在 data 内，严禁携带车1式 9 字段：
       {"data": "{处方码}_pharmacist-success"}
     （车1 是自定义消息 rxzy_msg/his_sub + 9 字段结构化格式 send_medicine_to_ros）
  3. 发送方式不同：车2 信号为连续发送（每 CAR2_SIGNAL_INTERVAL=2 秒重发），
     直到收到对应回执或切换下一信号；nurse-success 末位固定发 3 次自动停

复刻的车2 通信机制：
  ① pharmacist-success 连发，收到 lift-arrive 自动停（起始节点，手动触发不查库）
  ② lift-arrive 回执 → 9 步电梯编排（开门/跨楼/关门/查层/go_floor/到站开门）
  ③ lift-across / lift-open 连发（信号切换自动停）
  ④ nurse_arrive 上报（仅语音提示，不解锁 Step7，与真实系统一致）
  ⑤ nurse-success 固定发 3 次自动停
  ⑥ 电梯 TCP 协议（JSON+\n、seq 序列号、ACK 回执、floor_arrived 到达上报）
  ⑦ UDP 发现协议（ESP32 discovery 广播 → 回复 config）

用法：
  python car2_comm_test.py                # 交互模式（监听 + 菜单发送）
  python car2_comm_test.py --listen       # 仅监听车2上报，不发送
  Ctrl+C 停止

依赖：pip install websockets
"""
import asyncio
import json
import socket
import sys

try:
    import websockets
except ImportError:
    print("缺少依赖：pip install websockets")
    sys.exit(1)

# ===== 连接配置（与 hospital_dashboard_backend/.env 车2 一致）=====
WS_HOST = "192.168.51.16"       # ← CAR2_WS_HOST（车1 是 192.168.51.43）
WS_PORT = 9090                  # ← CAR2_WS_PORT
SEND_TOPIC = "/car02_rxzy_msg"  # ← CAR2_SEND_TOPIC（车1 是 /rxzy_msg）
# 车2 端节点用字符串消息订阅（std_msgs/String），不用车1 的自定义类型。
# .env 原 CAR2_SEND_MSG_TYPE=his_sub 为错误配置（非法类型名，rosbridge 会拒绝注册）。
SEND_MSG_TYPE = "std_msgs/String"
RECV_TOPIC = "/car02_pub"       # ← CAR2_TOPIC（车1 是 /car01_pub）
RECV_MSG_TYPE = "std_msgs/String"
SIGNAL_INTERVAL = 2             # ← CAR2_SIGNAL_INTERVAL，连发间隔

# ===== 电梯配置（与 .env ELEVATOR_* 一致）=====
ELEVATOR_TCP_HOST = "0.0.0.0"
ELEVATOR_TCP_PORT = 10833
ELEVATOR_UDP_PORT = 10832
ELEVATOR_CMD_TIMEOUT = 10       # ← ELEVATOR_CMD_TIMEOUT
ELEVATOR_TARGET_FLOOR = 4       # ← ELEVATOR_TARGET_FLOOR
DOOR_OPEN_DELAY = 3             # ← ELEVATOR_DOOR_OPEN_DELAY 开门后等待
DOOR_CLOSE_DELAY = 3            # ← ELEVATOR_DOOR_CLOSE_DELAY 关门后等待
FLOOR_ARRIVE_TIMEOUT = 20       # ← ELEVATOR_FLOOR_ARRIVE_TIMEOUT floor_arrived 兜底
ACROSS_DELAY = 4                # elevator_across_to_go_floor_delay（config 默认5）：发 lift-across 后等车2进梯

# ===== 系统级延迟（复刻 .env / workflow.py:412,540，当前=0 立即发送）=====
PHARMACIST_SUCCESS_DELAY = 0    # ← PHARMACIST_SUCCESS_DELAY：节点3扫码完成→延迟N秒再启动连发
NURSE_SUCCESS_DELAY = 0         # ← NURSE_SUCCESS_DELAY：节点4扫码确认→延迟N秒再触发 nurse-success

# ===== 测试参数（菜单 0 可修改）=====
prescription_code = "RX20250909001"


def parse_receipt(data: str) -> dict:
    """解析车2 上报（{处方码}_{状态}，与后端 ros_listener 解析规则一致）"""
    if "|" in data:
        parts = data.split("|")
        return {"status": parts[0], "prescription_code": parts[1] if len(parts) > 1 else None}
    parts = data.split("_", 1)
    if len(parts) == 2:
        return {"status": parts[1], "prescription_code": parts[0]}
    return {"status": data, "prescription_code": None}


class Car2Tester:
    def __init__(self):
        self.send_ws = None          # 发送连接（按需建立）
        self.listen_task = None
        self.drain_task = None
        self.running = True
        # ---- 连续发送状态（复刻 his_sender._continuous_*）----
        self._signal_task = None
        self._stop_event = None
        self._signal_name = None
        # ---- 编排状态 ----
        self._step7_event = asyncio.Event()   # 复刻 ros_listener._nurse_arrive_event
        self._orchestration_task = None
        # ---- 电梯 TCP 状态（复刻 elevator_control）----
        self._esp_writer = None
        self._esp_reader = None
        self._cmd_seq = 0
        self._pending_ack = None
        self._floor_arrived_event = asyncio.Event()
        self._client_lock = asyncio.Lock()
        self.elevator_connected = False

    # ===== 发送通道（与 car1 脚本一致：注册后 publish 才不被丢弃）=====

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

        # 注册发送 topic（与 his_sender.py 完全一致）
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

        # 后台打印 rosbridge 返回的 error/status（避免注册/发布被拒时静默）
        if self.drain_task:
            self.drain_task.cancel()
        self.drain_task = asyncio.create_task(self._drain_loop())
        return self.send_ws

    async def _drain_loop(self):
        """读取发送通道上 rosbridge 的返回消息，打印 error/status"""
        try:
            async for raw in self.send_ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if msg.get("op") == "status":
                    print(f"[rosbridge] level={msg.get('level')} {msg.get('msg')}")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def close_send_ws(self):
        if self.drain_task:
            self.drain_task.cancel()
            self.drain_task = None
        if self.send_ws is not None:
            try:
                await self.send_ws.close()
            except Exception:
                pass
            self.send_ws = None
            print("[连接] 发送通道已关闭")

    # ===== 发送信号（车2 专属：纯 data 载荷，与车1 的 9 字段不同）=====

    async def send_once(self, signal: str) -> bool:
        """发送一次。载荷只有 data 字段：{"data": "{处方码}_{信号}"}
        （his_sender._publish_signal_once 车2 分支，实测车2端节点对多余字段报错）"""
        try:
            ws = await self.ensure_send_ws()
            await ws.send(json.dumps({
                "op": "publish",
                "topic": SEND_TOPIC,
                "msg": {"data": f"{prescription_code}_{signal}"},
            }))
            print(f"[发送] {signal} | {prescription_code}_{signal}")
            return True
        except Exception as e:
            print(f"[错误] 发送失败: {e}")
            await self.close_send_ws()
            return False

    # ===== 连续发送框架（复刻 his_sender:333-395）=====

    async def start_signal(self, signal_name: str, max_sends=None):
        """启动连发：先停当前信号（信号切换即停）；max_sends=N 发 N 次自动停"""
        await self.stop_signal()
        self._stop_event = asyncio.Event()
        self._signal_name = signal_name
        self._signal_task = asyncio.create_task(
            self._signal_loop(signal_name, self._stop_event, max_sends))

    async def stop_signal(self):
        """停止当前连发（收到对应回执时调用，复刻 stop_current_signal）"""
        if self._stop_event is not None:
            self._stop_event.set()
        task = self._signal_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
            except Exception:
                pass
        self._signal_task = None
        self._stop_event = None
        self._signal_name = None

    async def _signal_loop(self, signal_name: str, stop_event: asyncio.Event, max_sends):
        count = 0
        try:
            while not stop_event.is_set():
                if max_sends is not None and count >= max_sends:
                    break
                count += 1
                ok = await self.send_once(signal_name)
                print(f"[连发] {signal_name} 第{count}次 {'✓' if ok else '✗'}")
                if max_sends is not None and count >= max_sends:
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=SIGNAL_INTERVAL)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            print(f"[停止] {signal_name}（共发送 {count} 次）")

    # ===== 监听车2 上报（含回显示证：同时订阅自己的发送话题）=====

    async def listen_loop(self):
        url = f"ws://{WS_HOST}:{WS_PORT}"
        while self.running:
            try:
                async with websockets.connect(url, proxy=None) as ws:
                    # 订阅车2 上报（与后端 ros_listener 订阅格式一致）
                    await ws.send(json.dumps({
                        "op": "subscribe",
                        "topic": RECV_TOPIC,
                        "type": RECV_MSG_TYPE,
                    }))
                    # 回显示证：订阅自己的发送话题，收到回显 = 消息确实进入车2 ROS 图
                    await ws.send(json.dumps({
                        "op": "subscribe",
                        "topic": SEND_TOPIC,
                    }))
                    print(f"[监听] 已订阅 {RECV_TOPIC}（车2上报）+ {SEND_TOPIC}（回显）")
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
                        topic = msg_data.get("topic", "")
                        data = (msg_data.get("msg") or {}).get("data", "")
                        if topic == SEND_TOPIC:
                            print(f"[回显✓] 消息已进入车2 ROS 图: {data}")
                            continue
                        if topic != RECV_TOPIC:
                            continue
                        await self._handle_car2_report(data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    print(f"[监听] 连接失败: {e}，5 秒后重试...")
                    await asyncio.sleep(5)

    async def _handle_car2_report(self, data: str):
        """处理车2 上报（复刻 ros_listener 各分支行为）"""
        r = parse_receipt(data)
        status = r["status"]
        print(f"[收到] {status} | 处方={r['prescription_code']} | 原始: {data}")

        if status == "lift-arrive":
            # 收到 lift-arrive → 停① pharmacist-success 连发 → 启动 9 步电梯编排
            if self._orchestration_task is None or self._orchestration_task.done():
                self._orchestration_task = asyncio.create_task(
                    self._lift_arrive_orchestration(r["prescription_code"]))
            else:
                print("[警告] 编排已在进行中，忽略本次 lift-arrive")
        elif status == "nurse_arrive":
            # 与真实系统一致：仅语音播报+记录 N14，不解锁 Step7
            print("[语音模拟] 播报：药物已送达请您确认（连播2次）→ 记录 N14 节点")
            print("[提示] Step7 仍锁定，需菜单选 7 模拟 HIS 节点4 扫码确认解锁")
        else:
            print(f"[提示] 未识别的车2状态: {status}（本脚本仅处理 lift-arrive / nurse_arrive）")

    # ===== lift-arrive 9 步编排（复刻 ros_listener:763-841）=====

    async def _lift_arrive_orchestration(self, code: str):
        print(f"===== 9步编排开始（处方={code}）=====")
        # Step 0: 停① + 清护士到达信号（复刻 ros_listener:774-778）
        self._step7_event.clear()
        await self.stop_signal()
        print("[Step0] 停止 pharmacist-success 连发，清除护士到达信号")
        try:
            # Step 1: 电梯开门
            if self.elevator_connected:
                await self.elevator_send({"cmd": "open_door"})
                print("[节点N8] 电梯门已打开")
                await asyncio.sleep(DOOR_OPEN_DELAY)
            else:
                print("[Step1] 电梯ESP32未连接，跳过开门")
            # Step 2: 连发 lift-across —— 电梯运动【前】发送：通知车2 跨梯进电梯
            # （电梯运动结束后发的是 lift-open 见 Step 6；与 ros_listener.py:789-794 一致）
            await self.start_signal("lift-across")
            print("[节点N9] 车2跨梯运输中（车2进梯中）")
            # Step 3: 串行等待（车2进梯）
            await asyncio.sleep(ACROSS_DELAY)
            # Step 4: 电梯关门
            if self.elevator_connected:
                await self.elevator_send({"cmd": "close_door"})
                print("[节点N10] 电梯门已关闭")
                await asyncio.sleep(DOOR_CLOSE_DELAY)
            # Step 5: 查层 → go_floor → 等 floor_arrived（真实到达上报，20s兜底）
            if self.elevator_connected:
                ack = await self.elevator_send({"cmd": "status"})
                current_floor = ack.get("floor", 0)
                if current_floor != ELEVATOR_TARGET_FLOOR:
                    self._floor_arrived_event.clear()
                    await self.elevator_send({"cmd": "go_floor", "floor": ELEVATOR_TARGET_FLOOR})
                    try:
                        await asyncio.wait_for(self._floor_arrived_event.wait(),
                                               timeout=FLOOR_ARRIVE_TIMEOUT)
                        print(f"[节点N11] 电梯已到达{ELEVATOR_TARGET_FLOOR}楼")
                    except asyncio.TimeoutError:
                        print(f"[警告] floor_arrived {FLOOR_ARRIVE_TIMEOUT}s 超时，兜底继续")
                else:
                    print(f"[Step5] 电梯已在{ELEVATOR_TARGET_FLOOR}楼，跳过 go_floor")
                # Step 5.5: 到站开门
                await self.elevator_send({"cmd": "open_door"})
                print(f"[节点N12] 电梯已到{ELEVATOR_TARGET_FLOOR}楼并开门")
                await asyncio.sleep(DOOR_OPEN_DELAY)
            # Step 6: 连发 lift-open（信号切换自动停 lift-across）
            await self.start_signal("lift-open")
            print("[节点N12] 已通知车2开门送出")
            # Step 7: 等待护士扫码确认（真实系统由 HIS 节点4 API 解锁）
            print("[Step7] 等待护士扫码确认…（菜单选 7 解锁）")
            await self._step7_event.wait()
            # Step 8: 停⑤ → 发 nurse-success（固定 3 次自动停）
            await self.stop_signal()
            await self.start_signal("nurse-success", max_sends=3)
            print("[节点N15] 护士已确认，任务完成")
        except Exception as e:
            print(f"[编排异常] {e}")
        finally:
            print("===== 9步编排结束 =====")

    # ===== 电梯 TCP 服务端（复刻 elevator_control.py）=====

    async def start_elevator_server(self):
        server = await asyncio.start_server(
            self._handle_esp32, ELEVATOR_TCP_HOST, ELEVATOR_TCP_PORT)
        print(f"[电梯] TCP服务端已启动，监听: {ELEVATOR_TCP_HOST}:{ELEVATOR_TCP_PORT}（等ESP32连入）")
        asyncio.create_task(self._udp_discovery())

    async def _handle_esp32(self, reader, writer):
        peer = writer.get_extra_info("peername")
        print(f"[电梯] ESP32已连接: {peer[0]}:{peer[1]}")
        async with self._client_lock:
            if self._esp_writer is not None:
                try:
                    self._esp_writer.close()
                except Exception:
                    pass
            self._esp_writer = writer
            self._esp_reader = reader
            self.elevator_connected = True
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue
                try:
                    await self._handle_esp32_msg(json.loads(line_str))
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            async with self._client_lock:
                if self._esp_writer is writer:
                    self._esp_writer = None
                    self._esp_reader = None
                    self.elevator_connected = False
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            print(f"[电梯] ESP32已断开: {peer[0]}:{peer[1]}")

    async def _handle_esp32_msg(self, msg: dict):
        msg_type = msg.get("type", "")
        if msg_type == "ack":
            extra = "".join(f", {k}={msg[k]}"
                            for k in ("floor", "temp", "humi", "power") if k in msg)
            print(f"[电梯] [收到] ACK | cmd={msg.get('cmd')} | seq={msg.get('seq')}{extra}")
            if self._pending_ack and not self._pending_ack.done():
                self._pending_ack.set_result(msg)
        elif msg_type == "floor_arrived":
            print(f"[电梯] [收到] FLOOR_ARRIVED | floor={msg.get('floor')}（真实到达上报）")
            self._floor_arrived_event.set()
        elif msg_type == "status":
            pass

    async def elevator_send(self, cmd: dict) -> dict:
        """发送命令并等 ACK（seq 序列号 + 超时，与 elevator_control._send_command 一致）"""
        if self._esp_writer is None:
            raise RuntimeError("ESP32 未连接，无法发送命令")
        self._cmd_seq += 1
        cmd["seq"] = self._cmd_seq
        async with self._client_lock:
            self._pending_ack = asyncio.get_event_loop().create_future()
        floor_info = f" floor={cmd['floor']}" if "floor" in cmd else ""
        print(f"[电梯] [发送] {cmd.get('cmd')}{floor_info} | 序列号={self._cmd_seq}")
        self._esp_writer.write((json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._esp_writer.drain()
        try:
            ack = await asyncio.wait_for(self._pending_ack, timeout=ELEVATOR_CMD_TIMEOUT)
            print(f"[电梯] [收到] ACK确认 | 序列号={self._cmd_seq}")
            return ack
        except asyncio.TimeoutError:
            print(f"[电梯] [超时] {cmd.get('cmd')} | {ELEVATOR_CMD_TIMEOUT}s无ACK")
            raise
        finally:
            async with self._client_lock:
                self._pending_ack = None

    async def _udp_discovery(self):
        """UDP 发现协议：ESP32 广播 discovery → 单播回复 config(ip,port)"""
        class Proto(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                try:
                    msg = json.loads(data.decode("utf-8", errors="ignore").strip())
                except json.JSONDecodeError:
                    return
                if msg.get("type") == "discovery":
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        s.connect((addr[0], 80))
                        local_ip = s.getsockname()[0]
                    except Exception:
                        local_ip = "127.0.0.1"
                    finally:
                        s.close()
                    resp = json.dumps(
                        {"type": "config", "ip": local_ip, "port": ELEVATOR_TCP_PORT})
                    self.transport.sendto(resp.encode(), addr)
                    print(f"[电梯UDP] [收到] discovery | from={addr[0]} → 已回复 config")

        loop = asyncio.get_event_loop()
        await loop.create_datagram_endpoint(
            Proto, local_addr=("0.0.0.0", ELEVATOR_UDP_PORT), allow_broadcast=True)
        print(f"[电梯UDP] 发现响应已启动，端口={ELEVATOR_UDP_PORT}")

    # ===== 电梯手动命令 =====

    async def elevator_manual(self):
        cmd = (await asyncio.to_thread(
            input,
            "电梯命令(open/close/status/go_floor/power_on/power_off，楼层如 go_floor:4): "
        )).strip().lower()
        if not cmd:
            return
        try:
            if cmd == "open":
                await self.elevator_send({"cmd": "open_door"})
            elif cmd == "close":
                await self.elevator_send({"cmd": "close_door"})
            elif cmd == "status":
                await self.elevator_send({"cmd": "status"})
            elif cmd.startswith("go_floor"):
                floor = int(cmd.split(":")[1]) if ":" in cmd else ELEVATOR_TARGET_FLOOR
                self._floor_arrived_event.clear()
                await self.elevator_send({"cmd": "go_floor", "floor": floor})
            elif cmd == "power_on":
                await self.elevator_send({"cmd": "power_on"})
            elif cmd == "power_off":
                await self.elevator_send({"cmd": "power_off"})
            else:
                print(f"未知电梯命令: {cmd}")
        except RuntimeError as e:
            print(f"[电梯] {e}")
        except asyncio.TimeoutError:
            pass

    # ===== 交互菜单 =====

    async def menu_loop(self):
        global prescription_code
        while self.running:
            print("\n========== 车2 通信测试 ==========")
            print(f"目标: ws://{WS_HOST}:{WS_PORT} | 发送 {SEND_TOPIC} | 监听 {RECV_TOPIC}")
            print(f"处方={prescription_code} | 连发间隔={SIGNAL_INTERVAL}s | "
                  f"电梯连接={'✓' if self.elevator_connected else '✗'}")
            print("----------------------------------")
            print("1. 发送 pharmacist-success（连发，收到 lift-arrive 自动停）")
            print("2. 发送 lift-across（连发，切换信号时自动停）")
            print("3. 发送 lift-open（连发，切换信号时自动停）")
            print("4. 发送 nurse-success（固定发 3 次自动停）")
            print("5. 停止当前连发")
            print("6. 模拟收到 lift-arrive（无车测试 9 步编排）")
            print("7. 模拟 HIS 节点4 扫码确认（解锁 Step7）")
            print("8. 电梯手动命令")
            print("0. 修改处方编码")
            print("s. 查看状态")
            print("q. 退出")
            choice = (await asyncio.to_thread(input, "选择: ")).strip()

            if choice == "1":
                # 复刻 workflow.py:412-415：节点3扫码完成 → 延迟 PHARMACIST_SUCCESS_DELAY 再发送
                if PHARMACIST_SUCCESS_DELAY > 0:
                    print(f"[延迟] 节点3扫码完成，{PHARMACIST_SUCCESS_DELAY}s 后发送 "
                          f"pharmacist-success（PHARMACIST_SUCCESS_DELAY）")
                    await asyncio.sleep(PHARMACIST_SUCCESS_DELAY)
                print("[手动触发] 模拟节点3扫码成功 → 启动 pharmacist-success 连发")
                await self.start_signal("pharmacist-success")
            elif choice == "2":
                await self.start_signal("lift-across")
            elif choice == "3":
                await self.start_signal("lift-open")
            elif choice == "4":
                await self.start_signal("nurse-success", max_sends=3)
            elif choice == "5":
                await self.stop_signal()
                print("[手动] 已停止当前连发")
            elif choice == "6":
                await self._handle_car2_report(f"{prescription_code}_lift-arrive")
            elif choice == "7":
                if self._step7_event.is_set():
                    print("[提示] Step7 已解锁过")
                else:
                    # 复刻 workflow.py:540-545：节点4扫码确认 → 延迟 NURSE_SUCCESS_DELAY 再触发
                    if NURSE_SUCCESS_DELAY > 0:
                        print(f"[延迟] 节点4扫码确认，{NURSE_SUCCESS_DELAY}s 后触发 "
                              f"nurse-success（NURSE_SUCCESS_DELAY）")
                        await asyncio.sleep(NURSE_SUCCESS_DELAY)
                    self._step7_event.set()
                    print("[手动] 模拟 HIS 节点4 扫码全部确认 → Step7 已解锁")
            elif choice == "8":
                await self.elevator_manual()
            elif choice == "0":
                new_code = (await asyncio.to_thread(
                    input, f"处方编码[{prescription_code}]: ")).strip()
                if new_code:
                    prescription_code = new_code
                    print(f"处方编码已设为: {prescription_code}")
            elif choice.lower() == "s":
                print(f"[状态] 当前连发={self._signal_name or '无'} | "
                      f"Step7解锁={self._step7_event.is_set()} | "
                      f"电梯连接={self.elevator_connected} | "
                      f"发送WS={'已连接' if (self.send_ws and self.send_ws.open) else '未连接'}")
            elif choice.lower() == "q":
                self.running = False
            else:
                print("无效选择")

    async def run(self):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("=" * 60)
        print("车2 通信独立测试脚本（根据 car1_comm_test.py 重写）")
        print(f"发送 topic: {SEND_TOPIC} ({SEND_MSG_TYPE}) | 监听 topic: {RECV_TOPIC}")
        print('消息格式: 纯 data 载荷 {"data": "<处方码>_信号"}（车2 专属，非车1 9字段）')
        print(f"电梯 TCP: {ELEVATOR_TCP_HOST}:{ELEVATOR_TCP_PORT} | UDP发现: {ELEVATOR_UDP_PORT}")
        print("=" * 60)
        await self.start_elevator_server()
        self.listen_task = asyncio.create_task(self.listen_loop())
        try:
            await self.menu_loop()
        finally:
            self.running = False
            if self._orchestration_task and not self._orchestration_task.done():
                self._orchestration_task.cancel()
            await self.stop_signal()
            if self.listen_task:
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    pass
            if self.drain_task:
                self.drain_task.cancel()
            if self._esp_writer:
                try:
                    self._esp_writer.close()
                except Exception:
                    pass
            await self.close_send_ws()
            print("[退出] 测试结束")


if __name__ == "__main__":
    tester = Car2Tester()
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
