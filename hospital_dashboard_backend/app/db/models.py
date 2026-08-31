from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SensorRecord(Base):
    __tablename__ = "sensor_records"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(32), nullable=False, default="unit")
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class FrontendRecord(Base):
    __tablename__ = "frontend_records"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PrescriptionWorkflowState(Base):
    """
    处方流程状态表
    记录每个处方在 ROS 任务流程中的状态

    节点对应：
    - 节点1（开具处方）：由 HIS prescription.status 决定
    - 节点2（任务确认）：由 ROS running_started 等状态决定
    - 节点3（扫码复合）：由 ROS running_step3 状态决定
    - 节点4（站台交互）：由 ROS running_step4 状态决定
    """
    __tablename__ = "prescription_workflow_state"

    id = Column(Integer, primary_key=True, index=True)
    prescription_code = Column(String(50), nullable=False, unique=True, index=True)
    prescription_id = Column(Integer, nullable=True)
    current_node = Column(Integer, default=1)

    node2_status = Column(String(20), default="pending")
    node2_desc = Column(String(100), default="等待任务启动")

    node3_status = Column(String(20), default="pending")
    node3_desc = Column(String(100), default="等待扫码复核")

    node4_status = Column(String(20), default="pending")
    node4_desc = Column(String(100), default="等待站台交互")

    ros_status = Column(String(50), nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_prescription_code', 'prescription_code'),
    )


class WorkflowEvent(Base):
    """
    处方流程事件流水表
    记录每个处方在全流程 15 个节点上的真实通信事件（何时发生、来源）

    事件来源 source：
    - his         HIS 系统通知（HTTP）
    - car1        车1 ROS topic（/car01_pub）
    - car2        车2 ROS topic（/car02_pub）
    - elevator    电梯 ESP32（TCP）
    - system      系统内部编排
    """
    __tablename__ = "workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    prescription_code = Column(String(50), nullable=False, index=True)
    event_key = Column(String(50), nullable=False)   # 事件键（15节点之一）
    source = Column(String(20), nullable=False)      # 事件来源
    detail = Column(String(200), nullable=True)      # 补充说明（中文）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_we_code_key', 'prescription_code', 'event_key'),
        Index('idx_we_created', 'created_at'),
    )
