"""
电梯控制服务（TCP 服务端 + UDP 发现响应）

与 elevator_access_control ESP32 通过 TCP 长连接通信。
ESP32 作为 TCP 客户端主动连接本服务端。

通信协议（JSON + 换行符 \\n 作为消息边界）：
  后端 → ESP32 命令（带序列号 seq）：
    {"cmd":"open_door","seq":1}\\n
    {"cmd":"close_door","seq":2}\\n
    {"cmd":"go_floor","floor":5,"seq":3}\\n
    {"cmd":"status","seq":4}\\n

  ESP32 → 后端 ACK（回传相同 seq）：
    {"type":"ack","cmd":"open_door","status":"ok","seq":1}\\n
    {"type":"ack","cmd":"go_floor","status":"ok","floor":5,"seq":3}\\n
    {"type":"ack","cmd":"status","status":"ok","floor":5,"temp":25,"humi":60,"seq":4}\\n

UDP 发现协议（与 ESP32 的 udp_broadcast.c 对接）：
  ESP32 → 后端（广播）:
    {"type":"discovery","id":"node_001"}
  后端 → ESP32（单播响应）:
    {"type":"config","ip":"后端IP","port":10833}

使用方式：
  1. 启动时调用 start_elevator_server() 拉起 TCP 服务端
  2. 通过 get_elevator_controller() 获取单例
  3. 调用 send_open_door() / send_close_door() / send_go_floor() 发送命令
  4. 每条命令会阻塞等待 ESP32 回传 ACK（带超时）
"""
import asyncio
import json
import logging
import socket
import time
from datetime import datetime
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局单例
_controller: Optional["ElevatorController"] = None
_udp_task: Optional[asyncio.Task] = None


