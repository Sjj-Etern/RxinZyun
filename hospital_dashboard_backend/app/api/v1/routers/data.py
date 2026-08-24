from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import crud
from app.schemas.data import FrontendDataCreate, FrontendDataRead

router = APIRouter()


@router.get("/items", response_model=List[FrontendDataRead])
def list_frontend_data(db: Session = Depends(get_db)):
    return crud.get_frontend_records(db=db)


@router.post("/items", response_model=FrontendDataRead, status_code=201)
def create_frontend_data(payload: FrontendDataCreate, db: Session = Depends(get_db)):
    return crud.create_frontend_record(db=db, payload=payload)
