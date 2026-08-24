"""
车2 ROS 通信 - 第一个信号模拟脚本

模拟后端 his_sender.send_pharmacist_success() 向车2 发送的
"药师审核通过"信号 —— 即 车2_ROS通信文档.md 流程中的 ① pharmacist-success。
本脚本只发送这第一个信号，不发送后续 lift-across / lift-open / nurse-success 等。

发送内容与格式完全照搬后端 app/services/his_sender.py（字节级一致）：
  1. WebSocket 连接 ws://<host>:<port>
  2. 发 unadvertise → sleep 0.1s（与后端 _ensure_ws_connection 一致）
  3. 发 advertise  → sleep 0.3s（注册 topic）
  4. 发 publish：{prescription_code}_pharmacist-success（第一个信号）
  5. 短暂监听 rosbridge 反馈（2秒，仅接收，不发任何信号）

默认配置取自 .env 的 CAR2_*（注意：文档写的 192.168.51.12 是错的，实际 .env 是 192.168.51.43）。

使用方式：
  python test_pharmacist_success.py                                # 用默认值发一次
  python test_pharmacist_success.py --prescription-code RXZY20260820001
  python test_pharmacist_success.py --medicine-id 2
  python test_pharmacist_success.py --host 192.168.51.43 --port 9090

注意：本脚本与后端 app.py 互斥，不要同时跑（否则两个发布者都会向车2 发信号）。
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


# ===== 默认配置（与 .env 中 CAR2_* 一致）=====
DEFAULT_HOST = "192.168.51.43"        # CAR2_WS_HOST（文档误写为 192.168.51.12，以 .env 为准）
DEFAULT_PORT = 9090                  # CAR2_WS_PORT
DEFAULT_TOPIC = "/car02_rxzy_msg"    # CAR2_SEND_TOPIC
DEFAULT_MSG_TYPE = "his_sub"         # CAR2_SEND_MSG_TYPE
DEFAULT_PRESCRIPTION_CODE = "TEST001"
DEFAULT_MEDICINE_ID = 1


def log(msg):
    """带时间戳的日志"""
    print(f"[{time.strftime('%H:%M:%S')}] [车2模拟] {msg}")


async def send_pharmacist_success(host, port, topic, msg_type, prescription_code, medicine_id):
    ws_url = f"ws://{host}:{port}"
    log(f"连接 ROS WebSocket: {ws_url}")

    try:
        async with websockets.connect(ws_url) as ws:
            log(f"✓ 已连接: {ws_url}")

            # ① unadvertise（与后端 _ensure_ws_connection 完全一致）
            unadv = {
                "op": "unadvertise",
                "topic": topic,
            }
            await ws.send(json.dumps(unadv))
            log(f"→ 发送 unadvertise: {json.dumps(unadv)}")
            await asyncio.sleep(0.1)

            # ② advertise（注册 topic，与后端一致）
            adv = {
                "op": "advertise",
                "topic": topic,
                "type": msg_type,
            }
            await ws.send(json.dumps(adv))
            log(f"→ 发送 advertise:   {json.dumps(adv)}")
            await asyncio.sleep(0.3)

            # ③ publish 第一个信号 pharmacist-success
            data_str = f"{prescription_code}_pharmacist-success"
            # msg 只保留 data 字符串（与后端 his_sender.py 一致，决策乙：medicine_id 不随信号发送）
            publish_msg = {
                "op": "publish",
                "topic": topic,
                "msg": {
                    "data": data_str,
                },
            }
            payload = json.dumps(publish_msg)
            await ws.send(payload)
            log("→ 发送 publish (第一个信号):")
            log(f"   {payload}")
            log(f"   data: {data_str}")
            log(f"   medicine_id: {medicine_id}")
            log(f"   prescription_code: {prescription_code}")
            log("✓ 第一个信号已发送（仅此一个，不发送后续 lift-across/lift-open/nurse-success）")

            # 短暂监听 rosbridge 反馈（2秒，仅接收，不发任何信号）
            log("等待 2 秒接收 rosbridge 反馈（如有）...")
            try:
                reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
                log(f"← 收到反馈: {reply}")
            except asyncio.TimeoutError:
                log("（2 秒内无反馈，正常 —— publish 通常无回执）")

    except Exception as e:
        log(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="车2 ROS 第一个信号(pharmacist-success)模拟脚本")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"ROS WebSocket 地址 (默认 {DEFAULT_HOST}，即 .env CAR2_WS_HOST)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"ROS WebSocket 端口 (默认 {DEFAULT_PORT})")
    parser.add_argument("--topic", default=DEFAULT_TOPIC,
                        help=f"发布 topic (默认 {DEFAULT_TOPIC}，即 CAR2_SEND_TOPIC)")
    parser.add_argument("--msg-type", default=DEFAULT_MSG_TYPE,
                        help=f"advertise 类型 (默认 {DEFAULT_MSG_TYPE}，即 CAR2_SEND_MSG_TYPE)")
    parser.add_argument("--prescription-code", default=DEFAULT_PRESCRIPTION_CODE,
                        help=f"处方号 (默认 {DEFAULT_PRESCRIPTION_CODE})")
    parser.add_argument("--medicine-id", type=int, default=DEFAULT_MEDICINE_ID,
                        help=f"药品ID (默认 {DEFAULT_MEDICINE_ID})")
    args = parser.parse_args()

    print("=" * 60)
    print("  车2 ROS 第一个信号模拟 (pharmacist-success)")
    print("=" * 60)

    asyncio.run(send_pharmacist_success(
        host=args.host,
        port=args.port,
        topic=args.topic,
        msg_type=args.msg_type,
        prescription_code=args.prescription_code,
        medicine_id=args.medicine_id,
    ))


if __name__ == "__main__":
    main()
