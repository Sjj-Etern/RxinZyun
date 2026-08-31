# -*- coding: utf-8 -*-
"""
电梯功能模拟测试脚本（无需连接 ESP32 / 电梯硬件）
=====================================
用内置的 Mock ESP32 模拟器替代真实设备，验证电梯命令收发、ACK 回执、
floor_arrived 上报与 8+1 步编排时序逻辑。适用于：

  1. 后端电梯编排（elevator_control.py）的联调自测（无硬件冒烟）
  2. 演示/教学场景（模拟电梯开门、关门、楼层移动全过程）
  3. 开发环境日常回归（不占用真实电梯）

原理：本脚本在本地同时扮演两个角色：
  - TCP 服务端（对等于真实后端 elevator_control 的服务端）
  - Mock ESP32 客户端（连入服务端，按协议应答 ACK / floor_arrived）

与真实固件行为对齐（elevator_access_control tcp_client.c / emission.c）：
  - ACK 格式: {"type":"ack","cmd":...,"seq":N,"status":"ok","floor":F,"temp":..,"humi":..,"power":P}
  - go_floor: 先回 ACK，异步执行移动，完成后上报 {"type":"floor_arrived","floor":F}
  - power_on/power_off: 持续吸合/释放（方案A），ACK 带 power 状态
  - 楼层移动耗时: 模拟每层约 2 秒（真实为红外 4.6~5s/层，可用 --floor-sec 调）

用法：
  python test_elevator_sim.py                 # 交互模式（默认），菜单手动选命令
  python test_elevator_sim.py --auto         # 全量自动测试（输出PASS/FAIL汇总）
  python test_elevator_sim.py --port 20833    # 指定端口
  python test_elevator_sim.py --floor-sec 4.5 # 模拟每层移动耗时4.5秒

交互菜单：
  [1] status      查询状态（当前楼层 + 温湿度 + 电源）
  [2] open_door   开门（模拟继电器3 @ GPIO17 吸合50ms）
  [3] close_door  关门（模拟继电器4 @ GPIO18 吸合50ms）
  [4] go_floor 2  去2楼（模拟继电器1 @ GPIO9 + 红外移动）
  [5] go_floor 4  去4楼（模拟继电器2 @ GPIO10 + 红外移动）
  [6] go_floor N  自定义楼层（1-5）
  [7] power_on    开机（模拟继电器5 @ GPIO19 持续吸合供电）
  [8] power_off   关机（模拟继电器5 @ GPIO19 释放断电）
  [9] auto        全量自动测试（含电源配对验证 + floor_arrived 验证 + 汇总）
  [q] 退出
"""
import argparse
import asyncio
import json
import random
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ACK_TIMEOUT = 5.0          # 等ACK超时（秒）——模拟器响应快，无需像真机12s
FLOOR_SEC_PER_LEVEL = 2.0  # 模拟每层移动耗时（秒）


