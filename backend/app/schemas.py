from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    uploaded_at: datetime


class Citation(BaseModel):
    section: str
    page: int


class AskRequest(BaseModel):
    document_id: str
    question: str


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


class ExampleGuide(BaseModel):
    slug: str
    name: str
    filename: str
