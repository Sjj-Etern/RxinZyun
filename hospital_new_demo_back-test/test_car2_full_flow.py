"""
车2 ROS 完整通信模拟脚本（7 步全流程，纯模拟，不等待车2）

模拟"系统(后端)"与"车2(ROS)"的完整 7 步对话，严格照搬 车2_ROS通信文档.md：

  ① 系统→车2  {prescription_code}_pharmacist-success   (发出)
  ② 车2→系统  {prescription_code}_lift-arrive           (接收-模拟，不等待)
  ③ 系统→车2  {prescription_code}_lift-across           (发出)
  ④ 延迟 60 秒                                          (模拟，默认不实际等待)
  ⑤ 系统→车2  {prescription_code}_lift-open             (发出)
  ⑥ 车2→系统  {prescription_code}_nurse_arrive           (接收-模拟，不等待)
  ⑦ 系统→车2  {prescription_code}_nurse-success         (发出)

特点：
  - 不等待车2发来的 ②⑥ —— 脚本直接把"车2应当发来的内容"列出来(模拟接收)，继续往下走
  - 同时列出"发出的内容"(①③⑤⑦)和"接收的内容"(②⑥)，完整格式
  - 真连接为最佳努力：能连上 rosbridge 就真发 ①③⑤⑦；连不上就纯打印(模拟发送)
  - 跑全流程极快，不依赖车2在线

发送格式照搬 his_sender.py；接收帧格式照搬 ros_listener.py 收到的 rosbridge 帧。
连接配置取自 .env（注意文档把 IP 误写为 192.168.51.12，实际 .env 是 192.168.51.43）。

使用方式：
  python test_car2_full_flow.py                                   # 纯模拟，瞬间跑完
  python test_car2_full_flow.py --prescription-code RXZY20260820001
  python test_car2_full_flow.py --connect                          # 尝试真连 rosbridge 真发 ①③⑤⑦
  python test_car2_full_flow.py --delay 60                         # ④ 真等 60 秒(模拟后端)
"""
import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    websockets = None  # 纯模拟模式下不需要；--connect 时才需要


# ===== 默认配置（与 .env 中 CAR2_* 一致）=====
DEFAULT_HOST = "192.168.51.43"          # CAR2_WS_HOST（文档误写为 192.168.51.12，以 .env 为准）
DEFAULT_PORT = 9090                     # CAR2_WS_PORT
SUB_TOPIC = "/car02_pub"               # CAR2_TOPIC（车2→系统 方向，接收帧的 topic）
PUB_TOPIC = "/car02_rxzy_msg"          # CAR2_SEND_TOPIC（系统→车2 方向，发送帧的 topic）
PUB_MSG_TYPE = "his_sub"               # CAR2_SEND_MSG_TYPE（advertise type）
DEFAULT_PRESCRIPTION_CODE = "TEST001"
DEFAULT_MEDICINE_ID = 1
DEFAULT_DELAY = 0                      # ④ 延迟秒数(模拟模式默认0=不实际等待；实际后端 LIFT_ACROSS_DELAY=60)
REAL_LIFT_ACROSS_DELAY = 60            # 真实后端的延迟值(仅用于提示)


def log(msg):
    """带时间戳的日志"""
    print(f"[{time.strftime('%H:%M:%S')}] [车2全流程] {msg}")


# ============================================================
# 发送侧：构造与 his_sender.py 字节级一致的 publish 帧
# ============================================================
def build_publish_frame(data_str, prescription_code=None, medicine_id=None):
    """构造 系统→车2 的 publish 帧（与后端 his_sender.py 一致，纯字符串载荷）。
    msg 只保留 data 字段（决策乙：信息已拼进 data，medicine_id/prescription_code
    不再作为 msg 独立字段发送）。prescription_code/medicine_id 保留仅为调用兼容。"""
    return {
        "op": "publish",
        "topic": PUB_TOPIC,
        "msg": {"data": data_str},
    }


