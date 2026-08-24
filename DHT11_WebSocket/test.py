import asyncio
import json
import random
import websockets
from datetime import datetime

WS_URL = "ws://192.168.1.103:8080/api/dht11/wifi"


async def simulate_esp32():
    print("=" * 60)
    print("DHT11 WebSocket 测试脚本 (模拟 ESP32)")
    print("=" * 60)
    print(f"目标地址: {WS_URL}")
    print(f"发送间隔: 5秒")
    print(f"数据格式: {{\"temp\":xx,\"humi\":xx}}")
    print("=" * 60)

    input("\n按回车键开始连接...")

    try:
        print(f"\n[WS] 正在连接到 {WS_URL} ...")
        async with websockets.connect(WS_URL) as ws:
            print("[WS] ✓ 连接成功!\n")

            send_count = 0

            while True:
                send_count += 1
                temp = round(24.0 + random.uniform(-2.0, 2.0), 1)
                humi = round(60.0 + random.uniform(-10.0, 10.0), 1)

                payload = {"temp": temp, "humi": humi}
                message = json.dumps(payload)

                print(f"{'=' * 60}")
                print(f"第 {send_count} 次发送")
                print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'=' * 60}")
                print(f"[WS] → 发送: {message}")

                await ws.send(message)

                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    print(f"[WS] ← 响应: {response}")

                    resp_data = json.loads(response)
                    if resp_data.get("status") == "success":
                        print(f"[WS] ✓ 服务器确认成功")
                    else:
                        print(f"[WS] ✗ 服务器返回错误: {resp_data}")
                except asyncio.TimeoutError:
                    print("[WS] ✗ 等待响应超时")

                print(f"\n[WS] 等待5秒后继续...")
                await asyncio.sleep(5)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"\n[WS] 连接已关闭: {e}")
    except ConnectionRefusedError:
        print(f"\n[WS] ✗ 无法连接到服务器: {WS_URL}")
        print("[WS]   请确认后端服务已启动")
    except KeyboardInterrupt:
        print(f"\n\n{'=' * 60}")
        print("测试已停止")
        print(f"{'=' * 60}")
        print(f"[统计] 总发送次数: {send_count}")
        print(f"{'=' * 60}")
    except Exception as e:
        print(f"\n[WS] ✗ 异常: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(simulate_esp32())
    except KeyboardInterrupt:
        print("\n程序已退出")
