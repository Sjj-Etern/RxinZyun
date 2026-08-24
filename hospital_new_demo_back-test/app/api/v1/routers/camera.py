"""摄像头路由 - 三个摄像头流"""
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


def _mjpeg_frame(jpeg_data: bytes) -> bytes:
    return (b'--mjpeg\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Content-length: ' + str(len(jpeg_data)).encode() + b'\r\n\r\n'
            + jpeg_data + b'\r\n')


def _create_placeholder_image(text: str) -> bytes:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = [15, 23, 42]
    cv2.rectangle(img, (20, 20), (620, 460), (51, 65, 85), 2)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1.0, 2)[0]
    text_x = (640 - text_size[0]) // 2
    text_y = (480 + text_size[1]) // 2
    cv2.putText(img, text, (text_x, text_y), font, 1.0, (148, 163, 184), 2)
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes()


@router.get("/url", response_model=CameraUrlResponse)
def camera_url():
    return {"rtsp_url": get_camera_rtsp_url()}


@router.get("/test", response_model=CameraTestResponse)
def camera_test():
    rtsp_url = get_camera_rtsp_url()
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    time.sleep(0.5)
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise HTTPException(status_code=500, detail="无法连接摄像头")
    return {"ok": True, "message": "摄像头连接正常"}


@router.get("/opencv")
def opencv_stream():
    """RTSP摄像头 - OpenCV转MJPEG流（限制重连次数，失败后快速结束）"""
    rtsp_url = get_camera_rtsp_url()
    offline_img = _create_placeholder_image("Camera Offline")

    def frame_generator():
        cap = None
        max_total_reconnects = 2  # 最多重连2次
        reconnect_count = 0
        max_consecutive_failures = 3  # 连续失败3次放弃
        consecutive_failures = 0

        while True:
            # 限制重连总次数
            if reconnect_count >= max_total_reconnects:
                # 返回一帧离线图后结束流，让前端触发 @error 切回备用视频
                yield _mjpeg_frame(offline_img)
                time.sleep(0.5)
                return  # 结束生成器

            # 尝试连接
            if cap is None:
                try:
                    cap = cv2.VideoCapture(rtsp_url)
                    if not cap.isOpened():
                        cap = None
                        raise Exception("无法打开RTSP流")
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FPS, 15)
                    consecutive_failures = 0
                    time.sleep(0.3)
                except Exception:
                    cap = None
                    reconnect_count += 1
                    # 短暂等待后重试（1秒）
                    time.sleep(1.0)
                    continue

            # 读取帧
            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        if cap is not None:
                            cap.release()
                            cap = None
                        consecutive_failures = 0
                        reconnect_count += 1
                        time.sleep(0.5)
                    else:
                        time.sleep(0.1)
                    continue

                # 成功读取帧
                consecutive_failures = 0
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, 80]
                ret, buffer = cv2.imencode('.jpg', frame, encode_params)
                if ret:
                    yield _mjpeg_frame(buffer.tobytes())
                time.sleep(0.05)

            except Exception:
                if cap is not None:
                    cap.release()
                    cap = None
                consecutive_failures = 0
                reconnect_count += 1
                time.sleep(0.5)

        if cap is not None:
            cap.release()

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=mjpeg")


@router.get("/robot")
def robot_camera_stream():
    """机器人摄像头1 - 代理ROS webvideo_server流"""
    try:
        resp = requests.get(ROBOT1_STREAM_URL, stream=True, timeout=3)
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', 'multipart/x-mixed-replace; boundary=frame')

        def stream_generator():
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        return StreamingResponse(stream_generator(), media_type=content_type)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"机器人摄像头1流获取失败: {str(e)}")


@router.get("/robot2")
def robot2_camera_stream():
    """机器人摄像头2 - 代理远程视频流"""
    try:
        resp = requests.get(ROBOT2_STREAM_URL, stream=True, timeout=3)
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', 'multipart/x-mixed-replace; boundary=frame')

        def stream_generator():
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        return StreamingResponse(stream_generator(), media_type=content_type)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"机器人摄像头2流获取失败: {str(e)}")
