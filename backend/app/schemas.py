"""Pydantic schemas shared by the FastAPI endpoints and frontend."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ScheduleItem(BaseModel):
    """Individual timetable entry surfaced in API responses."""
    time: str
    activity: str
    location: str | None = None


class ScheduleDay(BaseModel):
    """Collection of schedule items grouped by day heading."""
    title: str
    items: List[ScheduleItem]


class UploadResponse(BaseModel):
    """Metadata returned after a PDF is ingested and indexed."""
    document_id: str
    filename: str
    page_count: int
    uploaded_at: datetime
    schedule: List[ScheduleDay] = Field(default_factory=list)


class Citation(BaseModel):
    """Reference pointing back to a chunk that supported the answer."""
    section: str
    page: int
    excerpt: str


class AskRequest(BaseModel):
    """Payload accepted by the /ask endpoint."""
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
        """Strip whitespace and collapse spaces before validation."""
        text = (value or "").strip()
        if not text:
            raise ValueError("Question cannot be empty.")
        return " ".join(text.split())

    @field_validator("context", mode="before")
    @classmethod
    def sanitize_context(cls, value: Optional[str]) -> Optional[str]:
        """Normalize optional context strings, returning None for empty values."""
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        return " ".join(text.split())


class AskResponse(BaseModel):
    """Model for responses emitted by the /ask endpoint."""
    answer: str
    citations: List[Citation]


class ExampleGuide(BaseModel):
    """Represents a demo guide exposed through the examples endpoint."""
    slug: str
    name: str
    filename: str