# ============================================================
# 接收侧：构造 车2→系统 的 incoming 帧（ros_listener.py 收到的 rosbridge 帧）
# ============================================================
def build_incoming_frame(data_str):
    """构造 车2→系统 的 incoming 帧。
    后端 ros_listener.py:735 取 msg.data，故帧结构为 {op,publish,topic:/car02_pub,msg:{data}}。"""
    return {
        "op": "publish",
        "topic": SUB_TOPIC,
        "msg": {"data": data_str},
    }


async def do_send(ws, connected, status, prescription_code, medicine_id=None, with_medicine_id=False):
    """发出一步 系统→车2 信号。connected=True 则真发，否则纯打印。"""
    data_str = f"{prescription_code}_{status}"
    frame = build_publish_frame(
        data_str,
        prescription_code,
        medicine_id=medicine_id if with_medicine_id else None,
    )
    payload = json.dumps(frame)
    tag = "真实发送" if connected else "模拟发送"
    log(f"→ [{tag}] {payload}")
    # medicine_id 按决策乙不再随信号发送（仅 msg.data 字符串），日志不显示以免误读
    log(f"   方向: 系统→车2 | 信号: {status} | data={data_str}")
    if connected and ws is not None:
        try:
            await ws.send(payload)
        except Exception as e:
            log(f"   [发送异常] {e}")


def simulate_receive(status, prescription_code):
    """模拟接收一步 车2→系统 信号（不等待，直接列出车2应当发来的内容）。"""
    data_str = f"{prescription_code}_{status}"
    frame = build_incoming_frame(data_str)
    payload = json.dumps(frame)
    log(f"← [模拟接收] {payload}")
    log(f"   方向: 车2→系统 | 信号: {status} | data={data_str}")


