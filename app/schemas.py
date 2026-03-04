from datetime import datetime

from pydantic import BaseModel, Field


class DomainCreate(BaseModel):
    domain: str
    enabled: bool = True
    check_interval_sec: int = Field(default=300, ge=60)


class DomainOut(BaseModel):
    id: int
    domain: str
    enabled: bool
    check_interval_sec: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    detected_at: datetime
    change_type: str
    summary: str
    detail_json: str

    class Config:
        from_attributes = True
