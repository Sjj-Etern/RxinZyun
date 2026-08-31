# -*- coding: utf-8 -*-
"""
电梯门禁 IO 改版测试脚本（交互式手动控制版）
=====================================
手动选择要执行的命令，逐项验证新 IO 绑定硬件功能：
  开门(GPIO17) / 关门(GPIO18) / 2楼(GPIO9) / 4楼(GPIO10) / 电源(GPIO19)
不依赖后端服务，直接 TCP 连接 ESP32 发送命令。

前提：
  1. 固件已按新 IO 绑定烧录（relay.c/emission.c/tcp_client.c 改版后 idf.py build flash）
  2. ESP32 已上电并连接 WiFi
     （注意：ESP32 是 TCP 客户端，只连一个服务端；若后端在运行请先停掉，
      本脚本作为 TCP 服务端等 ESP32 重连/重启后自动发现连入）

用法：
  python test_elevator_new_io.py                 # 交互模式（默认），菜单手动选命令
  python test_elevator_new_io.py --auto         # 直接跑全量自动测试（原行为）
  python test_elevator_new_io.py --port 10833    # 指定端口

交互菜单：
  [1] status      查询状态（当前楼层 + 温湿度）
  [2] open_door   开门（继电器3 @ GPIO17）
  [3] close_door  关门（继电器4 @ GPIO18）
  [4] go_floor 2  去2楼（继电器1 @ GPIO9 + 红外移动）
  [5] go_floor 4  去4楼（继电器2 @ GPIO10 + 红外移动）
  [6] go_floor N  自定义楼层（1-5，未接线的楼层仅红外移动）
  [7] power       电源键（继电器5 @ GPIO19，新功能）
  [8] auto        全量自动测试（6项，输出PASS/FAIL汇总）
  [q] 退出
"""
import argparse
import asyncio
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ACK_TIMEOUT = 12.0        # 等ACK超时（秒）
FLOOR_WAIT = 12.0         # 楼层移动后额外等待（秒）


