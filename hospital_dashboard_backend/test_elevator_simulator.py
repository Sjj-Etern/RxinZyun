"""
电梯 ESP32 模拟器（测试脚本）

模拟 Elevator_AccessControl ESP32 的行为：
  1. 通过 UDP 广播发现后端服务端 IP
  2. 通过 TCP 连接后端服务端（端口 10833）
  3. 接收后端下发的电梯控制命令
  4. 回传 ACK 确认

使用方式：
  1. 先启动后端服务（python app.py）
  2. 运行本脚本：python test_elevator_simulator.py
  3. 在另一个终端用 curl 调用后端 API 发送命令：
     curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=open_door"
     curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=close_door"
     curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=go_floor&floor=3"
     curl -X POST "http://127.0.0.1:8080/api/v1/elevator/command?cmd=status"

  4. 观察本脚本输出，确认命令接收和 ACK 回传正确

注意：本脚本也可以跳过 UDP 发现，直接连接指定 IP（见 --host 参数）
"""
import socket
import json
import time
import threading
import argparse
import sys

# ===== 配置 =====
UDP_PORT = 10832
TCP_PORT = 10833
BROADCAST_ADDR = "255.255.255.255"
NODE_ID = "node_001"


def log(msg):
    """带时间戳的日志"""
    print(f"[{time.strftime('%H:%M:%S')}] [ESP32模拟器] {msg}")


def discover_server(timeout=5):
    """通过 UDP 广播发现后端服务端 IP"""
    log(f"开始 UDP 广播发现服务端 (端口 {UDP_PORT})...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    # 绑定本地端口接收响应
    sock.bind(("", UDP_PORT))

    # 发送发现请求
    payload = json.dumps({"type": "discovery", "id": NODE_ID})
    sock.sendto(payload.encode(), (BROADCAST_ADDR, UDP_PORT))
    log(f"已发送发现广播: {payload}")

    # 等待响应
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode())
            log(f"收到 UDP 响应: {msg} from {addr}")

            if msg.get("type") == "config":
                server_ip = msg.get("ip")
                server_port = msg.get("port", TCP_PORT)
                log(f"✓ 发现服务端: {server_ip}:{server_port}")
                sock.close()
                return server_ip, server_port
    except socket.timeout:
        log("✗ UDP 发现超时，未收到响应")
        sock.close()
        return None, None


def start_tcp_client(server_ip, server_port, auto_ack=True, delay=0.5):
    """启动 TCP 客户端，连接后端服务端"""
    log(f"连接 TCP 服务端 {server_ip}:{server_port}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((server_ip, server_port))
        log(f"✓ TCP 已连接: {server_ip}:{server_port}")
        log("等待后端下发命令...")
        log("-" * 60)

        # 设置非阻塞接收
        sock.settimeout(1.0)

        while True:
            # 接收命令
            try:
                data = sock.recv(1024)
                if not data:
                    log("连接已断开")
                    break

                msg_str = data.decode().strip()
                if not msg_str:
                    continue

                log(f"← 收到命令: {msg_str}")

                try:
                    cmd_msg = json.loads(msg_str)
                except json.JSONDecodeError as e:
                    log(f"[错误] JSON 解析失败: {e}")
                    continue

                cmd = cmd_msg.get("cmd", "")
                seq = cmd_msg.get("seq", 0)

                # 模拟执行命令
                if cmd == "open_door":
                    log(f"  → [模拟] 继电器3吸合（开门键），延时50ms，释放")
                    ack = {"type": "ack", "cmd": "open_door", "status": "ok", "seq": seq}

                elif cmd == "close_door":
                    log(f"  → [模拟] 继电器4吸合（关门键），延时50ms，释放")
                    ack = {"type": "ack", "cmd": "close_door", "status": "ok", "seq": seq}

                elif cmd == "go_floor":
                    floor = cmd_msg.get("floor", 1)
                    log(f"  → [模拟] 红外发射去{floor}楼信号，延时，发停止信号")
                    ack = {"type": "ack", "cmd": "go_floor", "status": "ok", "floor": floor, "seq": seq}

                elif cmd == "status":
                    log(f"  → [模拟] 查询当前状态")
                    ack = {
                        "type": "ack",
                        "cmd": "status",
                        "status": "ok",
                        "floor": 3,
                        "temp": 25.5,
                        "humi": 60.0,
                        "seq": seq
                    }

                else:
                    log(f"  → [未知命令] {cmd}")
                    ack = {"type": "ack", "cmd": cmd, "status": "unknown", "seq": seq}

                # 回传 ACK
                if auto_ack:
                    if delay > 0:
                        time.sleep(delay)
                    ack_str = json.dumps(ack) + "\n"
                    sock.send(ack_str.encode())
                    log(f"→ 回传 ACK: {ack_str.strip()}")

                log("-" * 60)

            except socket.timeout:
                # 没有数据，继续等待
                continue

    except ConnectionRefusedError:
        log(f"✗ 连接被拒绝，请确认后端服务已启动 (端口 {server_port})")
    except KeyboardInterrupt:
        log("用户中断")
    except Exception as e:
        log(f"✗ 异常: {e}")
    finally:
        sock.close()
        log("TCP 连接已关闭")


def main():
    parser = argparse.ArgumentParser(description="电梯 ESP32 模拟器")
    parser.add_argument("--host", type=str, default=None,
                        help="直接指定后端 IP（跳过 UDP 发现）")
    parser.add_argument("--port", type=int, default=TCP_PORT,
                        help=f"后端 TCP 端口（默认 {TCP_PORT}）")
    parser.add_argument("--no-auto-ack", action="store_true",
                        help="禁用自动 ACK（手动模式）")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="收到命令后回传 ACK 的延迟秒数（默认 0.5）")
    args = parser.parse_args()

    print("=" * 60)
    print("  电梯 ESP32 模拟器（测试脚本）")
    print("=" * 60)

    server_ip = args.host
    server_port = args.port

    # 如果未指定 host，通过 UDP 发现
    if server_ip is None:
        server_ip, server_port = discover_server()
        if server_ip is None:
            print("\n未发现后端服务，请：")
            print("  1. 确认后端服务已启动")
            print("  2. 或用 --host 参数直接指定后端 IP")
            print("     例: python test_elevator_simulator.py --host 127.0.0.1")
            sys.exit(1)

    # 启动 TCP 客户端
    start_tcp_client(server_ip, server_port,
                     auto_ack=not args.no_auto_ack,
                     delay=args.delay)


if __name__ == "__main__":
    main()
