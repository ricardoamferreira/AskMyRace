from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
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
from backend.app.services.pdf_loader import load_pdf_chunks
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


def ingest_pdf(file_bytes: bytes, filename: str) -> UploadResponse:
    chunks, page_count = load_pdf_chunks(file_bytes)
    if not chunks:
        raise ValueError("Could not extract text from the PDF.")

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


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-") or value.lower()


def _humanize(value: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    file_bytes = await file.read()
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
async def ask_question(payload: AskRequest) -> AskResponse:
    registry = document_registry.get_registry()
    try:
        entry = registry.require(payload.document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    query_embedding = embed_query(payload.question)
    settings = get_settings()
    top_chunks = entry.similarity_search(query_embedding, top_k=settings.top_k)
    answer = answer_question(payload.question, top_chunks)
    citations = [Citation(section=chunk.section, page=chunk.page) for chunk in top_chunks]
    return AskResponse(answer=answer, citations=citations)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
