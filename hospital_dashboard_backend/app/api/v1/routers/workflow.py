"""
药品运输流程跟踪 API
追踪处方从HIS同步到患者领药的完整流程
"""
import socket
import asyncio
import pymysql
from fastapi import APIRouter, HTTPException, Body
from app.core.config import settings, get_ros_ws_url, get_camera_audio_base_url
from app.services.ros_listener import get_ros_state
from app.services.audio_service import get_audio_state, play_audio_sync, check_camera_reachable
from app.services.workflow_event_service import record_event, get_events_for_prescriptions, delete_events_for_prescription

router = APIRouter()

# HIS 数据库连接配置
HIS_DB_CONFIG = {
    "host": settings.his_mysql_host,
    "port": settings.his_mysql_port,
    "user": settings.his_mysql_user,
    "password": settings.his_mysql_pass,
    "database": settings.his_mysql_db,
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

# 全局标记：MySQL 是否可用
_mysql_available = None


def _check_mysql():
    """检测 HIS MySQL 数据库是否可用"""
    global _mysql_available
    if _mysql_available is not None:
        return _mysql_available
    try:
        conn = pymysql.connect(**HIS_DB_CONFIG, connect_timeout=3)
        conn.close()
        _mysql_available = True
        return True
    except Exception:
        _mysql_available = False
        return False


def _get_his_connection():
    """获取 HIS MySQL 数据库连接"""
    return pymysql.connect(**HIS_DB_CONFIG, connect_timeout=5)


@router.get("/workflow/ros/test")
def test_ros_connection():
    """
    测试 ROS WebSocket 连通性
    
    返回：
    - reachable: 端口是否可达
    - host: ROS WebSocket 主机地址
    - port: ROS WebSocket 端口
    - ws_url: WebSocket 完整地址
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(settings.ros_connect_timeout)
        result = sock.connect_ex((settings.ros_ws_host, settings.ros_ws_port))
        sock.close()
        reachable = result == 0
    except Exception as e:
        reachable = False
    
    return {
        "reachable": reachable,
        "host": settings.ros_ws_host,
        "port": settings.ros_ws_port,
        "ws_url": get_ros_ws_url(),
        "topic": settings.ros_topic,
        "check_interval": settings.ros_check_interval,
        "connect_timeout": settings.ros_connect_timeout,
    }


@router.get("/workflow/ros/status")
def get_ros_listener_status():
    """
    获取 ROS WebSocket 监听服务状态
    
    返回：
    - listener_state: 监听服务状态（stopped/checking/connecting/connected/disconnected/reconnecting）
    - ws_reachable: WebSocket 端口是否可达
    - last_check_time: 上次检测时间
    - last_message_time: 上次收到消息时间
    - current_robot_status: 当前机器人状态
    - steps: 各节点状态
    """
    ros_state = get_ros_state()
    return {
        "config": {
            "host": settings.ros_ws_host,
            "port": settings.ros_ws_port,
            "ws_url": get_ros_ws_url(),
            "topic": settings.ros_topic,
        },
        **ros_state
    }


@router.get("/workflow/audio/test")
def test_audio_connection():
    """
    测试摄像头语音播报连通性
    
    返回：
    - camera_reachable: 摄像头 HTTP API 端口是否可达
    - camera_host: 摄像头主机地址
    - camera_audio_port: 摄像头 HTTP API 端口
    - audio_base_url: 语音播报 API 基础地址
    - audio_id_start: 任务确认语音 ID
    """
    reachable = check_camera_reachable(
        settings.camera_host,
        settings.camera_audio_port,
        settings.audio_connect_timeout
    )
    
    return {
        "camera_reachable": reachable,
        "camera_host": settings.camera_host,
        "camera_audio_port": settings.camera_audio_port,
        "audio_base_url": get_camera_audio_base_url(),
        "audio_id_start": settings.audio_id_start,
        "audio_check_interval": settings.audio_check_interval,
        "audio_connect_timeout": settings.audio_connect_timeout,
    }


@router.get("/workflow/audio/status")
def get_audio_status():
    """
    获取摄像头语音播报状态
    
    返回：
    - camera_reachable: 摄像头端口是否可达
    - last_check_time: 上次检测时间
    - last_play_time: 上次播放时间
    - last_play_status: 上次播放状态
    - last_audio_id: 上次播放的语音 ID
    """
    audio_state = get_audio_state()
    return {
        "config": {
            "camera_host": settings.camera_host,
            "camera_audio_port": settings.camera_audio_port,
            "audio_id_start": settings.audio_id_start,
        },
        **audio_state
    }


@router.post("/workflow/audio/play")
def trigger_audio_play(audio_id: int = None):
    """
    手动触发语音播报（测试用）
    
    参数：
    - audio_id: 语音 ID（默认使用 audio_id_start=15）
    
    返回：
    - success: 是否播放成功
    - audio_id: 播放的语音 ID
    """
    if audio_id is None:
        audio_id = settings.audio_id_start
    
    success = play_audio_sync(audio_id)
    
    return {
        "success": success,
        "audio_id": audio_id,
        "audio_state": get_audio_state(),
    }


@router.get("/workflow/status")
def get_workflow_status():
    """
    获取当前药品运输流程的整体状态
    
    流程步骤：
    1. 开具处方：处方开具完成
    2. 任务确认：任务确认完成
    3. 扫码复合：扫码复核完成
    4. 站台交互：站台交互完成
    
    返回：
    - current_step: 当前正在进行的步骤编号（1-4）
    - steps: 各步骤的详细状态
    - progress: 整体进度百分比
    """
    if not _check_mysql():
        # 数据库不可用时返回初始状态，同时返回 ROS 状态
        ros_state = get_ros_state()
        return {
            "current_step": ros_state.get("current_step", 1),
            "progress": 0,
            "steps": ros_state.get("steps", [
                {"id": 1, "name": "开具处方", "status": "pending", "desc": "等待处方开具"},
                {"id": 2, "name": "任务确认", "status": "pending", "desc": "等待任务启动"},
                {"id": 3, "name": "扫码复合", "status": "pending", "desc": "等待扫码复核"},
                {"id": 4, "name": "站台交互", "status": "pending", "desc": "等待站台交互"},
            ]),
            "ros_status": ros_state.get("current_robot_status"),
        }
    
    try:
        conn = _get_his_connection()
        with conn.cursor() as cursor:
            # 查询处方状态统计
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN status = 'dispensed' THEN 1 ELSE 0 END) as dispensed,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
                FROM prescriptions
            """)
            presc_stats = cursor.fetchone()
            
            # 查询药品追溯码扫描状态
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'scanned_identify' THEN 1 ELSE 0 END) as identified,
                    SUM(CASE WHEN status = 'scanned_outbound' THEN 1 ELSE 0 END) as outbound,
                    SUM(CASE WHEN status = 'scanned_confirm' THEN 1 ELSE 0 END) as confirmed
                FROM medicine_trace_codes
            """)
            trace_stats = cursor.fetchone()
            
            # 计算各步骤状态
            # 步骤1：开具处方
            step1_completed = presc_stats["total"] > 0
            
            # 步骤2：任务确认
            step2_completed = trace_stats["total"] > 0  # 2次扫码流程：节点2不绑扫码（识别已取消），以追溯码已生成判定
            
            # 步骤3：扫码复合
            step3_completed = trace_stats["outbound"] > 0 and trace_stats["outbound"] == trace_stats["total"]  # 第1次扫码=出库，全部出库完成
            
            # 步骤4：站台交互
            step4_completed = trace_stats["confirmed"] > 0 and trace_stats["confirmed"] == trace_stats["total"]
            
            # 确定当前步骤（第一个未完成的步骤）
            current_step_num = 1
            if step1_completed:
                current_step_num = 2
            if step2_completed:
                current_step_num = 3
            if step3_completed:
                current_step_num = 4
            if step4_completed:
                current_step_num = 5  # 全部完成
            
            # 设置各步骤状态
            # 步骤1: 开具处方
            if step1_completed:
                step1_status = "completed"
                step1_desc = "处方已开具"
            elif current_step_num == 1:
                step1_status = "active"
                step1_desc = "等待处方开具"
            else:
                step1_status = "pending"
                step1_desc = "等待处方开具"
            
            # 步骤2: 任务确认
            if step2_completed:
                step2_status = "completed"
                step2_desc = "任务确认完成"
            elif current_step_num == 2:
                step2_status = "active"
                if trace_stats["identified"] > 0:
                    progress_pct = int(trace_stats["identified"] / trace_stats["total"] * 100) if trace_stats["total"] > 0 else 0
                    step2_desc = f"任务确认中 ({progress_pct}%)"
                else:
                    step2_desc = "等待任务启动"
            else:
                step2_status = "pending"
                step2_desc = "等待任务启动"
            
            # 步骤3: 扫码复合
            if step3_completed:
                step3_status = "completed"
                step3_desc = "扫码复合完成"
            elif current_step_num == 3:
                step3_status = "active"
                step3_desc = "等待扫码复核"
            else:
                step3_status = "pending"
                step3_desc = "等待扫码复核"
            
            # 步骤4: 站台交互
            if step4_completed:
                step4_status = "completed"
                step4_desc = "站台交互完成"
            elif current_step_num == 4:
                step4_status = "active"
                if trace_stats["confirmed"] > 0:
                    confirmed_pct = int(trace_stats["confirmed"] / trace_stats["total"] * 100) if trace_stats["total"] > 0 else 0
                    step4_desc = f"站台交互中 ({confirmed_pct}%)"
                else:
                    step4_desc = "等待站台交互"
            else:
                step4_status = "pending"
                step4_desc = "等待站台交互"
            
            # 计算整体进度
            progress = 0
            if step1_completed:
                progress += 25
            if step2_completed:
                progress += 25
            elif current_step_num == 2:
                progress += 12
            if step3_completed:
                progress += 25
            elif current_step_num == 3:
                progress += 12
            if step4_completed:
                progress += 25
            elif current_step_num == 4:
                progress += 12
            
            # 获取 ROS 状态
            ros_state = get_ros_state()
            
            return {
                "current_step": current_step_num,
                "progress": progress,
                "prescription_stats": {
                    "total": presc_stats["total"],
                    "pending": presc_stats["pending"],
                    "approved": presc_stats["approved"],
                    "dispensed": presc_stats["dispensed"],
                },
                "trace_stats": {
                    "total": trace_stats["total"],
                    "pending": trace_stats["pending"],
                    "identified": trace_stats["identified"],
                    "outbound": trace_stats["outbound"],
                    "confirmed": trace_stats["confirmed"],
                },
                "steps": [
                    {"id": 1, "name": "开具处方", "status": step1_status, "desc": step1_desc},
                    {"id": 2, "name": "任务确认", "status": step2_status, "desc": step2_desc},
                    {"id": 3, "name": "扫码复合", "status": step3_status, "desc": step3_desc},
                    {"id": 4, "name": "站台交互", "status": step4_status, "desc": step4_desc},
                ],
                "ros_status": ros_state.get("current_robot_status"),
            }
    
    except pymysql.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库连接失败: {str(e)}")
    finally:
        if "conn" in locals():
            conn.close()


@router.get("/workflow/his_sender/status")
def get_his_sender_status():
    """
    获取 HIS 处方发送服务状态
    
    返回：
    - running: 服务是否运行
    - current_prescription_code: 当前发送的处方编码
    - last_sent_code: 上次发送成功的处方编码
    - ros_ws_url: ROS WebSocket 地址
    - ros_topic: 发送的 Topic
    """
    from app.services.his_sender import get_sender_status
    return get_sender_status()


# 已触发过 pharmacist-success 的处方编码集合（进程内幂等去重，同一处方只触发一次）
_triggered_pharmacist_success: set = set()


@router.post("/workflow/pharmacist-success-trigger")
async def trigger_pharmacist_success(prescription_code: str = Body(..., embed=True)):
    """
    HIS 节点3扫码复核完成时调用 → 延迟后触发车2 pharmacist-success 连续发送，
    同时向车1 发送同样的 pharmacist-success 信号（触发条件/发送内容/内容格式完全一致）。

    判断依据：节点3扫码结束（处方所有追溯码已扫到出库状态），由 HIS 扫码端点检测并 HTTP 通知本接口。
    延迟时间通过 .env 的 PHARMACIST_SUCCESS_DELAY 统一配置（秒），设为 0 表示无延迟。
    """
    from app.services.his_sender import _senders as his_senders
    car2_sender = his_senders.get(2)
    if not car2_sender:
        raise HTTPException(status_code=503, detail="车2发送服务未启动")

    # 幂等去重：同一处方只触发一次，避免重复扫码/并发通知导致重复发送
    if prescription_code in _triggered_pharmacist_success:
        print(f"[pharmacist-success-trigger] 处方 {prescription_code} 已触发过，跳过")
        return {"status": "skipped", "message": f"处方 {prescription_code} 已触发过 pharmacist-success，跳过"}
    _triggered_pharmacist_success.add(prescription_code)

    # 延迟发送（由 .env PHARMACIST_SUCCESS_DELAY 统一配置）
    delay = settings.pharmacist_success_delay
    if delay > 0:
        print(f"[pharmacist-success-trigger] 处方 {prescription_code} 延迟 {delay} 秒后发送 pharmacist-success")
        await asyncio.sleep(delay)

    # 阶段一强制闭环：扫码完成后 N1-N5 全部视为完成（缺失的节点由 system 补记）
    _events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
    _existing = {e["event_key"] for e in _events}
    _backfill = {
        "N1_prescription_created": "处方已开具（扫码完成时补记）",
        "N2_task_confirmed": "任务已确认（扫码完成时补记）",
        "N3_navigate_pharmacy": "已前往药房（扫码完成时补记）",
        "N4_picking_medicine": "药品抓取完成（扫码完成时补记）",
    }
    for _key, _detail in _backfill.items():
        if _key not in _existing:
            record_event(prescription_code, _key, "system", _detail)
    record_event(prescription_code, "N5_scanned_outbound", "his", "药师扫码出库完成")

    await car2_sender.send_pharmacist_success(0, prescription_code)
    record_event(prescription_code, "N6_task_dispatched", "system", "跨梯运输任务已下发车2")

    # 车1：同一触发点发送同样的 pharmacist-success 信号（内容/格式与车2 完全一致）
    car1_sender = his_senders.get(1)
    if car1_sender:
        await car1_sender.send_pharmacist_success(0, prescription_code)
        print(f"[pharmacist-success-trigger] 已向车1 发送 pharmacist-success: {prescription_code}")
    else:
        print(f"[pharmacist-success-trigger] [警告] 车1发送服务未注册，跳过车1 pharmacist-success")

    return {
        "status": "success",
        "message": f"已触发车2/车1 pharmacist-success: {prescription_code}",
        "delay": delay,
    }


# 已触发过 nurse-success 的处方编码集合（进程内幂等去重，同一处方只触发一次）
_triggered_nurse_success: set = set()


@router.post("/workflow/scan-progress")
async def scan_progress(
    prescription_code: str = Body(..., embed=True),
    scanned: int = Body(..., embed=True),
    total: int = Body(..., embed=True),
    medicine_name: str = Body("", embed=True),
):
    """HIS 每次出库扫码后调用 → 更新 N5 节点显示扫码进度（已扫第几个/共几个）

    仅在 N5 节点已存在（arm_end 已到，扫码出库进行中）且流程未闭环（无 N6）时更新 detail：
    "扫码出库进行中（1/2），最近扫码：阿莫西林胶囊"。
    全部扫完时由 pharmacist-success-trigger 写入正式完成事件，覆盖进度显示。
    """
    if not prescription_code:
        raise HTTPException(status_code=400, detail="处方编码不能为空")

    events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
    keys = {e["event_key"] for e in events}
    if "N6_task_dispatched" in keys:
        return {"status": "skipped", "message": "流程已闭环，忽略扫码进度"}
    if "N5_scanned_outbound" not in keys:
        # arm_end 未到：N5 尚未开始，进度不落库（避免提前把抓药节点顶成完成）
        return {"status": "skipped", "message": "N5 节点尚未开始（arm_end 未到），忽略扫码进度"}

    detail = f"扫码出库进行中（{scanned}/{total}）"
    if medicine_name:
        detail += f"，最近扫码：{medicine_name}"
    record_event(prescription_code, "N5_scanned_outbound", "his", detail)
    return {"status": "success", "message": detail}


@router.delete("/workflow/prescription-events")
async def delete_prescription_events(prescription_code: str = Body(..., embed=True)):
    """HIS 删除处方时联动调用 → 清空该处方在大屏侧的全部节点数据（不做存储）

    清理内容：
    - workflow_events：15 节点事件流水（该处方全部删除）
    - prescription_workflow_state：旧 4 节点表该处方记录
    - 进程内 pharmacist/nurse-success 幂等集合：允许同号新处方重新触发信号

    场景：处方被删除后重新下单（处方码可能复用），旧事件会导致大屏直接显示"全部完成"。
    """
    if not prescription_code:
        raise HTTPException(status_code=400, detail="处方编码不能为空")
    deleted = delete_events_for_prescription(prescription_code)
    print(f"[prescription-events] 处方 {prescription_code} 节点数据已清空（删除 {deleted} 条事件）")
    return {
        "status": "success",
        "message": f"处方 {prescription_code} 节点数据已全部清空",
        "deleted_events": deleted,
    }


@router.post("/workflow/nurse-success-trigger")
async def trigger_nurse_success(prescription_code: str = Body(..., embed=True)):
    """
    HIS 节点4扫码全部确认时调用 → 延迟后触发车2 nurse-success 连续发送。

    判断依据：节点4扫码结束（处方所有追溯码均已扫到确认状态 scanned_confirm，
    即每个药品完成第二次扫码），由 HIS 扫码端点检测并 HTTP 通知本接口。
    触发方式：唤醒车2 listener 的护士到达事件 → 停止 lift-open 连发 → Step8 发送
    nurse-success（发3次自动停）。延迟时间通过 .env 的 NURSE_SUCCESS_DELAY 配置。
    """
    from app.services.his_sender import _senders as his_senders
    from app.services.ros_listener import get_listener
    car2_sender = his_senders.get(2)
    car2_listener = get_listener(2)
    if not car2_sender or not car2_listener:
        raise HTTPException(status_code=503, detail="车2发送服务未启动")

    # 流程阶段校验：护士确认扫码只能发生在交付阶段（N12 开门送出已完成）之后。
    # 防止药师在出库阶段对同一药品重复扫码（scanned_outbound → scanned_confirm）导致
    # HIS 判定"全部确认"而提前误触发 nurse-success（跳过电梯运输流程）。
    # 校验放在幂等去重之前：未到阶段的调用不写入幂等集合，后续合法触发不受影响。
    events = get_events_for_prescriptions([prescription_code]).get(prescription_code, [])
    keys = {e["event_key"] for e in events}
    if "N12_lift_open_sent" not in keys:
        print(f"[nurse-success-trigger] 处方 {prescription_code} 流程未到交付阶段（N12 缺失），跳过 nurse-success")
        return {"status": "skipped", "message": f"处方 {prescription_code} 流程未到交付阶段（N12 开门送出未完成），跳过 nurse-success"}

    # 幂等去重：同一处方只触发一次，避免重复扫码/并发通知导致重复发送
    if prescription_code in _triggered_nurse_success:
        print(f"[nurse-success-trigger] 处方 {prescription_code} 已触发过，跳过")
        return {"status": "skipped", "message": f"处方 {prescription_code} 已触发过 nurse-success，跳过"}
    _triggered_nurse_success.add(prescription_code)

    # 延迟触发（由 .env NURSE_SUCCESS_DELAY 统一配置）
    delay = settings.nurse_success_delay
    if delay > 0:
        print(f"[nurse-success-trigger] 处方 {prescription_code} 延迟 {delay} 秒后触发 nurse-success")
        await asyncio.sleep(delay)

    car2_listener.trigger_nurse_arrive_event(prescription_code)
    record_event(prescription_code, "N13_scanned_confirm", "his", "护士扫码确认完成")
    return {
        "status": "success",
        "message": f"已触发车2 nurse-success: {prescription_code}",
        "delay": delay,
    }