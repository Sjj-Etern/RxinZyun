"""机器人实时坐标 API

返回两辆小车在 ROS map 坐标系下的实时坐标（米）。
数据源：car01_pose_publisher.py / car02_pose_publisher.py 通过 rosbridge 订阅。
"""
from fastapi import APIRouter

from app.services.ros_listener import _listeners

router = APIRouter()


@router.get("/robot/pose")
async def get_robot_pose():
    """
    返回两辆小车的实时坐标（map 坐标系，米）

    响应示例：
    {
      "car1": {"x": 1.234, "y": 0.567, "ts": "2026-...", "listener_state": "connected"},
      "car2": {"x": -0.456, "y": -0.890, "ts": "2026-...", "listener_state": "connected"}
    }

    若 ROS 未连接 / 未发布，x、y 为 null。
    listener_state: stopped（未启动）/ connecting（连接中）/ connected（已连接）/ disconnected（断开）
    """
    result = {}
    for car_id, listener in _listeners.items():
        result[f"car{car_id}"] = listener.get_pose()
    return result