async def run_full_flow(host, port, prescription_code, medicine_id, delay, try_connect):
    # ----- 最佳努力连接 -----
    ws = None
    connected = False
    if try_connect:
        if websockets is None:
            log("⚠ 未安装 websockets 库，--connect 不可用，转为纯模拟")
        else:
            ws_url = f"ws://{host}:{port}"
            log(f"尝试连接 ROS WebSocket: {ws_url} (最长 5s)")
            try:
                ws = await asyncio.wait_for(websockets.connect(ws_url), timeout=5)
                connected = True
                log(f"✓ 已连接，将真实发送 ①③⑤⑦")
                # 与后端 his_sender.py _ensure_ws_connection 一致：unadvertise → advertise
                unadv = {"op": "unadvertise", "topic": PUB_TOPIC}
                await ws.send(json.dumps(unadv))
                log(f"→ 发送 unadvertise: {json.dumps(unadv)}")
                await asyncio.sleep(0.1)
                adv = {"op": "advertise", "topic": PUB_TOPIC, "type": PUB_MSG_TYPE}
                await ws.send(json.dumps(adv))
                log(f"→ 发送 advertise:   {json.dumps(adv)}")
                await asyncio.sleep(0.3)
            except Exception as e:
                log(f"⚠ rosbridge 不可达({e})，转为纯模拟(只打印发送内容)")
                ws = None
                connected = False
    else:
        log("纯模拟模式(不加 --connect)，只打印发送内容，不连接 rosbridge")

    log("=" * 60)
    log(f"处方号 prescription_code = {prescription_code}")
    log(f"药品ID medicine_id       = {medicine_id}")
    log(f"发送 topic (系统→车2)     = {PUB_TOPIC}")
    log(f"接收 topic (车2→系统)     = {SUB_TOPIC}")
    log("=" * 60)

    # ============================================================
    # ① 系统→车2  pharmacist-success
    # ============================================================
    log("① [系统→车2] pharmacist-success")
    await do_send(ws, connected, "pharmacist-success", prescription_code,
                  medicine_id=medicine_id, with_medicine_id=True)

    # ============================================================
    # ② 车2→系统  lift-arrive   （模拟接收，不等待）
    # ============================================================
    log("② [车2→系统] lift-arrive  (模拟接收，不等待)")
    simulate_receive("lift-arrive", prescription_code)

    # ============================================================
    # ③ 系统→车2  lift-across
    # ============================================================
    log("③ [系统→车2] lift-across")
    await do_send(ws, connected, "lift-across", prescription_code)

    # ============================================================
    # ④ 延迟（车2进入电梯）
    # ============================================================
    if delay > 0:
        log(f"④ [延迟] 等待 {delay} 秒")
        for i in range(delay, 0, -1):
            print(f"\r[{time.strftime('%H:%M:%S')}] [车2全流程]    剩余 {i:3d}s   ",
                  end="", flush=True)
            await asyncio.sleep(1)
        print()
    else:
        log(f"④ [延迟] 模拟不实际等待 (实际后端 LIFT_ACROSS_DELAY={REAL_LIFT_ACROSS_DELAY}s)")

    # ============================================================
    # ⑤ 系统→车2  lift-open
    # ============================================================
    log("⑤ [系统→车2] lift-open")
    await do_send(ws, connected, "lift-open", prescription_code)

    # ============================================================
    # ⑥ 车2→系统  nurse_arrive   （模拟接收，不等待）
    # ============================================================
    log("⑥ [车2→系统] nurse_arrive (模拟接收，不等待)")
    simulate_receive("nurse_arrive", prescription_code)

    # ============================================================
    # ⑦ 系统→车2  nurse-success
    # ============================================================
    log("⑦ [系统→车2] nurse-success")
    await do_send(ws, connected, "nurse-success", prescription_code)

    # ----- 收尾 -----
    if ws is not None:
        try:
            await ws.close()
        except Exception:
            pass

    log("=" * 60)
    log("✓ 7 步全流程模拟完成（未等待车2任何信号）")
    log("=" * 60)
    log("【发出内容汇总】(系统→车2, topic=/car02_rxzy_msg):")
    log(f"  ① {prescription_code}_pharmacist-success  (2段, medicine_id 按决策乙已丢弃)")
    log(f"  ③ {prescription_code}_lift-across")
    log(f"  ⑤ {prescription_code}_lift-open")
    log(f"  ⑦ {prescription_code}_nurse-success")
    log("【接收内容汇总】(车2→系统, topic=/car02_pub):")
    log(f"  ② {prescription_code}_lift-arrive    (注意:连字符)")
    log(f"  ⑥ {prescription_code}_nurse_arrive   (注意:下划线)")


def main():
    parser = argparse.ArgumentParser(description="车2 ROS 完整通信模拟脚本(7步全流程,纯模拟不等待)")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"ROS WebSocket 地址 (默认 {DEFAULT_HOST}，即 .env CAR2_WS_HOST)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"ROS WebSocket 端口 (默认 {DEFAULT_PORT})")
    parser.add_argument("--prescription-code", default=DEFAULT_PRESCRIPTION_CODE,
                        help=f"处方号 (默认 {DEFAULT_PRESCRIPTION_CODE})")
    parser.add_argument("--medicine-id", type=int, default=DEFAULT_MEDICINE_ID,
                        help=f"药品ID (默认 {DEFAULT_MEDICINE_ID})")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                        help=f"步骤④延迟秒数 (默认 {DEFAULT_DELAY}=不实际等待；实际后端为 {REAL_LIFT_ACROSS_DELAY})")
    parser.add_argument("--connect", action="store_true",
                        help="尝试真连 rosbridge 真发 ①③⑤⑦(最佳努力，连不上自动转纯模拟)")
    args = parser.parse_args()

    print("=" * 60)
    print("  车2 ROS 完整通信模拟（7步全流程，不等待车2）")
    print("=" * 60)

    asyncio.run(run_full_flow(
        host=args.host,
        port=args.port,
        prescription_code=args.prescription_code,
        medicine_id=args.medicine_id,
        delay=args.delay,
        try_connect=args.connect,
    ))


if __name__ == "__main__":
    main()
