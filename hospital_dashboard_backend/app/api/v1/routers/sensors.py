from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import crud
from app.schemas.sensor import SensorDataCreate, SensorDataRead, TemperatureHumidityResponse, DHT11DataCreate

router = APIRouter()


@router.get("/", response_model=List[SensorDataRead])
def list_sensors(db: Session = Depends(get_db)):
    return crud.get_sensor_records(db=db)


@router.post("/", response_model=SensorDataRead, status_code=201)
def create_sensor(sensor: SensorDataCreate, db: Session = Depends(get_db)):
    return crud.create_sensor_record(db=db, sensor_data=sensor)


@router.post("/dht11", status_code=201)
def receive_dht11_data(data: DHT11DataCreate, db: Session = Depends(get_db)):
    temp_record = crud.create_sensor_record(
        db=db,
        sensor_data=SensorDataCreate(
            name="temperature",
            value=data.temp,
            unit="°C"
        )
    )
    
    humi_record = crud.create_sensor_record(
        db=db,
        sensor_data=SensorDataCreate(
            name="humidity",
            value=data.humi,
            unit="%"
        )
    )
    
    return {
        "status": "success",
        "temperature_id": temp_record.id,
        "humidity_id": humi_record.id
    }


@router.get("/temperature", response_model=SensorDataRead)
def get_temperature(db: Session = Depends(get_db)):
    record = crud.get_latest_temperature(db=db)
    if not record:
        raise HTTPException(status_code=404, detail="Temperature data not found")
    return record


@router.get("/humidity", response_model=SensorDataRead)
def get_humidity(db: Session = Depends(get_db)):
    record = crud.get_latest_humidity(db=db)
    if not record:
        raise HTTPException(status_code=404, detail="Humidity data not found")
    return record


@router.get("/temp-humidity", response_model=TemperatureHumidityResponse)
def get_temp_humidity(db: Session = Depends(get_db)):
    temp_record = crud.get_latest_temperature(db=db)
    humi_record = crud.get_latest_humidity(db=db)
    
    if not temp_record:
        raise HTTPException(status_code=404, detail="Temperature data not found")
    if not humi_record:
        raise HTTPException(status_code=404, detail="Humidity data not found")
    
    latest_timestamp = max(temp_record.timestamp, humi_record.timestamp)
    
    return TemperatureHumidityResponse(
        temperature=temp_record.value,
        temperature_unit=temp_record.unit,
        humidity=humi_record.value,
        humidity_unit=humi_record.unit,
        timestamp=latest_timestamp
    )
