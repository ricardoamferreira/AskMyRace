from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ScheduleItem(BaseModel):
    time: str
    activity: str


class ScheduleDay(BaseModel):
    title: str
    items: List[ScheduleItem]


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    uploaded_at: datetime
    schedule: List[ScheduleDay] = Field(default_factory=list)


class Citation(BaseModel):
    section: str
    page: int
    excerpt: str


class AskRequest(BaseModel):
    document_id: str = Field(..., min_length=8, max_length=64)
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="User question limited to 500 characters to reduce injection attempts.",
    )
    context: Optional[str] = Field(
        default=None,
        max_length=1500,
        description="Optional prior conversation to help with follow-up questions.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def sanitize_question(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("Question cannot be empty.")
        return " ".join(text.split())

    @field_validator("context", mode="before")
    @classmethod
    def sanitize_context(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        return " ".join(text.split())


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


class ExampleGuide(BaseModel):
    slug: str
    name: str
    filename: str
