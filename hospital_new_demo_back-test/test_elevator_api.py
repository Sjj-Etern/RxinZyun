"""
电梯控制 API 测试脚本

通过后端 HTTP API 测试电梯控制命令。
需要先启动后端服务 + test_elevator_simulator.py（模拟 ESP32）。

使用方式：
  1. 启动后端服务: python app.py
  2. 另开终端运行 ESP32 模拟器: python test_elevator_simulator.py --host 127.0.0.1
  3. 运行本脚本: python test_elevator_api.py

  或单独指定命令测试：
    python test_elevator_api.py --cmd open_door
    python test_elevator_api.py --cmd close_door
    python test_elevator_api.py --cmd go_floor --floor 3
    python test_elevator_api.py --cmd status
    python test_elevator_api.py --cmd all    # 顺序执行所有命令
"""
import argparse
import sys
import time
import requests


# ===== 配置 =====
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8080
BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"


def log(msg):
    """带时间戳的日志"""
    print(f"[{time.strftime('%H:%M:%S')}] [API测试] {msg}")


def check_elevator_state():
    """查询电梯控制器状态"""
    url = f"{BASE_URL}/api/v1/elevator/state"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        log(f"电梯状态: connected={data.get('connected')}, client={data.get('client_addr')}")
        return data
    except Exception as e:
        log(f"✗ 查询状态失败: {e}")
        return None


def send_command(cmd, floor=3):
    """发送电梯控制命令"""
    url = f"{BASE_URL}/api/v1/elevator/command"
    params = {"cmd": cmd, "floor": floor}

    log(f"发送命令: cmd={cmd}, floor={floor}")
    try:
        resp = requests.post(url, params=params, timeout=15)
        data = resp.json()

        if data.get("status") == "success":
            ack = data.get("ack", {})
            log(f"✓ 成功: cmd={ack.get('cmd')}, status={ack.get('status')}")
            if "floor" in ack:
                log(f"  楼层: {ack.get('floor')}")
            if "temp" in ack:
                log(f"  温度: {ack.get('temp')}°C, 湿度: {ack.get('humi')}%")
        else:
            log(f"✗ 失败: {data.get('message', '未知错误')}")

        return data

    except requests.exceptions.ConnectionError:
        log(f"✗ 无法连接后端，请确认服务已启动: {BASE_URL}")
        return None
    except Exception as e:
        log(f"✗ 异常: {e}")
        return None


def test_all_commands():
    """顺序测试所有命令"""
    print("=" * 60)
    print("  电梯控制 API 全流程测试")
    print("=" * 60)

    # 1. 查询状态（等待ESP32连接，最多约30秒，给ESP上电连接的时间）
    log("步骤1: 等待ESP32连接...")
    state = None
    for i in range(10):
        state = check_elevator_state()
        if state and state.get("connected"):
            log(f"✓ ESP32 已连接: {state.get('client_addr')}")
            break
        log(f"  ESP32 未连接，3秒后重试 ({i+1}/10)... 请确认ESP32已上电")
        time.sleep(3)
    if not state or not state.get("connected"):
        log("✗ ESP32 未连接，请确认：")
        log("  1. 后端已启动: python app.py")
        log("  2. ESP32已上电并烧录含固定后端IP的固件")
        log(f"  3. wifi_.h中ELEVATOR_SERVER_IP指向运行后端的电脑IP")
        return False

    print()

    # 2. 查询电梯状态
    log("步骤2: 查询电梯当前楼层和温湿度")
    send_command("status")

    print()
    time.sleep(1)

    # 3. 开门
    log("步骤3: 开门")
    send_command("open_door")

    print()
    time.sleep(1)

    # 4. 去3楼
    log("步骤4: 去3楼")
    send_command("go_floor", floor=3)

    print()
    time.sleep(1)

    # 5. 关门
    log("步骤5: 关门")
    send_command("close_door")

    print()
    time.sleep(1)

    # 6. 再次查询状态
    log("步骤6: 再次查询状态")
    send_command("status")

    print()
    log("=" * 60)
    log("全流程测试完成")
    log("=" * 60)
    return True


def main():
    global BACKEND_HOST, BACKEND_PORT, BASE_URL

    parser = argparse.ArgumentParser(description="电梯控制 API 测试脚本")
    parser.add_argument("--host", type=str, default=BACKEND_HOST,
                        help=f"后端服务地址（默认 {BACKEND_HOST}）")
    parser.add_argument("--port", type=int, default=BACKEND_PORT,
                        help=f"后端服务端口（默认 {BACKEND_PORT}）")
    parser.add_argument("--cmd", type=str, default="all",
                        choices=["all", "open_door", "close_door", "go_floor", "status", "state"],
                        help="要执行的命令（默认 all）")
    parser.add_argument("--floor", type=int, default=3,
                        help="目标楼层（go_floor 命令使用，默认 3）")
    args = parser.parse_args()

    BACKEND_HOST = args.host
    BACKEND_PORT = args.port
    BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    if args.cmd == "all":
        test_all_commands()
    elif args.cmd == "state":
        check_elevator_state()
    elif args.cmd == "go_floor":
        send_command("go_floor", floor=args.floor)
    else:
        send_command(args.cmd)


if __name__ == "__main__":
    main()