def _ts() -> str:
    """当前时间戳（精确到毫秒）"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class ElevatorController:
    """
    电梯控制器（TCP 服务端）

    等待 ESP32 主动连接，连接后可通过 send_* 方法下发命令。
    每条命令都会等待 ESP32 回传 ACK 才返回，超时抛出 asyncio.TimeoutError。
    """

    def __init__(self, host: str, port: int, cmd_timeout: float = 10.0):
        self.host = host
        self.port = port
        self.cmd_timeout = cmd_timeout

        self._server: Optional[asyncio.AbstractServer] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._client_lock = asyncio.Lock()

        # ACK 等待机制
        self._pending_ack: Optional[asyncio.Future] = None
        self._ack_lock = asyncio.Lock()

        # 命令序列号（递增，用于日志追溯）
        self._cmd_seq: int = 0

        # 电梯状态（由 ESP32 上报）
        self.elevator_state: Dict[str, Any] = {
            "connected": False,
            "client_addr": None,
            "last_ack": None,
            "last_status": None,
            "cmd_count": 0,
        }

    def _log_tag(self):
        return "[Elevator]"

    # ===== TCP 服务端 =====

    async def start_server(self) -> None:
        """启动 TCP 服务端，等待 ESP32 连接"""
        tag = self._log_tag()
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )

        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        print(f"[{_ts()}] {tag} TCP 服务端已启动，监听: {addrs}")
        print(f"[{_ts()}] {tag} 等待 ESP32 连接...")
        logger.info(f"电梯 TCP 服务端启动，监听 {addrs}")

    async def stop_server(self) -> None:
        """停止 TCP 服务端"""
        tag = self._log_tag()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        if self._server:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

        self.elevator_state["connected"] = False
        print(f"[{_ts()}] {tag} TCP 服务端已停止")

    # ===== 客户端连接处理 =====

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """处理 ESP32 连接"""
        tag = self._log_tag()
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}"
        print(f"[{_ts()}] {tag} {'='*56}")
        print(f"[{_ts()}] {tag} ESP32 已连接: {peer_str}")
        print(f"[{_ts()}] {tag} {'='*56}")
        logger.info(f"ESP32 电梯控制器已连接: {peer}")

        # 同一时间只允许一个 ESP32 连接
        async with self._client_lock:
            if self._writer is not None:
                # 断开旧连接
                try:
                    old_peer = self._writer.get_extra_info("peername")
                    old_peer_str = f"{old_peer[0]}:{old_peer[1]}" if old_peer else "unknown"
                    print(f"[{_ts()}] {tag} 断开旧连接: {old_peer_str}")
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass

            self._reader = reader
            self._writer = writer
            self.elevator_state["connected"] = True
            self.elevator_state["client_addr"] = peer_str

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue

                print(f"[{_ts()}] {tag} RECV ← {peer_str}: {line_str}")
                logger.info(f"ESP32 消息: {line_str}")

                try:
                    msg = json.loads(line_str)
                    await self._handle_esp32_message(msg, peer_str)
                except json.JSONDecodeError as e:
                    print(f"[{_ts()}] {tag} [警告] JSON 解析失败: {e}, 原始: {line_str}")
                    logger.warning(f"JSON 解析失败: {e}, 原始: {line_str}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[{_ts()}] {tag} [错误] 连接异常: {e}")
            logger.error(f"ESP32 连接异常: {e}", exc_info=True)
        finally:
            async with self._client_lock:
                if self._writer is writer:
                    self._writer = None
                    self._reader = None
                    self.elevator_state["connected"] = False
                    self.elevator_state["client_addr"] = None

            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

            print(f"[{_ts()}] {tag} ESP32 已断开: {peer_str}")
            logger.info(f"ESP32 电梯控制器已断开: {peer}")

    async def _handle_esp32_message(self, msg: dict, peer_str: str) -> None:
        """处理 ESP32 上报的消息（ACK / 状态）"""
        tag = self._log_tag()
        msg_type = msg.get("type", "")
        seq = msg.get("seq", "?")

        if msg_type == "ack":
            # 命令确认
            self.elevator_state["last_ack"] = msg
            cmd = msg.get("cmd", "?")
            status = msg.get("status", "?")
            extra = ""
            if "floor" in msg:
                extra += f", floor={msg['floor']}"
            if "temp" in msg:
                extra += f", temp={msg['temp']}°C"
            if "humi" in msg:
                extra += f", humi={msg['humi']}%"

            print(f"[{_ts()}] {tag} ACK  #{seq}: cmd={cmd}, status={status}{extra}")

            async with self._ack_lock:
                if self._pending_ack and not self._pending_ack.done():
                    self._pending_ack.set_result(msg)
                else:
                    print(f"[{_ts()}] {tag} [警告] 收到未匹配的 ACK #{seq}: {msg}")

        elif msg_type == "status":
            # 电梯状态上报
            self.elevator_state["last_status"] = msg
            print(f"[{_ts()}] {tag} STATUS #{seq}: floor={msg.get('floor')}, temp={msg.get('temp')}°C, humi={msg.get('humi')}%")

        else:
            print(f"[{_ts()}] {tag} [警告] 未知消息类型: {msg}")

    # ===== 命令发送 =====

    async def _send_command(self, cmd: dict) -> dict:
        """
        发送命令并等待 ACK
        返回 ESP32 回传的 ACK 消息
        超时抛出 asyncio.TimeoutError
        未连接抛出 RuntimeError
        """
        tag = self._log_tag()

        if self._writer is None:
            print(f"[{_ts()}] {tag} [错误] ESP32 未连接，无法发送命令: {cmd}")
            raise RuntimeError("ESP32 未连接，无法发送命令")

        # 分配序列号
        self._cmd_seq += 1
        seq = self._cmd_seq
        cmd["seq"] = seq
        self.elevator_state["cmd_count"] = seq

        cmd_str = json.dumps(cmd, ensure_ascii=False)
        cmd_json = cmd_str + "\n"
        peer_str = self.elevator_state.get("client_addr", "?")

        async with self._ack_lock:
            self._pending_ack = asyncio.get_event_loop().create_future()

        t0 = time.time()
        print(f"[{_ts()}] {tag} SEND #{seq} → {peer_str}: {cmd_str}")
        logger.info(f"发送电梯命令 #{seq}: {cmd_str}")
        self._writer.write(cmd_json.encode("utf-8"))
        await self._writer.drain()

        try:
            ack = await asyncio.wait_for(self._pending_ack, timeout=self.cmd_timeout)
            duration_ms = int((time.time() - t0) * 1000)
            print(f"[{_ts()}] {tag} DONE #{seq}: cmd={cmd.get('cmd')}, duration={duration_ms}ms")
            return ack
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - t0) * 1000)
            print(f"[{_ts()}] {tag} TIMEOUT #{seq}: cmd={cmd.get('cmd')}, {duration_ms}ms 无 ACK")
            logger.error(f"电梯命令超时 #{seq}: {cmd_str}")
            raise
        finally:
            async with self._ack_lock:
                self._pending_ack = None

    async def send_open_door(self) -> dict:
        """发送开门命令"""
        return await self._send_command({"cmd": "open_door"})

    async def send_close_door(self) -> dict:
        """发送关门命令"""
        return await self._send_command({"cmd": "close_door"})

    async def send_go_floor(self, floor: int) -> dict:
        """发送去指定楼层命令（1-5）"""
        if not 1 <= floor <= 5:
            raise ValueError(f"楼层必须在 1-5 之间，收到: {floor}")
        return await self._send_command({"cmd": "go_floor", "floor": floor})

    async def send_status_query(self) -> dict:
        """查询电梯当前状态"""
        return await self._send_command({"cmd": "status"})

    # ===== 状态查询 =====

    def is_connected(self) -> bool:
        """ESP32 是否已连接"""
        return self._writer is not None

    def get_state(self) -> dict:
        """获取电梯控制器状态"""
        return {
            "connected": self.is_connected(),
            "client_addr": self.elevator_state["client_addr"],
            "server_addr": f"{self.host}:{self.port}",
            "last_ack": self.elevator_state["last_ack"],
            "last_status": self.elevator_state["last_status"],
            "cmd_count": self.elevator_state["cmd_count"],
        }


# ===== 单例管理 =====

def get_elevator_controller() -> ElevatorController:
    """获取电梯控制器单例"""
    global _controller
    if _controller is None:
        _controller = ElevatorController(
            host=settings.elevator_tcp_host,
            port=settings.elevator_tcp_port,
            cmd_timeout=settings.elevator_cmd_timeout,
        )
    return _controller


async def start_elevator_server() -> None:
    """启动电梯 TCP 服务端 + UDP 发现响应（在 FastAPI lifespan 中调用）"""
    controller = get_elevator_controller()
    await controller.start_server()

    # 启动 UDP 发现响应
    global _udp_task
    _udp_task = asyncio.create_task(_udp_discovery_responder())
    print(f"[{_ts()}] [Elevator UDP] 发现响应服务已启动 (端口 {settings.elevator_udp_port})")


async def stop_elevator_server() -> None:
    """停止电梯 TCP 服务端 + UDP 发现响应"""
    global _controller, _udp_task

    if _udp_task is not None:
        _udp_task.cancel()
        try:
            await _udp_task
        except asyncio.CancelledError:
            pass
        _udp_task = None

    if _controller is not None:
        await _controller.stop_server()


def _get_local_ip_for(target_ip: str) -> str:
    """获取能到达目标 IP 的本机 IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


