from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.schemas import (
    AskRequest,
    AskResponse,
    Citation,
    ExampleGuide,
    UploadResponse,
)
from backend.app.services import document_registry
from backend.app.services.document_registry import Chunk, DocumentEntry
from backend.app.services.embedding import embed_chunks, embed_query
from backend.app.services.pdf_loader import PageChunk, load_pdf_chunks
from backend.app.services.qa import answer_question

load_dotenv(override=True)

app = FastAPI(title="Ask My Race API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EXAMPLES_DIR = BASE_DIR / "race_examples"
MAX_PDF_SIZE_BYTES = 80 * 1024 * 1024  # 80 MB limit
BANNED_PATTERNS = [
    re.compile(r"ignore\s+(?:all|any)\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"pretend\s+to\s+be", re.IGNORECASE),
    re.compile(r"leak\s+.*prompt", re.IGNORECASE),
    re.compile(r"reveal\s+.*system", re.IGNORECASE),
]
TRIATHLON_KEYWORDS = [
    "triathlon",
    "triathlete",
    "swim",
    "bike",
    "run",
    "transition",
    "t1",
    "t2",
    "split",
    "race brief",
    "cut off",
    "ironman",
    "70.3",
    "half iron",
    "age group",
    "relay",
]
MIN_KEYWORD_MATCHES = 3


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._records: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window
        queue = self._records[key]
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        return True


upload_rate_limiter = RateLimiter(limit=5, window_seconds=60)
ask_rate_limiter = RateLimiter(limit=30, window_seconds=60)


def ingest_pdf(file_bytes: bytes, filename: str) -> UploadResponse:
    chunks, page_count = load_pdf_chunks(file_bytes)
    if not chunks:
        raise ValueError("Could not extract text from the PDF.")

    if not _looks_like_triathlon_guide(chunks):
        raise ValueError(
            "The uploaded PDF does not appear to describe a triathlon athlete guide."
        )

    embeddings = embed_chunks([chunk.text for chunk in chunks])
    registry = document_registry.get_registry()
    document_id = str(uuid.uuid4())
    entry = DocumentEntry(
        id=document_id,
        filename=filename,
        page_count=page_count,
        uploaded_at=datetime.utcnow(),
    )
    for chunk, vector in zip(chunks, embeddings, strict=False):
        entry.chunks.append(
            Chunk(
                id=chunk.id,
                text=chunk.text,
                page=chunk.page,
                section=chunk.section,
                order=chunk.order,
                embedding=vector,
            )
        )
    registry.add(entry)

    return UploadResponse(
        document_id=document_id,
        filename=filename,
        page_count=page_count,
        uploaded_at=entry.uploaded_at,
    )


def list_example_guides() -> List[ExampleGuide]:
    if not EXAMPLES_DIR.exists():
        return []

    guides: List[ExampleGuide] = []
    for path in sorted(EXAMPLES_DIR.glob("*.pdf")):
        filename = path.name
        stem = path.stem
        slug = _slugify(stem)
        name = _humanize(stem)
        guides.append(ExampleGuide(slug=slug, name=name, filename=filename))
    return guides


def _looks_like_triathlon_guide(chunks: Iterable[PageChunk]) -> bool:
    pages = list(chunks)
    sample_text = " ".join(chunk.text for chunk in pages[:10])
    lower_text = sample_text.lower()
    matches = sum(1 for keyword in TRIATHLON_KEYWORDS if keyword in lower_text)
    return matches >= MIN_KEYWORD_MATCHES


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-") or value.lower()


def _humanize(value: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def _require_rate_limit(limiter: RateLimiter, request: Request, error_message: str) -> None:
    identifier = request.client.host if request.client else "anonymous"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        identifier = forwarded.split(",")[0].strip()
    if not limiter.check(identifier):
        raise HTTPException(status_code=429, detail=error_message)


def _check_text_for_abuse(text: str) -> None:
    for pattern in BANNED_PATTERNS:
        if pattern.search(text):
            raise HTTPException(
                status_code=400,
                detail="That request was blocked because it attempts to override safety instructions.",
            )


def _ensure_pdf_size(file: UploadFile, file_bytes: bytes) -> None:
    size = len(file_bytes)
    if size > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 80 MB limit.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Filename must end with .pdf")


@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(request: Request, file: UploadFile = File(...)) -> UploadResponse:
    _require_rate_limit(upload_rate_limiter, request, "Too many uploads from this IP. Try again later.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    file_bytes = await file.read()
    _ensure_pdf_size(file, file_bytes)
    try:
        return ingest_pdf(file_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/examples", response_model=List[ExampleGuide])
async def get_examples() -> List[ExampleGuide]:
    return list_example_guides()


@app.post("/examples/{slug}", response_model=UploadResponse)
async def load_example(slug: str) -> UploadResponse:
    for guide in list_example_guides():
        if guide.slug == slug:
            file_path = EXAMPLES_DIR / guide.filename
            file_bytes = file_path.read_bytes()
            try:
                return ingest_pdf(file_bytes, guide.filename)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail="Example guide not found.")


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: Request, payload: AskRequest) -> AskResponse:
    _require_rate_limit(ask_rate_limiter, request, "Too many questions from this IP. Please slow down.")
    _check_text_for_abuse(payload.question)
    if payload.context:
        _check_text_for_abuse(payload.context)

    registry = document_registry.get_registry()
    try:
        entry = registry.require(payload.document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    combined_query = payload.question
    if payload.context:
        combined_query = (
            f"{payload.question}\n\nPrevious conversation context:\n{payload.context}"
        )

    query_embedding = embed_query(combined_query)
    settings = get_settings()
    top_chunks = entry.similarity_search(query_embedding, top_k=settings.top_k)
    answer = answer_question(payload.question, payload.context, top_chunks)
    citations = [Citation(section=chunk.section, page=chunk.page) for chunk in top_chunks]
    return AskResponse(answer=answer, citations=citations)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
