"""
车2 ROS 完整通信流程 + 电梯升降联动测试

模拟车2 ROS 服务端，与 hospital 后端完整通信，测试电梯升降功能。

协议（车2_ROS通信文档）:
  ① 系统 → 车2:  {code}_pharmacist-success
  ② 车2 → 系统:  {code}_lift-arrive
  ③ 系统 → 车2:  {code}_lift-across
  ④ 延迟 60 秒
  ⑤ 系统 → 车2:  {code}_lift-open
  ⑥ 车2 → 系统:  {code}_nurse_arrive
  ⑦ 系统 → 车2:  {code}_nurse-success

电梯硬件联动:
  - lift-arrive 后: 开门 → lift-across → 60s → lift-open → 关门 → 去目标楼层
  - 升降测试: 多轮不同楼层验证上行/下行

用法:
  # 完整流程测试（默认: 3轮, 无护士延迟）
  python test_elevator_full_flow.py

  # 自定义参数
  python test_elevator_full_flow.py --rounds 2 --nurse-delay 0 --floors 3,5,1

  # 单轮快速测试（护士立即到达，10秒内完成）
  python test_elevator_full_flow.py --nurse-delay 0 --rounds 1 --quick

  # 交互模式（手动控制每一步）
  python test_elevator_full_flow.py --interactive
"""
import asyncio
import json
import argparse
import sys
import time
from datetime import datetime
from typing import Optional, List

try:
    import websockets
except ImportError:
    print("[错误] 请安装 websockets: pip install websockets")
    sys.exit(1)

try:
    import aiohttp
except ImportError:
    aiohttp = None
    print("[提示] 未安装 aiohttp，将跳过电梯状态查询。安装: pip install aiohttp")


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str, tag: str = "测试"):
    print(f"[{ts()}] [{tag}] {msg}")


# ====================================================================
# 模拟 ROS 服务端
# ====================================================================

