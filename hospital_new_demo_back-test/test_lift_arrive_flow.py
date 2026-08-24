"""
lift-arrive 全流程测试脚本

模拟车2 ROS 发送 lift-arrive 消息，触发完整电梯控制流程：
  1. 开门（电梯硬件）
  2. lift-across → 车2 ROS
  3. 等待 60 秒（车2进入电梯）
  4. lift-open → 车2 ROS
  5. 关门（电梯硬件）
  6. 去目标楼层（电梯硬件）
  7. 等待 nurse_arrive
  8. nurse-success → 车2 ROS

测试方式：
  1. 启动后端: python app.py
  2. 启动 ESP32 模拟器（可选，用于测试硬件交互）:
     python test_elevator_simulator.py --host 127.0.0.1
  3. 启动本脚本（模拟车2 ROS）:
     python test_lift_arrive_flow.py --prescription R001 --floor 3

  可选参数：
    --prescription  处方编码（默认: TEST001）
    --floor         目标楼层（默认: 3）
    --nurse-delay   护士到达延迟秒数（默认: 10，设置为0立即触发）
    --host          ROS服务端地址（默认: 127.0.0.1）
    --port          ROS服务端端口（默认: 9090）
"""
import asyncio
import json
import argparse
import time
from datetime import datetime
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None
    print("[错误] 请安装 websockets: pip install websockets")
    exit(1)


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str):
    print(f"[{ts()}] [测试] {msg}")


class FakeROSServer:
    """
    模拟 ROS 服务端，接收后端发送的消息，并可以发送消息给后端
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9090):
        self.host = host
        self.port = port
        self._server = None
        self._clients: set = set()
        self._received_messages: list = []  # 记录收到的消息

    async def _handler(self, websocket):
        """处理 WebSocket 连接"""
        self._clients.add(websocket)
        peer = websocket.remote_address
        log(f"✓ 后端已连接: {peer[0]}:{peer[1]}")
        try:
            async for message in websocket:
                log(f"← 收到后端消息: {message}")
                self._received_messages.append(message)
        except websockets.ConnectionClosed:
            log(f"后端已断开: {peer[0]}:{peer[1]}")
        finally:
            self._clients.discard(websocket)

    async def start(self):
        """启动模拟 ROS 服务端"""
        self._server = await websockets.serve(
            self._handler, self.host, self.port
        )
        log(f"模拟 ROS 服务端已启动: ws://{self.host}:{self.port}")

    async def stop(self):
        """停止服务端"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        log("模拟 ROS 服务端已停止")

    async def send_message(self, message: str):
        """向所有连接的客户端发送消息"""
        if not self._clients:
            log("[警告] 没有连接的客户端，无法发送消息")
            return
        for client in self._clients:
            try:
                await client.send(message)
                log(f"→ 发送消息: {message}")
            except Exception as e:
                log(f"[错误] 发送消息失败: {e}")

    def get_received(self) -> list:
        return self._received_messages


async def main():
    parser = argparse.ArgumentParser(description="lift-arrive 全流程测试")
    parser.add_argument("--prescription", default="TEST001", help="处方编码")
    parser.add_argument("--floor", type=int, default=3, help="目标楼层")
    parser.add_argument("--nurse-delay", type=int, default=10, help="护士到达延迟(秒)")
    parser.add_argument("--host", default="127.0.0.1", help="ROS服务端地址")
    parser.add_argument("--port", type=int, default=9090, help="ROS服务端端口")
    args = parser.parse_args()

    prescription_code = args.prescription
    medicine_id = 1  # 模拟药品ID

    print("=" * 60)
    print("  lift-arrive 全流程测试")
    print("=" * 60)
    print(f"  处方编码: {prescription_code}")
    print(f"  目标楼层: {args.floor}")
    print(f"  护士到达延迟: {args.nurse_delay} 秒")
    print(f"  ROS 服务端: ws://{args.host}:{args.port}")
    print("=" * 60)

    # 启动模拟 ROS 服务端
    ros_server = FakeROSServer(args.host, args.port)
    server_task = asyncio.create_task(ros_server.start())

    # 等待服务端启动
    await asyncio.sleep(1)

    # 等待后端连接（可能需要几秒）
    log("等待后端连接...")
    for i in range(15):
        if ros_server._clients:
            log(f"后端已连接，共 {len(ros_server._clients)} 个客户端")
            break
        await asyncio.sleep(1)
    else:
        log("[警告] 后端未连接，尝试继续发送消息...")

    # ===== Step 1: 发送 lift-arrive 消息 =====
    log("=" * 60)
    log("Step 1: 发送 lift-arrive 消息")
    log("=" * 60)

    # 格式: {medicine_id}_{prescription_code}_lift-arrive
    lift_arrive_msg = f"{medicine_id}_{prescription_code}_lift-arrive"
    await ros_server.send_message(lift_arrive_msg)
    log("lift-arrive 已发送，等待后端处理...")

    # 等待后端处理（开门 → lift-across → 60秒等待 → lift-open → 关门 → 去楼层）
    # 前两个命令会很快，但 lift_across_delay 是 60 秒
    log("等待 lift-across 信号 (最多 10 秒)...")
    await asyncio.sleep(10)

    # 检查是否收到 lift-across
    received = ros_server.get_received()
    lift_across_received = any("lift-across" in msg for msg in received)
    if lift_across_received:
        log("✓ 收到 lift-across")
    else:
        log("[警告] 未收到 lift-across")

    # 等待 lift-open 信号（60秒延迟后）
    log("等待 lift-open 信号 (最多 65 秒，含 60 秒延迟)...")
    for i in range(65):
        await asyncio.sleep(1)
        received = ros_server.get_received()
        if any("lift-open" in msg for msg in received):
            log("✓ 收到 lift-open")
            break

    # ===== Step 2: 发送 nurse_arrive 消息 =====
    log("=" * 60)
    log(f"Step 2: 等待 {args.nurse_delay} 秒后发送 nurse_arrive")
    log("=" * 60)

    await asyncio.sleep(args.nurse_delay)

    nurse_arrive_msg = f"{medicine_id}_{prescription_code}_nurse_arrive"
    await ros_server.send_message(nurse_arrive_msg)
    log("nurse_arrive 已发送")

    # 等待 nurse-success
    log("等待 nurse-success 信号 (最多 5 秒)...")
    for i in range(5):
        await asyncio.sleep(1)
        received = ros_server.get_received()
        if any("nurse-success" in msg for msg in received):
            log("✓ 收到 nurse-success")
            break

    # ===== 汇总 =====
    log("=" * 60)
    log("流程完成，汇总收到的消息:")
    log("=" * 60)
    for i, msg in enumerate(ros_server.get_received(), 1):
        log(f"  [{i}] {msg}")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)
    print("\n检查后端控制台，确认电梯日志:")
    print("  [Elevator] SEND #1: open_door")
    print("  [Elevator] SEND #2: close_door")
    print("  [Elevator] SEND #3: status")
    print("  [Elevator] SEND #4: go_floor")
    print("=" * 60)

    # 清理
    await ros_server.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")


# ============================================================
# 快速测试命令（无 ROS 场景，仅测试电梯硬件）
# ============================================================
# 如果只需要测试电梯硬件（不涉及 ROS），直接调用 API:
#
#   curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=open_door"
#   curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=close_door"
#   curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=go_floor&floor=3"
#   curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=status"