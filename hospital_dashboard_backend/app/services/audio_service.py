"""
摄像头语音播报服务
通过海康威视 ISAPI 接口触发摄像头播放语音
支持周期性检测端口可达性、自动重连
"""
import socket
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    requests = None
    HTTPDigestAuth = None

from app.core.config import settings, get_audio_trigger_url

logger = logging.getLogger(__name__)

_direct_http = requests.Session() if requests is not None else None
if _direct_http is not None:
    # The camera is on the hospital LAN; never route ISAPI calls through the
    # workstation's HTTP(S) proxy.
    _direct_http.trust_env = False


# 全局状态存储（供 API 查询）
_audio_state: Dict[str, Any] = {
    "camera_reachable": False,
    "last_check_time": None,
    "last_play_time": None,
    "last_play_status": None,
    "last_audio_id": None,
}


def get_audio_state() -> Dict[str, Any]:
    """获取当前语音播报状态（供 API 使用）"""
    return _audio_state.copy()


def check_camera_reachable(host: str, port: int, timeout: int = 5) -> bool:
    """检测摄像头 HTTP API 端口是否可达"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"摄像头端口检测失败: {e}")
        return False


async def play_audio_async(audio_id: int) -> bool:
    """
    异步播放指定 ID 的语音

    Args:
        audio_id: 语音文件 ID（15 = car_can_go）

    Returns:
        bool: 是否播放成功
    """
    if requests is None:
        logger.error("requests 库未安装，无法播放语音")
        return False

    # 先检测端口可达性
    reachable = check_camera_reachable(
        settings.camera_host,
        settings.camera_audio_port,
        settings.audio_connect_timeout
    )

    _audio_state["camera_reachable"] = reachable
    _audio_state["last_check_time"] = datetime.now().isoformat()

    if not reachable:
        logger.warning(f"摄像头 HTTP API 端口不可达: {settings.camera_host}:{settings.camera_audio_port}")
        _audio_state["last_play_status"] = "failed_port_unreachable"
        return False

    # 端口可达，尝试播放语音
    url = get_audio_trigger_url(audio_id)
    auth = HTTPDigestAuth(settings.camera_user, settings.camera_password)
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive"
    }

    logger.info(f"正在播放语音: audio_id={audio_id}, URL={url}")

    try:
        # 在 async 函数中调用同步 requests，使用 run_in_executor
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _direct_http.put(
                url,
                auth=auth,
                headers=headers,
                timeout=settings.audio_connect_timeout
            )
        )

        if response.status_code == 200:
            logger.info(f"✅ 语音播放成功: audio_id={audio_id}")
            _audio_state["last_play_time"] = datetime.now().isoformat()
            _audio_state["last_play_status"] = "success"
            _audio_state["last_audio_id"] = audio_id
            return True
        else:
            logger.warning(f"语音播放失败: HTTP {response.status_code}, {response.text}")
            _audio_state["last_play_status"] = f"failed_http_{response.status_code}"
            return False

    except requests.exceptions.Timeout:
        logger.error("语音播放超时")
        _audio_state["last_play_status"] = "failed_timeout"
        return False

    except requests.exceptions.RequestException as e:
        logger.error(f"语音播放请求错误: {e}")
        _audio_state["last_play_status"] = f"failed_request_error"
        return False


def play_audio_sync(audio_id: int) -> bool:
    """
    同步播放指定 ID 的语音（用于测试接口）

    Args:
        audio_id: 语音文件 ID

    Returns:
        bool: 是否播放成功
    """
    if requests is None:
        logger.error("requests 库未安装，无法播放语音")
        return False

    # 先检测端口可达性
    reachable = check_camera_reachable(
        settings.camera_host,
        settings.camera_audio_port,
        settings.audio_connect_timeout
    )

    _audio_state["camera_reachable"] = reachable
    _audio_state["last_check_time"] = datetime.now().isoformat()

    if not reachable:
        logger.warning(f"摄像头 HTTP API 端口不可达: {settings.camera_host}:{settings.camera_audio_port}")
        _audio_state["last_play_status"] = "failed_port_unreachable"
        return False

    # 端口可达，尝试播放语音
    url = get_audio_trigger_url(audio_id)
    auth = HTTPDigestAuth(settings.camera_user, settings.camera_password)
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive"
    }

    logger.info(f"正在播放语音: audio_id={audio_id}, URL={url}")

    try:
        response = _direct_http.put(
            url,
            auth=auth,
            headers=headers,
            timeout=settings.audio_connect_timeout
        )

        if response.status_code == 200:
            logger.info(f"✅ 语音播放成功: audio_id={audio_id}")
            _audio_state["last_play_time"] = datetime.now().isoformat()
            _audio_state["last_play_status"] = "success"
            _audio_state["last_audio_id"] = audio_id
            return True
        else:
            logger.warning(f"语音播放失败: HTTP {response.status_code}, {response.text}")
            _audio_state["last_play_status"] = f"failed_http_{response.status_code}"
            return False

    except requests.exceptions.Timeout:
        logger.error("语音播放超时")
        _audio_state["last_play_status"] = "failed_timeout"
        return False

    except requests.exceptions.RequestException as e:
        logger.error(f"语音播放请求错误: {e}")
        _audio_state["last_play_status"] = f"failed_request_error"
        return False


async def trigger_audio_on_task_confirm() -> bool:
    """
    任务确认时触发语音播报

    当收到 running_started 时，播放 audio_id=15 (car_can_go)

    Returns:
        bool: 是否播放成功
    """
    logger.info("🎵 任务确认 - 触发语音播报")
    return await play_audio_async(settings.audio_id_start)
