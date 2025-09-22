from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    uploaded_at: datetime


class Citation(BaseModel):
    section: str
    page: int


class AskRequest(BaseModel):
    document_id: str = Field(..., min_length=8, max_length=64)
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="User question limited to 500 characters to reduce injection attempts.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def sanitize_question(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("Question cannot be empty.")
        return " ".join(text.split())


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


class ExampleGuide(BaseModel):
    slug: str
    name: str
    filename: str
