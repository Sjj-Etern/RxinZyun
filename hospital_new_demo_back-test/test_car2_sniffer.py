"""
车2 ROS 流量嗅探器（独立监听，不依赖后端 app.py）

同时订阅车2 的两个 topic，把车2 收发的所有消息打出来，用来判断：
  - 车2 到底有没有回发 ② lift-arrive / ⑥ nurse_arrive（盯 /car02_pub）
  - 系统/脚本发给车2 的 ①③⑤⑦ 有没有真到（盯 /car02_rxzy_msg）

用法定位"系统没收到车2返回"问题：
  1. 跑这个嗅探器（终端A）
  2. 另开终端跑 python test_pharmacist_success.py 发 ①（终端B）
  3. 看终端A：
     - /car02_rxzy_msg 上出现 "...pharmacist-success" → ① 发出去了 ✓
     - /car02_pub 上出现 "...lift-arrive"            → 车2 回发了 ② ✓ → 那是后端没收到(订阅/连接问题)
     - /car02_pub 上啥都没有                          → 车2 根本没回发 ② → 问题在车2 ROS 节点

连接 ws://192.168.51.43:9090（取自 .env CAR2_WS_HOST），topic 取自 .env。
Ctrl+C 退出。

使用方式：
  python test_car2_sniffer.py                              # 默认监听两个 topic
  python test_car2_sniffer.py --host 192.168.51.43
  python test_car2_sniffer.py --only pub                   # 只盯车2回发(/car02_pub)
"""
import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    print("缺少 websockets 库，请先安装: pip install websockets")
    sys.exit(1)


# ===== 默认配置（与 .env CAR2_* 一致）=====
DEFAULT_HOST = "192.168.51.43"          # CAR2_WS_HOST
DEFAULT_PORT = 9090                     # CAR2_WS_PORT
PUB_TOPIC = "/car02_pub"               # CAR2_TOPIC（车2→系统，车2回发的信号在这）
SEND_TOPIC = "/car02_rxzy_msg"          # CAR2_SEND_TOPIC（系统→车2，发给车2的信号在这）
SUB_TYPE = "std_msgs/String"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] [嗅探] {msg}", flush=True)


async def subscribe_and_listen(ws, topic, direction):
    """订阅一个 topic 并打印收到的每条消息。direction 用于标注方向。"""
    sub_msg = {
        "op": "subscribe",
        "topic": topic,
        "type": SUB_TYPE,
    }
    await ws.send(json.dumps(sub_msg))
    log(f"已订阅 {topic}  ({direction})")
    # 吸收订阅确认
    try:
        confirm = await asyncio.wait_for(ws.recv(), timeout=3)
        log(f"  {topic} 订阅确认: {confirm[:120]}")
    except asyncio.TimeoutError:
        log(f"  {topic} 订阅确认超时(3s)，继续")
    except Exception as e:
        log(f"  {topic} 订阅确认异常: {e}")

    while True:
        try:
            raw = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            log(f"  {topic} 连接关闭")
            return
        except Exception as e:
            log(f"  {topic} 接收异常: {e}")
            return
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            log(f"  [{direction}] 非JSON: {raw[:150]}")
            continue
        # 只关心 publish 到本 topic 的消息帧
        if obj.get("op") == "publish" and obj.get("topic") == topic:
            msg = obj.get("msg", {})
            data = msg.get("data", "<无data字段>")
            log(f"  ◀ [{direction}] {topic}  data={data}")
        elif obj.get("op") == "publish":
            # 其它 topic 的消息（rosbridge 可能复用连接转发），标注一下
            log(f"  (其它topic) {obj.get('topic')}  data={obj.get('msg', {}).get('data', '')}")
        else:
            log(f"  (非publish帧) {raw[:120]}")


async def run_sniffer(host, port, only):
    ws_url = f"ws://{host}:{port}"
    log(f"连接 ROS WebSocket: {ws_url}")
    try:
        async with websockets.connect(ws_url) as ws:
            log(f"✓ 已连接: {ws_url}")
            log("=" * 60)
            log(f"开始监听车2 流量（Ctrl+C 退出）")
            log("=" * 60)

            tasks = []
            if only in ("pub", "both"):
                # /car02_pub = 车2→系统（车2回发的 ②⑥）
                tasks.append(asyncio.create_task(subscribe_and_listen(ws, PUB_TOPIC, "车2→系统")))
            if only in ("send", "both"):
                # /car02_rxzy_msg = 系统→车2（发给车2的 ①③⑤⑦）
                tasks.append(asyncio.create_task(subscribe_and_listen(ws, SEND_TOPIC, "系统→车2")))

            await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log("用户中断，退出")
    except Exception as e:
        log(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="车2 ROS 流量嗅探器(独立监听两个topic)")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"ROS WebSocket 地址 (默认 {DEFAULT_HOST}，即 .env CAR2_WS_HOST)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"ROS WebSocket 端口 (默认 {DEFAULT_PORT})")
    parser.add_argument("--only", choices=["pub", "send", "both"], default="both",
                        help="pub=只盯车2回发(/car02_pub); send=只盯发给车2(/car02_rxzy_msg); both=都盯(默认)")
    args = parser.parse_args()

    print("=" * 60)
    print("  车2 ROS 流量嗅探器")
    print(f"  监听: {PUB_TOPIC}(车2→系统) + {SEND_TOPIC}(系统→车2)")
    print("=" * 60)

    try:
        asyncio.run(run_sniffer(args.host, args.port, args.only))
    except KeyboardInterrupt:
        log("已退出")


if __name__ == "__main__":
    main()