async def _udp_discovery_responder() -> None:
    """
    UDP 发现响应任务（使用 asyncio.DatagramProtocol，Python 3.10 兼容）
    监听 ESP32 的发现广播，回复后端 TCP 服务端地址
    与 ESP32 的 udp_broadcast.c 对接
    """
    tag = "[Elevator UDP]"
    udp_port = settings.elevator_udp_port

    class DiscoveryProtocol(asyncio.DatagramProtocol):
        """UDP 发现协议处理器"""

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            msg_str = data.decode("utf-8", errors="ignore").strip()
            try:
                msg = json.loads(msg_str)
            except json.JSONDecodeError:
                print(f"[{_ts()}] {tag} [警告] UDP 收到非 JSON: {msg_str} from {addr}")
                return

            if msg.get("type") == "discovery":
                node_id = msg.get("id", "unknown")
                local_ip = _get_local_ip_for(addr[0])
                tcp_port = settings.elevator_tcp_port

                response = json.dumps({
                    "type": "config",
                    "ip": local_ip,
                    "port": tcp_port
                })

                self.transport.sendto(response.encode(), addr)
                print(f"[{_ts()}] {tag} RECV 发现请求 from {addr[0]}:{addr[1]} (node={node_id})")
                print(f"[{_ts()}] {tag} SEND 发现响应 → {addr[0]}:{addr[1]}: {{\"ip\":\"{local_ip}\",\"port\":{tcp_port}}}")
                logger.info(f"响应电梯发现: node={node_id}, addr={addr}, ip={local_ip}:{tcp_port}")

    loop = asyncio.get_event_loop()

    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(),
        local_addr=("0.0.0.0", udp_port),
        allow_broadcast=True,
    )

    print(f"[{_ts()}] {tag} 监听发现广播: 端口 {udp_port}")
    logger.info(f"电梯 UDP 发现响应启动，端口 {udp_port}")

    try:
        # 永久等待，直到被取消
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        print(f"[{_ts()}] {tag} 发现响应服务已停止")
    finally:
        transport.close()
