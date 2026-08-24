from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FrontendDataCreate(BaseModel):
    key: str
    value: str


class FrontendDataRead(FrontendDataCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
