from pydantic import BaseModel


class CameraTestResponse(BaseModel):
    ok: bool
    message: str


class CameraUrlResponse(BaseModel):
    rtsp_url: str
