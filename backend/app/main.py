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
RACK_TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b")
TIME_RANGE_PATTERN = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")
DAY_PATTERN = re.compile(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+", re.IGNORECASE)


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



def _has_transition_schedule(text: str) -> bool:
    lower = text.lower()
    if not RACK_TIME_PATTERN.search(text):
        return False
    keywords = ("transition 1", "transition one", "t1", "bike check-in", "bike check in", "blue bag")
    return any(keyword in lower for keyword in keywords)



def _augment_with_schedule_chunks(entry: DocumentEntry, selected: List[Chunk]) -> List[Chunk]:
    seen_ids = {chunk.id for chunk in selected}
    if any(_has_transition_schedule(chunk.text) for chunk in selected):
        return selected
    for chunk in entry.chunks:
        if chunk.id in seen_ids:
            continue
        if _has_transition_schedule(chunk.text):
            selected.insert(0, chunk)
            break
    return selected



def _extract_transition_schedule_notes(entry: DocumentEntry, selected: List[Chunk]) -> List[str]:
    pre_race_data: list[tuple[str | None, str, int, int]] = []
    race_morning_data: list[tuple[str | None, str, int]] = []
    seen_pre: set[str] = set()
    seen_race: set[str] = set()
    for chunk in entry.chunks:
        if "transition 1" not in chunk.text.lower():
            continue
        for day_label, time_range in _extract_transition_notes_from_text(chunk.text):
            start_str, end_str = [part.strip() for part in time_range.split("-", 1)]
            start_hour, start_min = map(int, start_str.split(":"))
            end_hour, end_min = map(int, end_str.split(":"))
            if start_hour <= 6:
                if time_range not in seen_race:
                    seen_race.add(time_range)
                    start_minutes = start_hour * 60 + start_min
                    race_morning_data.append((day_label, time_range, start_minutes))
            elif 7 <= start_hour <= 12:
                if time_range not in seen_pre:
                    seen_pre.add(time_range)
                    start_minutes = start_hour * 60 + start_min
                    end_minutes = end_hour * 60 + end_min
                    duration = end_minutes - start_minutes
                    if duration >= 240:
                        pre_race_data.append((day_label, time_range, start_hour, duration))
    notes: list[str] = []
    preferred_pre: tuple[str | None, str, int, int] | None = None
    for item in pre_race_data:
        label = (item[0] or "").lower()
        if "saturday" in label or "friday" in label:
            preferred_pre = item
            break
    if preferred_pre is None and pre_race_data:
        preferred_pre = max(pre_race_data, key=lambda item: (item[0] is not None, item[2], item[3]))
    if preferred_pre:
        day_label, time_range, _, _ = preferred_pre
        label_text = day_label or "Pre-race day"
        notes.append(f"Transition 1 pre-race ({label_text}): {time_range}")
    preferred_race: tuple[str | None, str, int] | None = None
    for item in race_morning_data:
        label = (item[0] or "").lower()
        if "sunday" in label or "race" in label:
            preferred_race = item
            break
    if preferred_race is None and race_morning_data:
        preferred_race = min(race_morning_data, key=lambda item: item[2])
    if preferred_race:
        day_label, time_range, _ = preferred_race
        label_text = day_label or "Race morning"
        notes.append(f"Transition 1 race morning ({label_text}): {time_range}")
    return notes


def _extract_transition_notes_from_text(text: str) -> List[tuple[str | None, str]]:
    results: list[tuple[str | None, str]] = []
    day_matches = [(match.group().strip(), match.start()) for match in DAY_PATTERN.finditer(text)]
    lowered = text.lower()
    for match in re.finditer(r"transition 1", lowered):
        idx = match.start()
        nearest_day: str | None = None
        for day_label, pos in day_matches:
            if pos <= idx:
                nearest_day = day_label
            else:
                break
        if nearest_day is None and day_matches:
            nearest_day = day_matches[0][0]
        segment = text[idx:idx + 800]
        time_ranges = TIME_RANGE_PATTERN.findall(segment)
        for time_range in time_ranges:
            results.append((nearest_day, time_range))
    return results


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

    filename = file.filename
    if not isinstance(filename, str) or not filename.strip():
        raise HTTPException(status_code=400, detail="Filename is required.")

    if not filename.lower().endswith(".pdf"):
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
    top_chunks = _augment_with_schedule_chunks(entry, top_chunks)
    helper_notes = _extract_transition_schedule_notes(entry, top_chunks)
    helper_text = " | ".join(helper_notes) if helper_notes else None
    answer = answer_question(payload.question, payload.context, helper_text, top_chunks)
    citations = [
        Citation(
            section=chunk.section,
            page=chunk.page,
            excerpt=_summarize_excerpt(chunk.text),
        )
        for chunk in top_chunks
    ]
    return AskResponse(answer=answer, citations=citations)


def _summarize_excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= 220:
        return cleaned
    return cleaned[:217] + "..."


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
