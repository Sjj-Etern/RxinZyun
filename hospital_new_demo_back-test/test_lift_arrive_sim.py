"""
lift-arrive 全流程模拟测试（极简版）

模拟 rosbridge WebSocket 服务端，自动完成车2 ROS 通信全流程：
  ① 模拟车2 → 后端: lift-arrive
  ② 后端 → 模拟车2: lift-across（后端自动开门→发lift-across）
  ③ 后端 → 模拟车2: lift-open（后端等待5秒→关门→去楼层→发lift-open）
  ④ 模拟车2 → 后端: nurse_arrive（自动发送）
  ⑤ 后端 → 模拟车2: nurse-success

用法:
  1. 修改 .env: CAR2_WS_HOST=127.0.0.1
  2. 设置快速延迟: curl -X POST "http://127.0.0.1:8080/api/v1/elevator/debug/delay?seconds=5"
  3. 启动后端: python app.py
  4. 运行本脚本: python test_lift_arrive_sim.py

  可选参数:
    --nurse-delay  护士到达延迟秒数（默认5，设0立即）
    --code          处方编码（默认TEST001）
"""
import asyncio
import json
import argparse
import time
import urllib.request
import urllib.error
from datetime import datetime

try:
    import websockets
except ImportError:
    print("请安装: pip install websockets")
    exit(1)

# 全局状态
subscribers = {}   # topic → set(websocket)
advertisers = {}   # topic → set(websocket)
received_msgs = [] # 收到的所有消息
nurse_event = asyncio.Event()


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg):
    print(f"[{ts()}] {msg}")


def set_backend_delay(backend_host: str, backend_port: int, seconds: int) -> bool:
    """调用后端 debug API，动态设置 lift_across_delay（秒）"""
    url = f"http://{backend_host}:{backend_port}/api/v1/elevator/debug/delay?seconds={seconds}"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            log(f"[设置延迟] POST {url} → {body}")
            return True
    except Exception as e:
        log(f"[设置延迟] 失败: {e}")
        return False


async def handler(websocket):
    """处理 WebSocket 连接（rosbridge 协议）"""
    peer = websocket.remote_address
    log(f"[连接] 客户端已连接: {peer[0]}:{peer[1]}")

    try:
        async for raw in websocket:
            msg = json.loads(raw)
            op = msg.get("op", "")
            topic = msg.get("topic", "")

            if op == "subscribe":
                # 后端订阅 /car02_pub
                subscribers.setdefault(topic, set()).add(websocket)
                log(f"[订阅] {topic}")
                # 回复确认
                await websocket.send(json.dumps({"op": "subscribe", "topic": topic}))
                log(f"[确认] 已回复订阅确认: {topic}")

            elif op == "unadvertise":
                advertisers.pop(topic, None)
                log(f"[取消广告] {topic}")

            elif op == "advertise":
                # 后端注册发送 topic /car02_rxzy_msg
                advertisers.setdefault(topic, set()).add(websocket)
                log(f"[广告] {topic}")
                await websocket.send(json.dumps({"op": "advertise", "topic": topic}))

            elif op == "publish":
                # 后端发送消息到 /car02_rxzy_msg
                data = msg.get("msg", {}).get("data", "")
                log(f"[收到后端消息] topic={topic}, data={data}")
                received_msgs.append(data)

            else:
                log(f"[未知op] {op}: {raw[:100]}")

    except websockets.ConnectionClosed:
        log(f"[断开] {peer[0]}:{peer[1]}")
    finally:
        for s in subscribers.values():
            s.discard(websocket)
        for s in advertisers.values():
            s.discard(websocket)


async def send_to_subscribers(topic: str, data: str):
    """向订阅了 topic 的客户端发送消息"""
    subs = subscribers.get(topic, set()).copy()
    if not subs:
        log(f"[警告] topic {topic} 无订阅者，消息丢失: {data}")
        return False

    msg = json.dumps({
        "op": "publish",
        "topic": topic,
        "msg": {"data": data}
    })
    for ws in subs:
        try:
            await ws.send(msg)
        except Exception as e:
            log(f"[错误] 发送失败: {e}")
    log(f"[已发送] {topic}: {data}")
    return True


