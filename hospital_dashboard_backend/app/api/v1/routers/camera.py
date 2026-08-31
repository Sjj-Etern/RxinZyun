"""摄像头路由 - 三个摄像头流"""
import os
import threading
import time
import requests
import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_camera_rtsp_url, settings
from app.schemas.camera import CameraTestResponse, CameraUrlResponse

router = APIRouter()

ROBOT1_TOPIC = "/camera/color/image_raw"
ROBOT1_STREAM_URL = f"http://{settings.robot1_host}:{settings.robot1_port}/stream?topic={ROBOT1_TOPIC}"
ROBOT1_SNAPSHOT_URL = f"http://{settings.robot1_host}:{settings.robot1_port}/snapshot?topic={ROBOT1_TOPIC}"

ROBOT2_STREAM_URL = f"http://{settings.robot2_host}:{settings.robot2_port}/video_feed"
UPSTREAM_STREAM_TIMEOUT = (5, 15)
STREAM_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "X-Accel-Buffering": "no",
}

# RTSP 使用 TCP，并限制底层打开/读取阻塞时间。必须在首次 VideoCapture 前设置。
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000",
)

_rtsp_condition = threading.Condition()
_rtsp_worker_lock = threading.Lock()
_rtsp_worker = None
_rtsp_frame = None
_rtsp_frame_id = 0
_rtsp_online = False


def _mjpeg_frame(jpeg_data: bytes) -> bytes:
    return (b'--mjpeg\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Content-length: ' + str(len(jpeg_data)).encode() + b'\r\n\r\n'
            + jpeg_data + b'\r\n')


@router.get("/url", response_model=CameraUrlResponse)
def camera_url():
    return {"rtsp_url": get_camera_rtsp_url()}


@router.get("/test", response_model=CameraTestResponse)
def camera_test():
    _ensure_rtsp_worker()
    with _rtsp_condition:
        connected = _rtsp_condition.wait_for(lambda: _rtsp_online, timeout=8)
    if not connected:
        raise HTTPException(status_code=500, detail="无法连接摄像头")
    return {"ok": True, "message": "摄像头连接正常"}


def _set_rtsp_offline():
    global _rtsp_frame, _rtsp_online
    with _rtsp_condition:
        _rtsp_frame = None
        _rtsp_online = False
        _rtsp_condition.notify_all()


def _rtsp_capture_loop():
    """保持唯一的 RTSP 连接，持续重连并发布最新 JPEG 帧。"""
    global _rtsp_frame, _rtsp_frame_id, _rtsp_online

    retry_delay = 1.0
    while True:
        cap = None
        try:
            cap = cv2.VideoCapture(get_camera_rtsp_url(), cv2.CAP_FFMPEG)
            if not cap.isOpened():
                raise RuntimeError("无法打开 RTSP 流")

            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            consecutive_failures = 0

            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        raise RuntimeError("RTSP 连续读取失败")
                    time.sleep(0.1)
                    continue

                consecutive_failures = 0
                encoded, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if not encoded:
                    continue

                with _rtsp_condition:
                    _rtsp_frame = buffer.tobytes()
                    _rtsp_frame_id += 1
                    _rtsp_online = True
                    _rtsp_condition.notify_all()

                retry_delay = 1.0
                time.sleep(0.03)
        except Exception as exc:
            _set_rtsp_offline()
            print(f"[摄像头] RTSP 连接中断，{retry_delay:.0f}秒后重试: {exc}")
        finally:
            if cap is not None:
                cap.release()

        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 10.0)


def _ensure_rtsp_worker():
    global _rtsp_worker
    with _rtsp_worker_lock:
        if _rtsp_worker is None or not _rtsp_worker.is_alive():
            _rtsp_worker = threading.Thread(
                target=_rtsp_capture_loop,
                name="rtsp-camera-capture",
                daemon=True,
            )
            _rtsp_worker.start()


@router.get("/opencv")
def opencv_stream():
    """RTSP摄像头 - OpenCV转MJPEG流

    稳定性策略：
    - 后端只建立一个常驻 RTSP 连接，避免多个浏览器重复占用摄像头连接数
    - 掉线后无限重连，成功后所有前端连接自动收到最新画面
    - 已经出过画面的客户端在掉线时结束响应，让前端及时切换备用视频
    """
    _ensure_rtsp_worker()

    def frame_generator():
        last_frame_id = None
        has_streamed = False
        while True:
            with _rtsp_condition:
                _rtsp_condition.wait_for(
                    lambda: (
                        _rtsp_online
                        and _rtsp_frame_id != last_frame_id
                    ) or (has_streamed and not _rtsp_online),
                    timeout=2,
                )
                if not _rtsp_online or _rtsp_frame is None:
                    if has_streamed:
                        return
                    continue
                if _rtsp_frame_id == last_frame_id:
                    continue
                jpeg_data = _rtsp_frame
                last_frame_id = _rtsp_frame_id

            has_streamed = True
            yield _mjpeg_frame(jpeg_data)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=mjpeg",
        headers=STREAM_HEADERS,
    )


@router.get("/robot")
def robot_camera_stream():
    """机器人摄像头1 - 代理ROS webvideo_server流"""
    try:
        resp = requests.get(
            ROBOT1_STREAM_URL,
            stream=True,
            timeout=UPSTREAM_STREAM_TIMEOUT,
        )
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', 'multipart/x-mixed-replace; boundary=frame')

        def stream_generator():
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        return StreamingResponse(
            stream_generator(), media_type=content_type, headers=STREAM_HEADERS
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"机器人摄像头1流获取失败: {str(e)}")


@router.get("/robot2")
def robot2_camera_stream():
    """机器人摄像头2 - 代理远程视频流"""
    try:
        resp = requests.get(
            ROBOT2_STREAM_URL,
            stream=True,
            timeout=UPSTREAM_STREAM_TIMEOUT,
        )
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', 'multipart/x-mixed-replace; boundary=frame')

        def stream_generator():
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        return StreamingResponse(
            stream_generator(), media_type=content_type, headers=STREAM_HEADERS
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"机器人摄像头2流获取失败: {str(e)}")
