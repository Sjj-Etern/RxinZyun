from typing import List
from sqlalchemy.orm import Session

from app.db import models
from app.schemas.sensor import SensorDataCreate
from app.schemas.data import FrontendDataCreate


def create_sensor_record(db: Session, sensor_data: SensorDataCreate) -> models.SensorRecord:
    record = models.SensorRecord(
        name=sensor_data.name,
        value=sensor_data.value,
        unit=sensor_data.unit,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_sensor_records(db: Session, limit: int = 50) -> List[models.SensorRecord]:
    return db.query(models.SensorRecord).order_by(models.SensorRecord.timestamp.desc()).limit(limit).all()


def get_latest_temperature(db: Session) -> models.SensorRecord:
    return db.query(models.SensorRecord).filter(
        models.SensorRecord.name == "temperature"
    ).order_by(models.SensorRecord.timestamp.desc()).first()


def get_latest_humidity(db: Session) -> models.SensorRecord:
    return db.query(models.SensorRecord).filter(
        models.SensorRecord.name == "humidity"
    ).order_by(models.SensorRecord.timestamp.desc()).first()


def create_frontend_record(db: Session, payload: FrontendDataCreate) -> models.FrontendRecord:
    record = models.FrontendRecord(
        key=payload.key,
        value=payload.value,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_frontend_records(db: Session, limit: int = 50) -> List[models.FrontendRecord]:
    return db.query(models.FrontendRecord).order_by(models.FrontendRecord.created_at.desc()).limit(limit).all()
