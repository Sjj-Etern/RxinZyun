import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.v1.routers.camera import router as camera_router
from app.api.v1.routers.sensors import router as sensors_router
from app.api.v1.routers.agent import router as agent_router
from app.api.v1.routers.data import router as data_router
from app.api.v1.routers.prescription import router as prescription_router
from app.api.v1.routers.workflow import router as workflow_router
from app.api.v1.routers.robot import router as robot_router
from app.schemas.sensor import DHT11DataCreate, SensorDataCreate
from app.db.session import SessionLocal, engine
from app.db import models, crud
from app.services.ros_listener import create_listener, _listeners as ros_listeners
from app.services.his_sender import create_sender, _senders as his_senders
from app.services.elevator_control import (
    start_elevator_server,
    stop_elevator_server,
    get_elevator_controller,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# 后台任务列表
_background_tasks: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("Hospital New Demo Back 服务启动（双车模式）")
    print("=" * 60)

    # ===== 创建数据库表 =====
    try:
        models.Base.metadata.create_all(bind=engine)
        print("[成功] 数据库表创建完成")
        logger.info("数据库表创建完成")
    except Exception as e:
        print(f"[警告] 数据库表创建失败: {e}")
        logger.warning(f"数据库表创建失败: {e}")

    # ===== 启动电梯 TCP 服务端（与 elevator_access_control ESP32 通信）=====
    # 注意：必须在小车服务之前启动，因为 ros_listener 中的 check_port_reachable()
    # 是同步阻塞函数，会阻塞事件循环，导致 lifespan 的 yield 无法执行
    try:
        await start_elevator_server()
        print(f"[成功] 电梯 TCP 服务端已启动 (端口 {settings.elevator_tcp_port})")
    except Exception as e:
        print(f"[警告] 电梯 TCP 服务端启动失败: {e}")
        logger.warning(f"电梯 TCP 服务端启动失败: {e}")

    # ===== 启动所有小车服务 =====
    car_configs = settings.get_car_configs()

    for cfg in car_configs:
        car_id = cfg["car_id"]
        print(f"\n{'='*60}")
        print(f"[启动] 小车 {car_id} 服务")
        print(f"{'='*60}")

        # 创建 HIS Sender 实例
        sender = create_sender(
            car_id=car_id,
            ws_host=cfg["ws_host"],
            ws_port=cfg["ws_port"],
            send_topic=cfg["send_topic"],
            send_msg_type=cfg["send_msg_type"],
        )
        sender_task = asyncio.create_task(sender.start())
        _background_tasks.append(sender_task)
        print(f"[成功] 小车{car_id} HIS Sender 已启动")

        # 创建 ROS Listener 实例
        listener = create_listener(
            car_id=car_id,
            ws_host=cfg["ws_host"],
            ws_port=cfg["ws_port"],
            topic=cfg["topic"],
            send_topic=cfg["send_topic"],
            send_msg_type=cfg["send_msg_type"],
            pose_topic=cfg.get("pose_topic", ""),
        )
        listener_task = asyncio.create_task(listener.start())
        _background_tasks.append(listener_task)
        print(f"[成功] 小车{car_id} ROS Listener 已启动")

    print(f"\n{'='*60}")
    print(f"服务启动完成，共 {len(car_configs)} 辆小车")
    print(f"后台任务数: {len(_background_tasks)}")
    print(f"{'='*60}")

    yield

    # 关闭时：取消所有后台任务
    print("\n[停止] 正在关闭所有服务...")

    # 停止电梯 TCP 服务端
    try:
        await stop_elevator_server()
    except Exception as e:
        print(f"[警告] 电梯 TCP 服务端停止失败: {e}")

    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[警告] 任务取消失败: {e}")

    # 停止所有 HIS Sender
    for sender in his_senders.values():
        try:
            await sender.stop()
        except Exception as e:
            print(f"[警告] HIS Sender 停止失败: {e}")

    _background_tasks.clear()
    print("=" * 60)
    print("服务已关闭")
    print("=" * 60)


app = FastAPI(
    title="Hospital New Demo API",
    version="1.0.0",
    description="A FastAPI backend for sensors, AI agent, database data, and camera streaming.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(camera_router, prefix="/api/v1/camera", tags=["camera"])
app.include_router(sensors_router, prefix="/api/v1/sensors", tags=["sensors"])
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(data_router, prefix="/api/v1/data", tags=["data"])
app.include_router(prescription_router, prefix="/api/v1", tags=["prescription"])
app.include_router(workflow_router, prefix="/api/v1", tags=["workflow"])
app.include_router(robot_router, prefix="/api/v1", tags=["robot"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/api/dht11", status_code=201, tags=["dht11"])
def receive_dht11_data_direct(data: DHT11DataCreate, db: Session = Depends(get_db)):
    print("=" * 60)
    print("[DHT11] 接收到传感器数据")
    print("=" * 60)
    print(f"[DHT11]   温度: {data.temp}°C")
    print(f"[DHT11]   湿度: {data.humi}%")
    
    try:
        temp_record = crud.create_sensor_record(
            db=db,
            sensor_data=SensorDataCreate(
                name="temperature",
                value=data.temp,
                unit="°C"
            )
        )
        print(f"[DHT11] ✓ 温度数据已存储 (ID: {temp_record.id})")
        
        humi_record = crud.create_sensor_record(
            db=db,
            sensor_data=SensorDataCreate(
                name="humidity",
                value=data.humi,
                unit="%"
            )
        )
        print(f"[DHT11] ✓ 湿度数据已存储 (ID: {humi_record.id})")
        print("=" * 60)
        
        return {
            "status": "success",
            "temperature_id": temp_record.id,
            "humidity_id": humi_record.id
        }
    except Exception as e:
        print(f"[DHT11] ✗ 数据存储失败: {e}")
        print("=" * 60)
        raise


@app.websocket("/api/dht11/wifi")
async def websocket_dht11(websocket: WebSocket):
    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else 0
    print("=" * 60)
    print("[DHT11-WiFi] ESP32 设备已连接")
    print(f"[DHT11-WiFi]   客户端: {client_host}:{client_port}")
    print(f"[DHT11-WiFi]   连接时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    logger.info(f"[DHT11-WiFi] ESP32 设备已连接: {client_host}:{client_port}")

    try:
        while True:
            message = await websocket.receive_text()

            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                print(f"[DHT11-WiFi] ✗ JSON解析失败: {e}")
                print(f"[DHT11-WiFi]   原始数据: {message}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid JSON format"
                })
                continue

            temp = data.get("temp")
            humi = data.get("humi")

            if temp is None or humi is None:
                print(f"[DHT11-WiFi] ✗ 数据字段缺失: {data}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Missing 'temp' or 'humi' field"
                })
                continue

            try:
                temp = float(temp)
                humi = float(humi)
            except (TypeError, ValueError) as e:
                print(f"[DHT11-WiFi] ✗ 数据类型转换失败: {e}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid data type for 'temp' or 'humi'"
                })
                continue

            print("-" * 60)
            print(f"[DHT11-WiFi] 接收到传感器数据")
            print(f"[DHT11-WiFi]   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[DHT11-WiFi]   温度: {temp}°C")
            print(f"[DHT11-WiFi]   湿度: {humi}%")

            db = SessionLocal()
            try:
                temp_record = crud.create_sensor_record(
                    db=db,
                    sensor_data=SensorDataCreate(
                        name="temperature",
                        value=temp,
                        unit="°C"
                    )
                )
                humi_record = crud.create_sensor_record(
                    db=db,
                    sensor_data=SensorDataCreate(
                        name="humidity",
                        value=humi,
                        unit="%"
                    )
                )
                print(f"[DHT11-WiFi] ✓ 温度数据已存储 (ID: {temp_record.id})")
                print(f"[DHT11-WiFi] ✓ 湿度数据已存储 (ID: {humi_record.id})")
                print("-" * 60)

                await websocket.send_json({
                    "status": "success",
                    "temperature_id": temp_record.id,
                    "humidity_id": humi_record.id,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"[DHT11-WiFi] ✗ 数据存储失败: {e}")
                print("-" * 60)
                logger.error(f"[DHT11-WiFi] 数据存储失败: {e}")
                await websocket.send_json({
                    "status": "error",
                    "message": f"Database error: {str(e)}"
                })
            finally:
                db.close()

    except WebSocketDisconnect:
        print("=" * 60)
        print("[DHT11-WiFi] ESP32 设备已断开连接")
        print(f"[DHT11-WiFi]   客户端: {client_host}:{client_port}")
        print(f"[DHT11-WiFi]   断开时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        logger.info(f"[DHT11-WiFi] ESP32 设备已断开: {client_host}:{client_port}")
    except Exception as e:
        print("=" * 60)
        print(f"[DHT11-WiFi] ✗ 连接异常: {e}")
        print(f"[DHT11-WiFi]   客户端: {client_host}:{client_port}")
        print("=" * 60)
        logger.error(f"[DHT11-WiFi] 连接异常: {e}")


@app.get("/")
def root():
    return {"message": "Hospital New Demo API", "docs": "/docs"}


# ===== 电梯控制调试 API（测试用，后续可移除）=====

@app.get("/api/v1/elevator/state", tags=["elevator"])
async def elevator_state():
    """查询电梯控制器状态（ESP32 是否连接等）"""
    controller = get_elevator_controller()
    return controller.get_state()


@app.post("/api/v1/elevator/command", tags=["elevator"])
async def elevator_command(cmd: str, floor: int = 3):
    """
    发送电梯控制命令（调试用）
    - cmd: open_door / close_door / go_floor / status / power_on / power_off
    - floor: 目标楼层（仅 go_floor 时有效，1-5）
    - power_on: 开机（方案A：继电器5持续吸合供电）
    - power_off: 关机（继电器5释放断电）
    """
    controller = get_elevator_controller()

    if not controller.is_connected():
        return {"status": "error", "message": "ESP32 电梯控制器未连接"}

    try:
        if cmd == "open_door":
            ack = await controller.send_open_door()
        elif cmd == "close_door":
            ack = await controller.send_close_door()
        elif cmd == "go_floor":
            ack = await controller.send_go_floor(floor)
        elif cmd == "status":
            ack = await controller.send_status_query()
        elif cmd == "power_on":
            ack = await controller.send_power_on()
        elif cmd == "power_off":
            ack = await controller.send_power_off()
        else:
            return {"status": "error", "message": f"未知命令: {cmd}"}

        return {"status": "success", "ack": ack}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "命令超时，未收到 ESP32 ACK"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===== 电梯调试 API：动态设置 lift_across_delay（测试用）=====

@app.post("/api/v1/elevator/debug/delay", tags=["elevator"])
async def set_lift_delay(seconds: int = 60):
    """
    动态设置 lift-across 到 lift-open 的延迟时间（调试用）
    默认 60 秒，设为 5 可快速测试
    """
    from app.services.ros_listener import set_lift_across_delay_override
    set_lift_across_delay_override(seconds)
    return {"status": "success", "lift_across_delay": seconds}


@app.get("/api/v1/elevator/debug/delay", tags=["elevator"])
async def get_lift_delay():
    """查询当前 lift_across_delay"""
    from app.services.ros_listener import get_lift_across_delay_override
    delay = get_lift_across_delay_override()
    return {"lift_across_delay": delay}