async def wait_for_msg(keyword: str, timeout: float = 30.0) -> bool:
    """等待收到的消息中包含关键词"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for msg in received_msgs:
            if keyword in msg:
                return True
        await asyncio.sleep(0.5)
    return False


async def run_test(args):
    """主测试流程"""
    code = args.code
    medicine_id = 1
    topic_pub = "/car02_pub"       # 车2发布，后端订阅
    nurse_delay = args.nurse_delay

    print("=" * 60)
    print("  lift-arrive 全流程模拟测试")
    print("=" * 60)
    print(f"  处方编码: {code}")
    print(f"  护士延迟: {nurse_delay} 秒")
    print(f"  ROS 端口: 9090")
    print("=" * 60)

    # 等待后端连接
    log("等待后端连接...")
    for i in range(30):
        if subscribers.get(topic_pub):
            log("✓ 后端已订阅 /car02_pub")
            break
        await asyncio.sleep(1)
    else:
        log("✗ 后端未连接，退出")
        return

    # 自动设置快速延迟（避免 .env 默认 60 秒导致测试过慢）
    log(f"自动设置后端 lift_across_delay={args.lift_delay} 秒...")
    set_backend_delay(args.backend_host, args.backend_port, args.lift_delay)
    await asyncio.sleep(1)

    # 清空已接收消息
    received_msgs.clear()

    # ===== Step ①: 发送 lift-arrive =====
    log("=" * 60)
    log("Step ① 模拟车2 → 后端: lift-arrive")
    log("=" * 60)
    msg = f"{medicine_id}_{code}_lift-arrive"
    await send_to_subscribers(topic_pub, msg)

    # ===== Step ②: 等待后端发 lift-across =====
    log("等待后端发 lift-across（后端会先开门再发）...")
    ok = await wait_for_msg("lift-across", timeout=30)
    if ok:
        log("✓ 收到 lift-across")
    else:
        log("✗ 超时未收到 lift-across")
        return

    # ===== Step ③: 等待后端发 lift-open =====
    log("等待后端发 lift-open（后端会等延迟→关门→去楼层→发lift-open）...")
    ok = await wait_for_msg("lift-open", timeout=120)
    if ok:
        log("✓ 收到 lift-open")
    else:
        log("✗ 超时未收到 lift-open")
        return

    # ===== Step ④: 发送 nurse_arrive =====
    log(f"等待 {nurse_delay} 秒后发送 nurse_arrive...")
    await asyncio.sleep(nurse_delay)

    log("Step ④ 模拟车2 → 后端: nurse_arrive")
    msg = f"{medicine_id}_{code}_nurse_arrive"
    await send_to_subscribers(topic_pub, msg)

    # ===== Step ⑤: 等待后端发 nurse-success =====
    log("等待后端发 nurse-success...")
    ok = await wait_for_msg("nurse-success", timeout=15)
    if ok:
        log("✓ 收到 nurse-success")
    else:
        log("✗ 超时未收到 nurse-success")

    # ===== 汇总 =====
    log("=" * 60)
    log("流程完成，后端发送的所有消息:")
    for i, m in enumerate(received_msgs, 1):
        log(f"  [{i}] {m}")
    log("=" * 60)

    expected = ["lift-across", "lift-open", "nurse-success"]
    passed = sum(1 for e in expected if any(e in m for m in received_msgs))
    log(f"结果: {passed}/{len(expected)} 步通过")


async def main():
    parser = argparse.ArgumentParser(description="lift-arrive 全流程模拟测试")
    parser.add_argument("--nurse-delay", type=int, default=5, help="护士到达延迟秒数")
    parser.add_argument("--code", default="TEST001", help="处方编码")
    parser.add_argument("--port", type=int, default=9090, help="ROS WebSocket 端口")
    parser.add_argument("--backend-host", default="127.0.0.1", help="后端 HTTP 主机")
    parser.add_argument("--backend-port", type=int, default=8080, help="后端 HTTP 端口")
    parser.add_argument("--lift-delay", type=int, default=5, help="设置后端 lift_across_delay 秒数（默认5）")
    args = parser.parse_args()

    # 启动 WebSocket 服务端
    server = await websockets.serve(handler, "0.0.0.0", args.port)
    log(f"模拟 rosbridge 服务端启动: ws://0.0.0.0:{args.port}")

    # 运行测试
    await run_test(args)

    # 关闭
    server.close()
    await server.wait_closed()
    log("服务端已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")
