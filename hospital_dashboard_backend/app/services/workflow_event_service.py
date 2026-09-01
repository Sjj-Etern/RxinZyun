"""
处方流程事件流水服务

记录每个处方在 15 节点全流程中的真实通信事件，供前端大屏竖向时间线展示。
事件即状态：有事件 = 该节点已完成；最后一条事件对应节点 = 进行中。

15 节点定义（3 阶段）：
  阶段一 处方流转：N1 开具处方 / N2 任务确认 / N3 前往药房 / N4 抓取药品 / N5 扫码出库
  阶段二 跨梯运输：N6 任务下发 / N7 抵达电梯 / N8 电梯开门 / N9 跨梯运输
                    N10 电梯关门 / N11 楼层到达 / N12 开门送出
  阶段三 交付确认：N13 扫码确认 / N14 语音播报 / N15 任务完成
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import sessionmaker

from app.db.session import engine as LOCAL_ENGINE
from app.db.models import WorkflowEvent

# 引擎已存在的 Session 工厂（与 init_workflow_table.py 一致）
_Session = sessionmaker(bind=LOCAL_ENGINE)

# ===== 15 节点常量（event_key → 中文名） =====
EVENT_NODE_NAMES: Dict[str, str] = {
    "N1_prescription_created":  "开具处方",
    "N2_task_confirmed":        "任务确认",
    "N3_navigate_pharmacy":     "前往药房",
    "N4_picking_medicine":      "抓取药品",
    "N5_scanned_outbound":      "扫码出库",
    "N6_task_dispatched":       "任务下发",
    "N7_arrived_elevator":      "抵达电梯",
    "N8_elevator_door_open":   "电梯开门",
    "N9_crossing_elevator":     "跨梯运输",
    "N10_elevator_door_close": "电梯关门",
    "N11_floor_arrived":        "楼层到达",
    "N12_lift_open_sent":       "开门送出",
    "N13_scanned_confirm":      "扫码确认",
    "N14_voice_broadcast":      "语音播报",
    "N15_task_completed":       "任务完成",
}

# 节点顺序（用于前端排序与状态推导）
NODE_ORDER: List[str] = list(EVENT_NODE_NAMES.keys())


def record_event(prescription_code: str, event_key: str, source: str,
                 detail: Optional[str] = None) -> None:
    """记录一条流程事件（同步写库，失败仅打警告不影响主流程）"""
    if event_key not in EVENT_NODE_NAMES:
        print(f"[WorkflowEvent] [警告] 未知事件键: {event_key}，忽略")
        return
    try:
        session = _Session()
        try:
            session.add(WorkflowEvent(
                prescription_code=prescription_code,
                event_key=event_key,
                source=source,
                detail=detail,
                created_at=datetime.utcnow(),
            ))
            session.commit()
        finally:
            session.close()
    except Exception as e:
        # 事件记录失败不阻塞业务流程
        print(f"[WorkflowEvent] [警告] 事件写入失败 {prescription_code}/{event_key}: {e}")


def delete_events_for_prescription(prescription_code: str) -> int:
    """删除指定处方的全部节点事件（HIS 删除处方时联动调用，清空节点数据，不做存储）

    返回删除的事件条数。同时清理进程内 pharmacist/nurse-success 幂等集合，
    保证同号新处方重新走流程时信号能正常触发。
    """
    deleted = 0
    try:
        session = _Session()
        try:
            deleted = (
                session.query(WorkflowEvent)
                .filter(WorkflowEvent.prescription_code == prescription_code)
                .delete(synchronize_session=False)
            )
            session.commit()
        finally:
            session.close()
    except Exception as e:
        print(f"[WorkflowEvent] [警告] 事件删除失败 {prescription_code}: {e}")
        return deleted

    # 同步清理大屏后端 prescription_workflow_state 旧表该处方记录
    try:
        from app.db.models import PrescriptionWorkflowState
        session = _Session()
        try:
            session.query(PrescriptionWorkflowState).filter(
                PrescriptionWorkflowState.prescription_code == prescription_code
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        print(f"[WorkflowEvent] [警告] 旧表清理失败 {prescription_code}: {e}")

    # 清理幂等集合（允许同处方码重新触发 success 信号）
    try:
        from app.api.v1.routers import workflow as _wf
        _wf._triggered_pharmacist_success.discard(prescription_code)
        _wf._triggered_nurse_success.discard(prescription_code)
    except Exception:
        pass
    return deleted


def get_events_for_prescriptions(codes: List[str]) -> Dict[str, List[dict]]:
    """批量查询多个处方的事件流水，返回 {prescription_code: [event_dict, ...]}（按时间正序）"""
    if not codes:
        return {}
    result: Dict[str, List[dict]] = {code: [] for code in codes}
    try:
        session = _Session()
        try:
            rows = (
                session.query(WorkflowEvent)
                .filter(WorkflowEvent.prescription_code.in_(codes))
                .order_by(WorkflowEvent.created_at.asc(), WorkflowEvent.id.asc())
                .all()
            )
            for r in rows:
                result.setdefault(r.prescription_code, []).append({
                    "event_key": r.event_key,
                    "node_name": EVENT_NODE_NAMES.get(r.event_key, r.event_key),
                    "source": r.source,
                    "detail": r.detail,
                    "created_at": r.created_at,
                    "time": r.created_at.strftime("%H:%M:%S") if r.created_at else "",
                })
        finally:
            session.close()
    except Exception as e:
        print(f"[WorkflowEvent] [警告] 事件查询失败: {e}")
    return result


def build_steps_from_events(events: List[dict]) -> List[dict]:
    """根据事件流水推导 15 节点状态（供 /prescriptions/progress 接口使用）

    规则：节点有事件 → completed；最后一个事件节点 → active；其余 → pending。
    无事件时返回全 pending（前端始终按 15 节点渲染）。
    """
    occurred_keys = []
    for ev in events:
        if ev["event_key"] not in occurred_keys:
            occurred_keys.append(ev["event_key"])
    last_key = occurred_keys[-1] if occurred_keys else None

    steps = []
    for key in NODE_ORDER:
        if key == last_key and key != "N15_task_completed":
            status = "active"
        elif key in occurred_keys:
            status = "completed"
        else:
            status = "pending"
        # 找该节点最新一次事件
        node_event = next((e for e in reversed(events) if e["event_key"] == key), None)
        steps.append({
            "id": key,
            "name": EVENT_NODE_NAMES[key],
            "status": status,
            "desc": (node_event.get("detail") or "") if node_event else "",
            "time": (node_event.get("time") or "") if node_event else "",
        })
    return steps
