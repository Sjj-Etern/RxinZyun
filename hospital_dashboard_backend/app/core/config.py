import importlib.util

_spec_settings = importlib.util.find_spec("pydantic_settings")
_spec_pydantic = importlib.util.find_spec("pydantic")

if _spec_settings is not None:
    from pydantic_settings import BaseSettings, SettingsConfigDict
elif _spec_pydantic is not None:
    import pydantic as _pydantic
    _ver = getattr(_pydantic, "__version__", "")
    if _ver and _ver.split(".")[0] == "1":
        from pydantic import BaseSettings
    else:
        raise ImportError(
            "pydantic v2 is installed; please install 'pydantic-settings' (pip install pydantic-settings)."
        )
else:
    raise ImportError(
        "Neither 'pydantic' nor 'pydantic-settings' is installed. Install one of them."
    )


class Settings(BaseSettings):
    """
    hospital_new_demo 后端配置
    所有配置项都可以通过 .env 文件或环境变量覆盖
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False  # 环境变量名不区分大小写
    )

    # ===== 应用基础配置 =====
    app_name: str

    # ===== MySQL 数据库配置（直接连接）=====
    # 说明：大屏系统直接连接MySQL数据库，与HIS系统共享同一数据库
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_pass: str
    mysql_db: str

    # 兼容别名（部分代码使用 his_mysql_* 前缀）
    @property
    def his_mysql_host(self) -> str:
        return self.mysql_host

    @property
    def his_mysql_port(self) -> int:
        return self.mysql_port

    @property
    def his_mysql_user(self) -> str:
        return self.mysql_user

    @property
    def his_mysql_pass(self) -> str:
        return self.mysql_pass

    @property
    def his_mysql_db(self) -> str:
        return self.mysql_db

    # ===== 海康摄像头配置（RTSP） =====
    camera_host: str
    camera_port: int
    camera_user: str
    camera_password: str
    camera_stream_path: str

    # ===== 摄像头语音播报配置（ISAPI） =====
    camera_audio_port: int
    audio_id_start: int  # car_can_go - 车辆可以通行（任务启动）
    audio_id_end: int  # car_already_arrive - 车辆已到达（药单完成）
    audio_check_interval: int  # 语音播报端口检测间隔（秒）
    audio_connect_timeout: int  # 语音播报连接超时（秒）

    # ===== ROS WebSocket 配置 =====
    # 车1 配置
    car1_ws_host: str
    car1_ws_port: int
    car1_topic: str  # 车1 监听的ROS Topic（接收消息）
    car1_pose_topic: str = "/car01_pose"  # 车1 实时坐标 Topic（pose publisher 发布 "x,y" 字符串）
    car1_send_topic: str  # 车1 发送到ROS的Topic
    car1_send_msg_type: str  # 车1 发送消息的类型

    # 车2 配置
    car2_ws_host: str
    car2_ws_port: int
    car2_topic: str  # 车2 监听的ROS Topic（接收消息）
    car2_pose_topic: str = "/car02_pose"  # 车2 实时坐标 Topic（pose publisher 发布 "x,y" 字符串）
    car2_send_topic: str  # 车2 发送到ROS的Topic
    car2_send_msg_type: str  # 车2 发送消息的类型

    # 通用ROS配置
    ros_check_interval: int  # 周期检测间隔（秒）
    ros_connect_timeout: int  # 连接超时（秒）
    medicine_send_max_attempts: int = 15  # 药品 start/running 重发上限（超限停止发送，防无限重发）
    medicine_receipt_wait_timeout: int = 300  # 重发上限后静默等待回执的最长时间（秒），超时才放弃本处方

    # ===== 电梯控制配置 =====
    lift_across_delay: int  # 历史兼容字段；电梯到达后发送跨楼信号的延迟时间（秒）
    car2_signal_interval: int  # 车2 信号连续发送的重发间隔（秒）
    pharmacist_success_delay: int  # 节点3扫码复核完成 → 发送车2 pharmacist-success 的延迟（秒）
    nurse_success_delay: int  # 节点4扫码全部确认 → 发送车2 nurse-success 的延迟（秒）

    # ===== 电梯硬件 TCP 通信配置（与 elevator_access_control ESP32 通信）=====
    elevator_tcp_host: str  # TCP 服务端监听地址（监听所有网卡）
    elevator_tcp_port: int  # TCP 服务端端口（与 ESP32 的 TCP_PORT 一致）
    elevator_udp_port: int  # UDP 发现响应端口（与 ESP32 的 UDP_PORT 一致）
    elevator_cmd_timeout: float  # 命令 ACK 超时时间（秒）
    elevator_target_floor: int  # 目标楼层（1-5）
    elevator_door_open_delay: float  # 开门动作后等待时间（秒）
    elevator_door_close_delay: float  # 关门动作后等待时间（秒）
    elevator_go_floor_delay: float = 5  # 每层楼层移动等待时间（秒）
    elevator_floor_arrive_timeout: float  # 等待 ESP32 floor_arrived 上报的超时兜底（秒）
    elevator_across_to_go_floor_delay: float = 5  # 发 lift-across 后 → 触发电梯上楼的串行等待（秒，等车进梯）

    # ===== 向后兼容（旧字段名 → 映射到车1）=====
    @property
    def ros_ws_host(self) -> str:
        """向后兼容：ROS WebSocket 主机地址（映射到车1）"""
        return self.car1_ws_host

    @property
    def ros_ws_port(self) -> int:
        """向后兼容：ROS WebSocket 端口（映射到车1）"""
        return self.car1_ws_port

    @property
    def ros_topic(self) -> str:
        """向后兼容：监听的ROS Topic（映射到车1）"""
        return self.car1_topic

    @property
    def ros_send_topic(self) -> str:
        """向后兼容：发送到ROS的Topic（映射到车1）"""
        return self.car1_send_topic

    @property
    def ros_send_msg_type(self) -> str:
        """向后兼容：发送消息类型（映射到车1）"""
        return self.car1_send_msg_type

    def get_car_configs(self) -> list[dict]:
        """获取所有小车配置列表，方便统一遍历"""
        return [
            {
                "car_id": 1,
                "ws_host": self.car1_ws_host,
                "ws_port": self.car1_ws_port,
                "topic": self.car1_topic,
                "pose_topic": self.car1_pose_topic,
                "send_topic": self.car1_send_topic,
                "send_msg_type": self.car1_send_msg_type,
            },
            {
                "car_id": 2,
                "ws_host": self.car2_ws_host,
                "ws_port": self.car2_ws_port,
                "topic": self.car2_topic,
                "pose_topic": self.car2_pose_topic,
                "send_topic": self.car2_send_topic,
                "send_msg_type": self.car2_send_msg_type,
            },
        ]

    # ===== 机器人摄像头1（ROS webvideo_server） =====
    robot1_host: str
    robot1_port: int

    # ===== 机器人摄像头2 =====
    robot2_host: str
    robot2_port: int


settings = Settings()


def get_camera_rtsp_url() -> str:
    """获取海康摄像头 RTSP 地址"""
    return (
        f"rtsp://{settings.camera_user}:{settings.camera_password}@"
        f"{settings.camera_host}:{settings.camera_port}{settings.camera_stream_path}"
    )


def get_ros_ws_url(car_id: int = 1) -> str:
    """获取 ROS WebSocket 连接地址（支持指定小车编号）"""
    car_configs = settings.get_car_configs()
    for cfg in car_configs:
        if cfg["car_id"] == car_id:
            return f"ws://{cfg['ws_host']}:{cfg['ws_port']}"
    return f"ws://{settings.car1_ws_host}:{settings.car1_ws_port}"


def get_camera_audio_base_url() -> str:
    """获取摄像头语音播报 API 基础地址"""
    return f"http://{settings.camera_host}:{settings.camera_audio_port}"


def get_audio_trigger_url(audio_id: int) -> str:
    """获取摄像头语音触发 API 地址"""
    return (
        f"http://{settings.camera_host}:{settings.camera_audio_port}"
        f"/ISAPI/Event/triggers/notifications/AudioAlarm/{audio_id}/test?format=json"
    )