class ElevatorIOTester:
    def __init__(self):
        self.reader = None
        self.writer = None
        self.seq = 0
        self.results = []          # (测试项, 结果, 详情)
        self.pending_ack = None    # asyncio.Future
        self.last_floor_arrived = None

    # ---------- TCP 服务端（让 ESP32 主动连入）----------
    async def start_server(self, host, port):
        server = await asyncio.start_server(self._on_client, host, port)
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
        print(f"[TEST] TCP 服务端已启动: {addrs}")
        print(f"[TEST] 等待 ESP32 连入（请重启 ESP32 或等待其 5 秒重连）...")
        async with server:
            for _ in range(90):
                if self.writer is not None:
                    return True
                await asyncio.sleep(1)
            return False

    async def _on_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"[TEST] ESP32 已连入: {addr}\n")
        self.reader, self.writer = reader, writer
        asyncio.create_task(self._recv_loop())

    # ---------- 接收循环 ----------
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

    # ---------- 发送命令 ----------
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

    # ---------- 记录结果 ----------
    def record(self, name, ok, detail=""):
        self.results.append((name, "PASS" if ok else "FAIL", detail))
        mark = "[PASS]" if ok else "[FAIL]"
        print(f"{mark} {name} {detail}\n")

    # ---------- 手动单命令 ----------
    async def manual_status(self):
        ack = await self.send_cmd("status")
        if ack:
            print(f"    当前楼层={ack.get('floor')}  温度={ack.get('temp')}°C  湿度={ack.get('humi')}%  电源={'开机' if ack.get('power') == 1 else '关机'}\n")

    async def manual_simple(self, cmd, label, post_delay=0.0):
        ack = await self.send_cmd(cmd)
        if ack:
            if post_delay > 0:
                await asyncio.sleep(post_delay)
            print(f"    {label} 完成（ACK ok）\n")

    async def manual_go_floor(self, floor):
        print(f"[TEST] 去{floor}楼：继电器按键（若接线）+ 红外移动，等待约{FLOOR_WAIT}s...")
        self.last_floor_arrived = None
        ack = await self.send_cmd("go_floor", floor=floor)
        if ack is None:
            return
        # 等待移动完成（收到 floor_arrived 或超时）
        for _ in range(int(FLOOR_WAIT)):
            if self.last_floor_arrived is not None:
                break
            await asyncio.sleep(1)
        st = await self.send_cmd("status")
        if st:
            print(f"    结果：当前楼层={st.get('floor')}  到达上报={self.last_floor_arrived}\n")

    # ---------- 全量自动测试（原流程）----------
    async def run_tests(self, skip_power=False):
        print("=" * 60)
        print("电梯门禁 IO 改版自动测试（开门17/关门18/2楼9/4楼10/电源19）")
        print("=" * 60)

        ack = await self.send_cmd("status")
        if ack is None:
            self.record("TCP连通性(status)", False, "未收到ACK，ESP32无响应")
            return
        self.record("TCP连通性(status)", True,
                    f"楼层={ack.get('floor')} 温度={ack.get('temp')}°C 湿度={ack.get('humi')}%")

        ack = await self.send_cmd("open_door")
        self.record("开门 open_door (GPIO17/继电器3)",
                    ack is not None and ack.get("status") == "ok",
                    "" if ack else "ACK超时")

        ack = await self.send_cmd("close_door")
        self.record("关门 close_door (GPIO18/继电器4)",
                    ack is not None and ack.get("status") == "ok",
                    "" if ack else "ACK超时")

        for floor, gpio in ((2, "GPIO9/继电器1"), (4, "GPIO10/继电器2")):
            print(f"[TEST] 去{floor}楼：继电器按键 + 红外移动，等待约{FLOOR_WAIT}s...")
            self.last_floor_arrived = None
            ack = await self.send_cmd("go_floor", floor=floor)
            if ack is not None:
                for _ in range(int(FLOOR_WAIT)):
                    if self.last_floor_arrived is not None:
                        break
                    await asyncio.sleep(1)
                arrived = self.last_floor_arrived
                st = await self.send_cmd("status")
                floor_now = st.get("floor") if st else None
                self.record(f"去{floor}楼 go_floor({floor}) ({gpio})",
                            floor_now == floor,
                            f"当前楼层={floor_now} 到达上报={arrived}")
            else:
                self.record(f"去{floor}楼 go_floor({floor}) ({gpio})", False, "ACK超时")

        if not skip_power:
            # 方案A：电源持续吸合模式，power_off/power_on 两命令配对验证
            # （继电器5串在供电回路：off=断电，on=持续供电；测试结束恢复开机状态）
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
==================== 电梯手动控制 ====================
  [1] status      查询状态（楼层+温湿度+电源）
  [2] open_door   开门   （继电器3 @ GPIO17）
  [3] close_door  关门   （继电器4 @ GPIO18）
  [4] go_floor 2  去2楼 （继电器1 @ GPIO9）
  [5] go_floor 4  去4楼 （继电器2 @ GPIO10）
  [6] go_floor N  自定义楼层（1-5）
  [7] power_on    开机   （继电器5 @ GPIO19 持续吸合供电）
  [8] power_off   关机   （继电器5 @ GPIO19 释放断电）
  [9] auto        全量自动测试（含电源配对验证+汇总）
  [q] 退出
======================================================"""


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
    parser = argparse.ArgumentParser(description="电梯IO改版测试脚本（交互式）")
    parser.add_argument("--host", default="0.0.0.0", help="TCP监听地址（服务端模式）")
    parser.add_argument("--port", type=int, default=10833, help="TCP端口")
    parser.add_argument("--auto", action="store_true", help="跳过菜单，直接跑全量自动测试")
    parser.add_argument("--skip-power", action="store_true", help="(auto模式)跳过电源测试")
    args = parser.parse_args()

    tester = ElevatorIOTester()
    ok = await tester.start_server(args.host, args.port)
    if not ok:
        print("[TEST] 90秒内无 ESP32 连入，退出。请确认：")
        print("  1. ESP32 已烧录改版固件并重启")
        print("  2. 后端 hospital_dashboard_backend 已停止（ESP32 只连一个服务端）")
        print("  3. UDP发现正常（ESP32 会自动发现本机并连入）")
        sys.exit(2)

    try:
        if args.auto:
            await tester.run_tests(skip_power=args.skip_power)
        else:
            await interactive(tester)
    finally:
        if tester.writer:
            tester.writer.close()


if __name__ == "__main__":
    asyncio.run(main())