class MockESP32:
    """
    Mock ESP32 电梯控制器：作为 TCP 客户端连入测试服务端，模拟真实固件行为。
    状态：当前楼层 Floor_Num（初始1，对齐 emission.c:40）、电源（初始开机，POWER_BOOT_DEFAULT=1）
    """

    def __init__(self, host, port, floor_sec):
        self.host, self.port = host, port
        self.floor_sec = floor_sec
        self.floor_num = 1       # 初始楼层（与固件 Floor_Num=1 一致）
        self.power_on = True     # 上电默认开机（方案A 持续吸合）
        self.temp = round(random.uniform(24.0, 28.0), 1)   # 模拟温湿度
        self.humi = round(random.uniform(40.0, 60.0), 1)
        self.relay_events = []   # 继电器动作记录（用于验证时序）

    async def connect(self):
        """连入测试服务端"""
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        print(f"[SIM] Mock ESP32 已连入服务端 {self.host}:{self.port}")
        print(f"[SIM] 初始状态: 楼层={self.floor_num} 电源={'开机' if self.power_on else '关机'} "
              f"温度={self.temp}°C 湿度={self.humi}%")
        await self._loop()

    def _ack(self, cmd, seq):
        """构造 ACK（对齐 tcp_client.c 应答格式）"""
        return {
            "type": "ack", "cmd": cmd, "seq": seq, "status": "ok",
            "floor": self.floor_num, "temp": self.temp, "humi": self.humi,
            "power": 1 if self.power_on else 0,
        }

    async def _send(self, obj):
        self.writer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.writer.drain()

    async def _press_button(self, relay_name, gpio, ms=50):
        """模拟继电器按键（50ms 短按，对齐 emission.c BUTTON_PRESS_MS）"""
        self.relay_events.append((relay_name, gpio, ms))
        print(f"[SIM]   继电器动作: {relay_name}(@GPIO{gpio}) 吸合{ms}ms")

    async def _move_to(self, target):
        """模拟楼层移动（红外 Lift2UpDown），完成后上报 floor_arrived（对齐固件行为）"""
        diff = abs(target - self.floor_num)
        if diff == 0:
            print(f"[SIM]   已在 {target} 楼，无需移动，直接上报到达")
        else:
            cost = diff * self.floor_sec
            print(f"[SIM]   红外移动: {self.floor_num}楼 → {target}楼（{diff}层，模拟{cost:.1f}s）...")
            await asyncio.sleep(cost)
        self.floor_num = target
        await self._send({"type": "floor_arrived", "floor": target})
        print(f"[SIM]   已上报 floor_arrived: {target} 楼")

    async def _loop(self):
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8", errors="ignore").strip())
                except Exception:
                    continue
                cmd = msg.get("cmd")
                seq = msg.get("seq", 0)
                print(f"[SIM] ← 收到命令: {msg}")

                if cmd == "status":
                    await self._send(self._ack(cmd, seq))

                elif cmd == "open_door":
                    await self._press_button("继电器3(开门)", 17)
                    await self._send(self._ack(cmd, seq))

                elif cmd == "close_door":
                    await self._press_button("继电器4(关门)", 18)
                    await self._send(self._ack(cmd, seq))

                elif cmd == "go_floor":
                    floor = int(msg.get("floor", 0))
                    # 先回 ACK（对齐固件：go_floor 先应答再异步移动）
                    await self._send(self._ack(cmd, seq))
                    if 1 <= floor <= 5:
                        if floor == 2:
                            await self._press_button("继电器1(2楼)", 9)
                        elif floor == 4:
                            await self._press_button("继电器2(4楼)", 10)
                        # 3/5楼未接线：仅红外移动（对齐 emission.c toFloor）
                        asyncio.create_task(self._move_to(floor))

                elif cmd in ("power_on", "power_off"):
                    # 方案A：持续吸合/释放（对齐 emission.c power_on/power_off）
                    self.power_on = (cmd == "power_on")
                    state = "持续吸合供电" if self.power_on else "释放断电"
                    print(f"[SIM]   继电器5(@GPIO19) 电源: {state}")
                    self.relay_events.append(("继电器5(电源)", 19, "HOLD" if self.power_on else "OFF"))
                    await self._send(self._ack(cmd, seq))

                elif cmd == "power":
                    # 兼容旧切换命令
                    self.power_on = not self.power_on
                    await self._send(self._ack(cmd, seq))

                else:
                    await self._send({"type": "ack", "cmd": cmd, "seq": seq,
                                      "status": "error", "msg": "未知命令"})
        except Exception as e:
            print(f"[SIM] 模拟器结束: {e}")


