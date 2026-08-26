# -*- coding: utf-8 -*-
"""
模拟 rosbridge 服务器（双车 pose 模拟器）
==========================================
用途：不依赖真实小车/rosbridge，测试后端 pose 链路与前端实时地图是否正常工作。

原理：
  1. 在 127.0.0.1:9090 起一个 WebSocket 服务器，实现 rosbridge 最小协议子集
     - 响应后端的 "op":"subscribe"（记录订阅的 topic）
     - 以 2Hz 向已订阅客户端推送 pose 消息：{"op":"publish","topic":"/car0X_pose","msg":{"data":"x,y"}}
     - 接收后端 "op":"publish"（start/running 等信号）并打印（可同时验证发送链）
  2. 车1 绕 (2.0, 1.0) 画圆，车2 绕 (-1.0, 2.0) 反向画圆，半径 1m，周期 30 秒

测试步骤：
  1. 修改 .env：CAR1_WS_HOST=127.0.0.1、CAR2_WS_HOST=127.0.0.1（端口均 9090）
  2. 本终端:        python mock_rosbridge.py
  3. 另一终端启动后端: python run_backend.py
  4. 浏览器打开大屏前端，观察两车沿圆周实时移动
     或 curl http://127.0.0.1:8080/api/v1/robot/pose 多次对比 x/y 变化
"""
import asyncio
import json
import math
import time

import websockets

HOST = "127.0.0.1"
PORT = 9090
POSE_HZ = 2.0                      # pose 推送频率（与真实 publisher 一致）
PERIOD = 30.0                      # 画圆周期（秒）
CAR1_POSE_TOPIC = "car01_pose"    # 注意：不带斜杠，与后端 config.py 的 pose_topic 命名严格一致
CAR2_POSE_TOPIC = "car02_pose"

# 模拟轨迹参数: topic -> (圆心x, 圆心y, 半径, 方向)
TRAJECTORIES = {
    CAR1_POSE_TOPIC: (2.0, 1.0, 1.0, 1.0),
    CAR2_POSE_TOPIC: (-1.0, 2.0, 1.0, -1.0),
}

connected = set()          # 所有客户端连接
subscriptions = {}         # ws -> set(topic)，模拟 rosbridge 按订阅过滤分发


def make_pose(topic: str, t: float) -> str:
    cx, cy, r, direction = TRAJECTORIES[topic]
    angle = direction * 2 * math.pi * ((t % PERIOD) / PERIOD)
    x = cx + r * math.cos(angle)
    y = cy + r * math.sin(angle)
    return json.dumps({
        "op": "publish",
        "topic": topic,
        "msg": {"data": f"{x:.3f},{y:.3f}"},
    })


async def handler(ws):
    peer = f"{ws.remote_address[0]}:{ws.remote_address[1]}" if ws.remote_address else "?"
    subscriptions[ws] = set()
    connected.add(ws)
    print(f"[MOCK] 客户端已连接: {peer}（当前连接数 {len(connected)}）")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                print(f"[MOCK] 非 JSON 消息，忽略: {str(raw)[:100]}")
                continue

            op = msg.get("op")
            topic = msg.get("topic", "")

            if op == "subscribe":
                subscriptions[ws].add(topic)
                print(f"[MOCK] {peer} 订阅: {topic}（类型 {msg.get('type')}）")
            elif op == "unsubscribe":
                subscriptions[ws].discard(topic)
            elif op == "publish":
                # 后端发来的信号（start/running/end/lift-across 等），打印留痕
                data = msg.get("msg", {}).get("data", "")
                print(f"[MOCK] {peer} ← 后端发送: topic={topic} data={str(data)[:80]}")
            elif op == "advertise":
                print(f"[MOCK] {peer} advertise: {topic}（忽略）")
            else:
                print(f"[MOCK] {peer} 未知 op={op}，忽略")
    except websockets.ConnectionClosed:
        pass
    finally:
        connected.discard(ws)
        subscriptions.pop(ws, None)
        print(f"[MOCK] 客户端断开: {peer}（剩余 {len(connected)}）")


async def pose_broadcaster():
    """全局 2Hz 推送：只向订阅了对应 topic 的客户端发送（模拟 rosbridge 订阅过滤）"""
    t0 = time.monotonic()
    interval = 1.0 / POSE_HZ
    tick = 0
    while True:
        t = time.monotonic() - t0
        targets = []
        for ws, subs in subscriptions.items():
            for topic in (CAR1_POSE_TOPIC, CAR2_POSE_TOPIC):
                if topic in subs:
                    targets.append(ws.send(make_pose(topic, t)))
        if targets:
            await asyncio.gather(*targets, return_exceptions=True)
        tick += 1
        if tick % int(POSE_HZ * 10) == 0:  # 每 10 秒打印一次状态
            print(f"[MOCK] 已推送 {tick} 轮 pose，连接数 {len(connected)}")
        await asyncio.sleep(interval)


async def main():
    print(f"[MOCK] 模拟 rosbridge 启动: ws://{HOST}:{PORT}")
    print(f"[MOCK] 车1 轨迹: 绕{TRAJECTORIES[CAR1_POSE_TOPIC][:3]} 圆周 {PERIOD}s/圈")
    print(f"[MOCK] 车2 轨迹: 绕{TRAJECTORIES[CAR2_POSE_TOPIC][:3]} 圆周 {PERIOD}s/圈")
    print(f"[MOCK] 推送频率: {POSE_HZ}Hz | 等待后端连接...")
    async with websockets.serve(handler, HOST, PORT):
        await pose_broadcaster()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MOCK] 已停止")
