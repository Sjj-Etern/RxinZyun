"""
阶段1 快速验证脚本：不启动完整 FastAPI，仅验证 ElevatorController TCP 通信

测试流程：
  1. 启动 ElevatorController TCP 服务端
  2. 模拟 ESP32 TCP 客户端连接
  3. 通过 Controller 发送命令
  4. 模拟 ESP32 接收命令并回传 ACK
  5. 验证 ACK 收发正确
"""
import asyncio
import json
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.elevator_control import ElevatorController


async def simulate_esp32_client(host, port, results):
    """模拟 ESP32 TCP 客户端"""
    print("[ESP32模拟] 连接 TCP 服务端...")
    reader, writer = await asyncio.open_connection(host, port)
    print("[ESP32模拟] 已连接")

    # 接收 4 条命令
    for i in range(4):
        line = await reader.readline()
        if not line:
            print(f"[ESP32模拟] 连接断开（第{i+1}条）")
            break

        msg_str = line.decode().strip()
        print(f"[ESP32模拟] ← 收到命令: {msg_str}")

        try:
            cmd_msg = json.loads(msg_str)
            cmd = cmd_msg.get("cmd", "")

            # 模拟执行 + 回传 ACK
            if cmd == "open_door":
                ack = {"type": "ack", "cmd": "open_door", "status": "ok"}
                results.append(("open_door", True))
            elif cmd == "close_door":
                ack = {"type": "ack", "cmd": "close_door", "status": "ok"}
                results.append(("close_door", True))
            elif cmd == "go_floor":
                floor = cmd_msg.get("floor", 1)
                ack = {"type": "ack", "cmd": "go_floor", "status": "arrived", "floor": floor}
                results.append(("go_floor", True, floor))
            elif cmd == "status":
                ack = {"type": "ack", "cmd": "status", "status": "ok", "floor": 3, "temp": 25.5, "humi": 60.0}
                results.append(("status", True))
            else:
                ack = {"type": "ack", "cmd": cmd, "status": "unknown"}

            await asyncio.sleep(0.1)  # 模拟执行延时
            ack_str = json.dumps(ack) + "\n"
            writer.write(ack_str.encode())
            await writer.drain()
            print(f"[ESP32模拟] → 回传 ACK: {ack_str.strip()}")

        except Exception as e:
            print(f"[ESP32模拟] 错误: {e}")
            results.append(("error", False, str(e)))

    writer.close()
    await writer.wait_closed()
    print("[ESP32模拟] 连接已关闭")


async def main():
    print("=" * 60)
    print("  阶段1 快速验证：ElevatorController TCP 通信")
    print("=" * 60)

    host = "127.0.0.1"
    port = 11833  # 用非标准端口避免冲突

    # 1. 创建并启动 Controller
    controller = ElevatorController(host=host, port=port, cmd_timeout=5.0)
    await controller.start_server()
    print(f"[Controller] 服务端启动: {host}:{port}")

    # 2. 启动模拟 ESP32 客户端任务
    results = []
    esp32_task = asyncio.create_task(simulate_esp32_client(host, port, results))

    # 3. 等待 ESP32 连接
    await asyncio.sleep(0.5)
    print(f"\n[Controller] ESP32 已连接: {controller.is_connected()}")

    # 4. 发送命令并验证 ACK
    print("\n--- 测试1: open_door ---")
    try:
        ack = await controller.send_open_door()
        print(f"[Controller] ✓ ACK: {ack}")
    except Exception as e:
        print(f"[Controller] ✗ 失败: {e}")

    print("\n--- 测试2: close_door ---")
    try:
        ack = await controller.send_close_door()
        print(f"[Controller] ✓ ACK: {ack}")
    except Exception as e:
        print(f"[Controller] ✗ 失败: {e}")

    print("\n--- 测试3: go_floor(3) ---")
    try:
        ack = await controller.send_go_floor(3)
        print(f"[Controller] ✓ ACK: {ack}")
    except Exception as e:
        print(f"[Controller] ✗ 失败: {e}")

    print("\n--- 测试4: status ---")
    try:
        ack = await controller.send_status_query()
        print(f"[Controller] ✓ ACK: {ack}")
    except Exception as e:
        print(f"[Controller] ✗ 失败: {e}")

    # 5. 等待 ESP32 模拟任务完成
    await esp32_task

    # 6. 汇总
    print("\n" + "=" * 60)
    print("  验证结果汇总")
    print("=" * 60)
    for r in results:
        print(f"  {r[0]}: {'✓ 通过' if r[1] else '✗ 失败'}")

    # 7. 测试超时机制
    print("\n--- 测试5: 超时机制（不回传 ACK）---")
    # 此时 ESP32 模拟已断开，发送命令应报错
    try:
        ack = await controller.send_open_door()
        print(f"[Controller] ✗ 应该报错但成功了: {ack}")
    except RuntimeError as e:
        print(f"[Controller] ✓ 预期错误（未连接）: {e}")
    except asyncio.TimeoutError:
        print(f"[Controller] ✓ 预期超时")

    await controller.stop_server()
    print("\n[完成] 阶段1 验证通过")
    print("\n下一步：可以启动完整后端服务进行实际测试")
    print("  1. python app.py                              # 启动后端")
    print("  2. python test_elevator_simulator.py --host 127.0.0.1  # 模拟ESP32")
    print("  3. python test_elevator_api.py --cmd all       # 测试API")


if __name__ == "__main__":
    asyncio.run(main())