class ElevatorSimTester:
    """测试主控：TCP 服务端 + 测试用例（结构对齐 test_elevator_new_io.py）"""

    def __init__(self):
        self.reader = None
        self.writer = None
        self.seq = 0
        self.results = []          # (测试项, 结果, 详情)
        self.pending_ack = None    # asyncio.Future
        self.last_floor_arrived = None

    async def start_server(self, host, port):
        server = await asyncio.start_server(self._on_client, host, port)
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
        print(f"[TEST] TCP 服务端已启动: {addrs}")
        print(f"[TEST] 启动内置 Mock ESP32（无需真实硬件）...")
        async with server:
            # 等 Mock ESP32 连入（本地回环，几乎立即）
            for _ in range(15):
                if self.writer is not None:
                    return True
                await asyncio.sleep(0.2)
            return False

    async def _on_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"[TEST] Mock ESP32 已连入: {addr}\n")
        self.reader, self.writer = reader, writer
        asyncio.create_task(self._recv_loop())

    async def _recv_loop(self):
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8", errors="ignore").strip())
                except Exception:
                    print(f"[TEST] 非JSON: {line!r}")
                    continue
                mtype = msg.get("type")
                if mtype == "ack":
                    print(f"[TEST] ← ACK: {msg}")
                    if self.pending_ack and not self.pending_ack.done():
                        self.pending_ack.set_result(msg)
                elif mtype == "floor_arrived":
                    floor = msg.get("floor")
                    print(f"[TEST] ← 楼层到达上报: {floor} 楼")
                    self.last_floor_arrived = floor
                else:
                    print(f"[TEST] ← 其他消息: {msg}")
        except Exception as e:
            print(f"[TEST] 接收循环结束: {e}")

    async def send_cmd(self, cmd, **extra):
        self.seq += 1
        payload = {"cmd": cmd, "seq": self.seq}
        payload.update(extra)
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        print(f"[TEST] → 发送: {payload}")
        self.pending_ack = asyncio.get_event_loop().create_future()
        self.writer.write(data.encode("utf-8"))
        await self.writer.drain()
        try:
            return await asyncio.wait_for(self.pending_ack, timeout=ACK_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"[TEST] !! ACK 超时（{ACK_TIMEOUT}s）")
            return None

    def record(self, name, ok, detail=""):
        self.results.append((name, "PASS" if ok else "FAIL", detail))
        mark = "[PASS]" if ok else "[FAIL]"
        print(f"{mark} {name} {detail}\n")

    # ---------- 手动单命令 ----------
    async def manual_status(self):
        ack = await self.send_cmd("status")
        if ack:
            print(f"    当前楼层={ack.get('floor')}  温度={ack.get('temp')}°C  "
                  f"湿度={ack.get('humi')}%  电源={'开机' if ack.get('power') == 1 else '关机'}\n")

    async def manual_simple(self, cmd, label, post_delay=0.0):
        ack = await self.send_cmd(cmd)
        if ack:
            if post_delay > 0:
                await asyncio.sleep(post_delay)
            print(f"    {label} 完成（ACK ok）\n")

    async def manual_go_floor(self, floor):
        print(f"[TEST] 去{floor}楼：模拟继电器按键 + 红外移动，等待 floor_arrived...")
        self.last_floor_arrived = None
        ack = await self.send_cmd("go_floor", floor=floor)
        if ack is None:
            return
        for _ in range(30):
            if self.last_floor_arrived is not None:
                break
            await asyncio.sleep(1)
        st = await self.send_cmd("status")
        if st:
            print(f"    结果：当前楼层={st.get('floor')}  到达上报={self.last_floor_arrived}\n")

    # ---------- 全量自动测试 ----------
    async def run_tests(self, skip_power=False):
        print("=" * 60)
        print("电梯功能模拟测试（Mock ESP32，无需真实硬件）")
        print("=" * 60)

        # 1. 连通性
        ack = await self.send_cmd("status")
        if ack is None:
            self.record("TCP连通性(status)", False, "未收到ACK，模拟器无响应")
            return
        self.record("TCP连通性(status)", True,
                    f"楼层={ack.get('floor')} 温度={ack.get('temp')}°C 湿度={ack.get('humi')}% "
                    f"电源={'开' if ack.get('power') == 1 else '关'}")

        # 2. 开门 / 关门
        ack = await self.send_cmd("open_door")
        self.record("开门 open_door (GPIO17/继电器3)",
                    ack is not None and ack.get("status") == "ok",
                    "" if ack else "ACK超时")

        ack = await self.send_cmd("close_door")
        self.record("关门 close_door (GPIO18/继电器4)",
                    ack is not None and ack.get("status") == "ok",
                    "" if ack else "ACK超时")

        # 3. 楼层移动（含 floor_arrived 真实到达上报验证）
        for floor, gpio in ((2, "GPIO9/继电器1"), (4, "GPIO10/继电器2")):
            print(f"[TEST] 去{floor}楼：模拟按键 + 红外移动...")
            self.last_floor_arrived = None
            ack = await self.send_cmd("go_floor", floor=floor)
            if ack is not None:
                for _ in range(30):
                    if self.last_floor_arrived is not None:
                        break
                    await asyncio.sleep(1)
                arrived = self.last_floor_arrived
                st = await self.send_cmd("status")
                floor_now = st.get("floor") if st else None
                self.record(f"去{floor}楼 go_floor({floor}) ({gpio})",
                            floor_now == floor and arrived == floor,
                            f"当前楼层={floor_now} 到达上报={arrived}")
            else:
                self.record(f"去{floor}楼 go_floor({floor}) ({gpio})", False, "ACK超时")

        # 4. 电源配对（方案A）
        if not skip_power:
            ack = await self.send_cmd("power_off")
            st = await self.send_cmd("status") if ack else None
            self.record("关机 power_off (GPIO19/继电器5)",
                        ack is not None and ack.get("status") == "ok"
                        and st is not None and st.get("power") == 0,
                        f"ACK={'ok' if ack else '超时'} status确认power={st.get('power') if st else 'N/A'}")

            ack = await self.send_cmd("power_on")
            st = await self.send_cmd("status") if ack else None
            self.record("开机 power_on (GPIO19/继电器5)",
                        ack is not None and ack.get("status") == "ok"
                        and st is not None and st.get("power") == 1,
                        f"ACK={'ok' if ack else '超时'} status确认power={st.get('power') if st else 'N/A'}")

        # 5. 回到初始层（保持模拟器状态干净，便于重复测试）
        if self.last_floor_arrived != 1:
            print("[TEST] 收尾：回到 1 楼（初始状态）")
            await self.send_cmd("go_floor", floor=1)
            for _ in range(30):
                if self.last_floor_arrived == 1:
                    break
                await asyncio.sleep(1)

        print("=" * 60)
        print("测试汇总")
        print("=" * 60)
        for name, r, detail in self.results:
            print(f"  {r:4s} | {name} {detail}")
        passed = sum(1 for _, r, _ in self.results if r == "PASS")
        print(f"\n通过 {passed}/{len(self.results)} 项")
        if any(r == "FAIL" for _, r, _ in self.results):
            sys.exit(1)