class FakeROSServer:
    """模拟车2 ROS WebSocket 服务端"""

    def __init__(self, host: str = "0.0.0.0", port: int = 9090):
        self.host = host
        self.port = port
        self._server = None
        self._clients: dict = {}  # websocket → peer_str
        self._received: list = []  # 所有收到的消息
        self._latest_msg: Optional[str] = None

    async def _handler(self, websocket):
        peer = websocket.remote_address
        peer_str = f"{peer[0]}:{peer[1]}"
        self._clients[websocket] = peer_str
        log(f"✓ 后端已连接: {peer_str}", "ROS")

        try:
            async for message in websocket:
                self._received.append(message)
                self._latest_msg = message
                log(f"← 收到: {message}", "ROS")
        except websockets.ConnectionClosed:
            log(f"后端已断开: {peer_str}", "ROS")
        finally:
            self._clients.pop(websocket, None)

    async def start(self):
        self._server = await websockets.serve(self._handler, self.host, self.port)
        log(f"模拟 ROS 启动: ws://{self.host}:{self.port}", "ROS")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        log("模拟 ROS 已停止", "ROS")

    async def send(self, message: str):
        """向所有客户端发送消息"""
        if not self._clients:
            log("[警告] 无客户端连接", "ROS")
            return False
        for ws in list(self._clients.keys()):
            try:
                await ws.send(message)
            except Exception:
                pass
        log(f"→ 发送: {message}", "ROS")
        return True

    def clear_received(self):
        self._received.clear()
        self._latest_msg = None

    def wait_for(self, keyword: str, timeout: float = 5.0) -> Optional[str]:
        """检查已收到的消息中是否包含关键词"""
        for msg in self._received:
            if keyword in msg:
                return msg
        return None

    async def wait_for_async(self, keyword: str, timeout: float = 10.0) -> Optional[str]:
        """异步等待包含关键词的消息"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.wait_for(keyword)
            if msg:
                return msg
            await asyncio.sleep(0.3)
        return None


# ====================================================================
# 电梯状态查询
# ====================================================================

class ElevatorMonitor:
    """通过 HTTP API 查询电梯状态"""

    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None and aiohttp is not None:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def get_state(self) -> dict:
        """查询电梯控制器状态"""
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/v1/elevator/state") as resp:
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def send_command(self, cmd: str, floor: int = 3) -> dict:
        """发送电梯命令"""
        await self._ensure_session()
        url = f"{self.base_url}/api/v1/elevator/command?cmd={cmd}"
        if cmd == "go_floor":
            url += f"&floor={floor}"
        try:
            async with self._session.post(url) as resp:
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_floor(self) -> int:
        """获取当前楼层"""
        result = await self.send_command("status")
        if result.get("status") == "success":
            return result.get("ack", {}).get("floor", 0)
        return 0

    async def get_temp_humi(self) -> tuple:
        """获取温湿度"""
        result = await self.send_command("status")
        if result.get("status") == "success":
            ack = result.get("ack", {})
            return ack.get("temp", 0), ack.get("humi", 0)
        return 0, 0


# ====================================================================
# 主测试流程
# ====================================================================

class ElevatorFlowTester:
    """完整流程测试器"""

    def __init__(self, args):
        self.args = args
        self.ros = FakeROSServer(host="0.0.0.0", port=args.ros_port)
        self.elevator = ElevatorMonitor(base_url=f"http://127.0.0.1:{args.backend_port}")
        self.round_results: List[dict] = []

    def banner(self, text: str):
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}")

    async def check_prerequisites(self) -> bool:
        """检查前置条件"""
        self.banner("前置条件检查")

        # 1. 检查后端是否可达
        state = await self.elevator.get_state()
        if "error" in state:
            log(f"✗ 后端不可达: {state['error']}", "检查")
            log("请先启动后端: python app.py", "检查")
            return False
        log(f"✓ 后端可达: {state}", "检查")

        # 2. 检查 ESP32 是否连接
        if not state.get("connected"):
            log("✗ ESP32 电梯控制器未连接", "检查")
            log("请确保 ESP32 已上电并连接到同一 WiFi", "检查")
            return False
        log(f"✓ ESP32 已连接: {state.get('client_addr')}", "检查")

        # 3. 查询电梯当前状态
        floor = await self.elevator.get_floor()
        temp, humi = await self.elevator.get_temp_humi()
        log(f"✓ 电梯状态: 楼层={floor}, 温度={temp}°C, 湿度={humi}%", "检查")

        return True

    async def run_single_round(self, round_num: int, prescription_code: str, target_floor: int) -> dict:
        """执行单轮完整流程"""
        result = {
            "round": round_num,
            "prescription": prescription_code,
            "target_floor": target_floor,
            "steps": {},
        }

        self.banner(f"第 {round_num} 轮: {prescription_code} → 目标楼层 {target_floor}")

        medicine_id = 1
        self.ros.clear_received()

        # ---- Step ①: pharmacist-success ----
        log("Step ①: 发送 pharmacist-success", "流程")
        msg = f"{medicine_id}_{prescription_code}_pharmacist-success"
        await self.ros.send(msg)
        await asyncio.sleep(1)
        result["steps"]["pharmacist-success"] = "sent"

        # ---- Step ②: lift-arrive ----
        log("Step ②: 发送 lift-arrive", "流程")
        msg = f"{medicine_id}_{prescription_code}_lift-arrive"
        await self.ros.send(msg)
        result["steps"]["lift-arrive"] = "sent"

        # 等待电梯开门
        log("等待电梯开门...", "流程")
        await asyncio.sleep(3)
        result["steps"]["open_door"] = "done"

        # ---- Step ③: 等待 lift-across ----
        log("Step ③: 等待 lift-across", "流程")
        msg = await self.ros.wait_for_async("lift-across", timeout=10)
        if msg:
            log(f"  ✓ 收到: {msg}", "流程")
            result["steps"]["lift-across"] = "received"
        else:
            log("  ✗ 未收到 lift-across", "流程")
            result["steps"]["lift-across"] = "timeout"

        # ---- Step ④: 等待 60 秒延迟（使用 quick 模式跳过）----
        if self.args.quick:
            log("Step ④: [快速模式] 跳过 60 秒等待", "流程")
            result["steps"]["delay"] = "skipped"
        else:
            log(f"Step ④: 等待 {self.args.lift_delay} 秒...", "流程")
            for remaining in range(self.args.lift_delay, 0, -5):
                await asyncio.sleep(5)
                if remaining % 15 == 0 or remaining <= 10:
                    log(f"  剩余 {remaining} 秒...", "流程")
            result["steps"]["delay"] = "done"

        # ---- Step ⑤: 等待 lift-open ----
        log("Step ⑤: 等待 lift-open", "流程")
        msg = await self.ros.wait_for_async("lift-open", timeout=10)
        if msg:
            log(f"  ✓ 收到: {msg}", "流程")
            result["steps"]["lift-open"] = "received"
        else:
            log("  ✗ 未收到 lift-open", "流程")
            result["steps"]["lift-open"] = "timeout"

        # 等待关门 + 去楼层
        log("等待关门 + 去目标楼层...", "流程")
        await asyncio.sleep(self.args.door_delay * 2 + 5)
        result["steps"]["close_door"] = "done"
        result["steps"]["go_floor"] = "done"

        # ---- Step ⑥: nurse_arrive ----
        if self.args.interactive:
            input(f"\n按 Enter 发送 nurse_arrive (模拟护士到达)...")
        elif self.args.nurse_delay > 0:
            log(f"Step ⑥: 等待 {self.args.nurse_delay} 秒后发送 nurse_arrive", "流程")
            await asyncio.sleep(self.args.nurse_delay)

        log("Step ⑥: 发送 nurse_arrive", "流程")
        msg = f"{medicine_id}_{prescription_code}_nurse_arrive"
        await self.ros.send(msg)
        result["steps"]["nurse_arrive"] = "sent"

        # ---- Step ⑦: 等待 nurse-success ----
        log("Step ⑦: 等待 nurse-success", "流程")
        msg = await self.ros.wait_for_async("nurse-success", timeout=10)
        if msg:
            log(f"  ✓ 收到: {msg}", "流程")
            result["steps"]["nurse-success"] = "received"
        else:
            log("  ✗ 未收到 nurse-success", "流程")
            result["steps"]["nurse-success"] = "timeout"

        # ---- 验证电梯状态 ----
        log("验证电梯状态...", "流程")
        await asyncio.sleep(2)
        floor = await self.elevator.get_floor()
        temp, humi = await self.elevator.get_temp_humi()
        log(f"电梯状态: 楼层={floor}, 温度={temp}°C, 湿度={humi}%", "流程")
        result["final_floor"] = floor
        result["temp"] = temp
        result["humi"] = humi

        return result

    async def run_lift_test(self) -> dict:
        """升降功能专项测试"""
        self.banner("升降功能专项测试")

        floors_to_test = [int(f) for f in self.args.floors.split(",")]
        results = []

        for i, floor in enumerate(floors_to_test, 1):
            log(f"--- 升降测试 {i}/{len(floors_to_test)}: 目标楼层 = {floor} ---", "升降")

            # 查询当前楼层
            current = await self.elevator.get_floor()
            if current == floor:
                log(f"已在 {floor} 楼，跳过", "升降")
                continue

            direction = "上行" if floor > current else "下行"
            log(f"当前楼层={current}, 目标={floor}, 方向={direction}", "升降")

            result = await self.elevator.send_command("go_floor", floor)
            if result.get("status") == "success":
                log(f"✓ {direction}命令已发送: {result.get('ack')}", "升降")
            else:
                log(f"✗ {direction}命令失败: {result}", "升降")

            # 等待移动完成
            floor_diff = abs(floor - current)
            wait_time = self.args.go_floor_delay * floor_diff
            log(f"等待移动完成 ({wait_time} 秒)...", "升降")
            await asyncio.sleep(wait_time)

            # 验证
            new_floor = await self.elevator.get_floor()
            temp, humi = await self.elevator.get_temp_humi()
            status = "✓" if new_floor == floor else "✗"
            log(f"{status} 楼层验证: 期望={floor}, 实际={new_floor}, 温度={temp}°C, 湿度={humi}%", "升降")

            results.append({
                "from": current,
                "to": floor,
                "direction": direction,
                "actual": new_floor,
                "match": new_floor == floor,
                "temp": temp,
                "humi": humi,
            })

        return results

    async def run(self):
        """主入口"""
        self.banner("车2 ROS 完整流程 + 电梯升降联动测试")
        print(f"  ROS 端口: {self.args.ros_port}")
        print(f"  后端端口: {self.args.backend_port}")
        print(f"  测试轮数: {self.args.rounds}")
        print(f"  目标楼层: {self.args.floors}")
        print(f"  护士延迟: {self.args.nurse_delay} 秒")
        print(f"  快速模式: {'是' if self.args.quick else '否'}")
        print(f"  交互模式: {'是' if self.args.interactive else '否'}")
        print(f"  60秒延迟: {self.args.lift_delay} 秒")

        # 启动 ROS 服务端
        await self.ros.start()
        await asyncio.sleep(1)

        # 等待后端连接
        log("等待后端连接 ROS 服务端...", "启动")
        for i in range(20):
            if self.ros._clients:
                break
            await asyncio.sleep(1)
        else:
            log("[警告] 后端未连接 ROS，可能无法接收消息", "启动")

        # 检查前置条件
        ok = await self.check_prerequisites()
        if not ok:
            log("前置条件不满足，退出", "启动")
            await self.ros.stop()
            await self.elevator.close()
            return

        # ===== 升降功能专项测试 =====
        if self.args.test_lift:
            lift_results = await self.run_lift_test()
            self.banner("升降测试结果")
            passed = sum(1 for r in lift_results if r["match"])
            total = len(lift_results)
            for r in lift_results:
                status = "✓" if r["match"] else "✗"
                print(f"  {status} {r['direction']}: {r['from']}→{r['to']} (实际={r['actual']})")
            print(f"\n  通过: {passed}/{total}")

        # ===== 完整流程测试 =====
        if self.args.test_flow:
            floor_list = [int(f) for f in self.args.floors.split(",")]
            for i in range(self.args.rounds):
                code = f"TEST{self.args.round_id:03d}"

                # 如果流程测试时也测试升降，每轮用不同楼层
                if self.args.test_lift:
                    floor = floor_list[i % len(floor_list)]
                else:
                    floor = floor_list[0]

                result = await self.run_single_round(i + 1, code, floor)
                self.round_results.append(result)

                if i < self.args.rounds - 1:
                    await asyncio.sleep(3)

            # 汇总
            self.banner("流程测试汇总")
            for r in self.round_results:
                steps = r["steps"]
                all_ok = all(
                    steps.get(k) in ("received", "sent", "done")
                    for k in ["lift-across", "lift-open", "nurse-success"]
                )
                status = "✓" if all_ok else "✗"
                print(f"  {status} 第{r['round']}轮: {r['prescription']} "
                      f"楼层={r['final_floor']}/{r['target_floor']} "
                      f"温度={r['temp']}°C 湿度={r['humi']}%")

        # 清理
        await self.ros.stop()
        await self.elevator.close()
        self.banner("测试完成")


# ====================================================================
# 命令行入口
# ====================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="车2 ROS 完整流程 + 电梯升降联动测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整流程 + 升降测试（默认）
  python test_elevator_full_flow.py

  # 快速模式（跳过 60 秒延迟，护士立即到达）
  python test_elevator_full_flow.py --quick --nurse-delay 0

  # 仅测试升降功能
  python test_elevator_full_flow.py --test-lift --no-flow

  # 仅测试完整流程
  python test_elevator_full_flow.py --test-flow --no-lift

  # 交互模式（手动控制每一步）
  python test_elevator_full_flow.py --interactive

  # 自定义楼层序列
  python test_elevator_full_flow.py --floors 1,3,5,3,1
        """,
    )
    parser.add_argument("--ros-port", type=int, default=9090, help="模拟 ROS 服务端端口")
    parser.add_argument("--backend-port", type=int, default=8080, help="后端端口")
    parser.add_argument("--rounds", type=int, default=3, help="流程测试轮数")
    parser.add_argument("--floors", default="3,5,1", help="目标楼层列表（逗号分隔）")
    parser.add_argument("--nurse-delay", type=int, default=10, help="护士到达延迟秒数")
    parser.add_argument("--lift-delay", type=int, default=60, help="lift-across 到 lift-open 的延迟秒数")
    parser.add_argument("--door-delay", type=float, default=3.0, help="开门/关门后等待秒数")
    parser.add_argument("--go-floor-delay", type=float, default=5.0, help="每层移动等待秒数")
    parser.add_argument("--round-id", type=int, default=1, help="轮次起始 ID")
    parser.add_argument("--quick", action="store_true", help="快速模式（跳过 60 秒延迟）")
    parser.add_argument("--interactive", action="store_true", help="交互模式（手动控制每一步）")
    parser.add_argument("--test-lift", action="store_true", default=True, help="测试升降功能（默认开启）")
    parser.add_argument("--test-flow", action="store_true", default=True, help="测试完整流程（默认开启）")
    parser.add_argument("--no-lift", action="store_true", help="禁用升降测试")
    parser.add_argument("--no-flow", action="store_true", help="禁用流程测试")
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.no_lift:
        args.test_lift = False
    if args.no_flow:
        args.test_flow = False

    if not args.test_lift and not args.test_flow:
        print("[错误] 至少需要启用一个测试: --test-lift 或 --test-flow")
        sys.exit(1)

    tester = ElevatorFlowTester(args)
    try:
        await tester.run()
    except KeyboardInterrupt:
        print("\n用户中断")
        await tester.ros.stop()
        await tester.elevator.close()


if __name__ == "__main__":
    asyncio.run(main())