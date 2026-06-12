from pydantic import BaseModel, Field


class SeoPageTrackBody(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)


class SeoPageOut(BaseModel):
    id: int
    path: str
    title: str
    views_count: int
    sort_order: int