MENU = """
==================== 电梯模拟控制（无硬件） ====================
  [1] status      查询状态（楼层+温湿度+电源）
  [2] open_door   开门   （模拟继电器3 @ GPIO17）
  [3] close_door  关门   （模拟继电器4 @ GPIO18）
  [4] go_floor 2  去2楼 （模拟继电器1 @ GPIO9 + 红外移动）
  [5] go_floor 4  去4楼 （模拟继电器2 @ GPIO10 + 红外移动）
  [6] go_floor N  自定义楼层（1-5）
  [7] power_on    开机   （模拟继电器5 @ GPIO19 持续吸合供电）
  [8] power_off   关机   （模拟继电器5 @ GPIO19 释放断电）
  [9] auto        全量自动测试（含电源配对 + floor_arrived 验证 + 汇总）
  [q] 退出
================================================================"""


async def interactive(tester):
    """交互菜单：手动选择要执行的操作"""
    loop = asyncio.get_event_loop()
    while True:
        print(MENU)
        choice = (await loop.run_in_executor(None, input, "请选择操作 > ")).strip().lower()
        print()
        if choice in ("q", "quit", "exit", "0"):
            print("[TEST] 退出")
            return
        elif choice == "1":
            await tester.manual_status()
        elif choice == "2":
            await tester.manual_simple("open_door", "开门")
        elif choice == "3":
            await tester.manual_simple("close_door", "关门")
        elif choice == "4":
            await tester.manual_go_floor(2)
        elif choice == "5":
            await tester.manual_go_floor(4)
        elif choice == "6":
            f = (await loop.run_in_executor(None, input, "目标楼层(1-5) > ")).strip()
            if f.isdigit() and 1 <= int(f) <= 5:
                await tester.manual_go_floor(int(f))
            else:
                print("    无效楼层，请输入 1-5\n")
        elif choice == "7":
            await tester.manual_simple("power_on", "开机（持续供电）")
        elif choice == "8":
            await tester.manual_simple("power_off", "关机（断电）")
        elif choice == "9":
            await tester.run_tests()
        else:
            print("    无效选项，请重新选择\n")


async def main():
    parser = argparse.ArgumentParser(description="电梯功能模拟测试脚本（无需连接 ESP32/电梯硬件）")
    parser.add_argument("--host", default="127.0.0.1", help="TCP监听地址（本机回环）")
    parser.add_argument("--port", type=int, default=20833, help="TCP端口（默认20833，避免与真机脚本10833冲突）")
    parser.add_argument("--auto", action="store_true", help="跳过菜单，直接跑全量自动测试")
    parser.add_argument("--skip-power", action="store_true", help="(auto模式)跳过电源测试")
    parser.add_argument("--floor-sec", type=float, default=FLOOR_SEC_PER_LEVEL,
                        help=f"模拟每层移动耗时秒数（默认{FLOOR_SEC_PER_LEVEL}）")
    args = parser.parse_args()

    tester = ElevatorSimTester()
    server = await asyncio.start_server(tester._on_client, args.host, args.port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"[TEST] TCP 服务端已启动: {addrs}")
    print(f"[TEST] 启动内置 Mock ESP32（无需真实硬件，每层移动模拟 {args.floor_sec}s）...")

    # 启动 Mock ESP32 客户端
    mock = MockESP32(args.host, args.port, args.floor_sec)
    mock_task = asyncio.create_task(mock.connect())

    # 等连入
    for _ in range(50):
        if tester.writer is not None:
            break
        await asyncio.sleep(0.2)
    if tester.writer is None:
        print("[TEST] Mock ESP32 连入失败（异常）")
        sys.exit(2)
    print()

    try:
        if args.auto:
            await tester.run_tests(skip_power=args.skip_power)
        else:
            await interactive(tester)
    finally:
        if tester.writer:
            tester.writer.close()
        mock_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
