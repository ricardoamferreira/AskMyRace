from __future__ import annotations

import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.schemas import AskRequest, AskResponse, Citation, UploadResponse
from backend.app.services import document_registry
from backend.app.services.document_registry import Chunk, DocumentEntry
from backend.app.services.embedding import embed_chunks, embed_query
from backend.app.services.pdf_loader import PageChunk, load_pdf_chunks
from backend.app.services.qa import answer_question

load_dotenv()

app = FastAPI(title="Ask My Race API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    file_bytes = await file.read()
    chunks, page_count = load_pdf_chunks(file_bytes)
    if not chunks:
        raise HTTPException(status_code=400, detail="Could not extract text from the PDF.")

    embeddings = embed_chunks([chunk.text for chunk in chunks])
    registry = document_registry.get_registry()
    document_id = str(uuid.uuid4())
    entry = DocumentEntry(
        id=document_id,
        filename=file.filename,
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
                embedding=vector,
            )
        )
    registry.add(entry)

    return UploadResponse(
        document_id=document_id,
        filename=file.filename,
        page_count=page_count,
        uploaded_at=entry.uploaded_at,
    )


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
