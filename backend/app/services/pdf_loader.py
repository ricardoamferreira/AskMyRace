"""Utilities for splitting athlete guide PDFs into contextual chunks."""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from typing import List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


@dataclass
class PageChunk:
    """Represents one chunk of text tied to a source page and section."""
    id: str
    text: str
    page: int
    section: str
    order: int


def load_pdf_chunks(file_bytes: bytes) -> Tuple[List[PageChunk], int]:
    """Extract text from a PDF, split it into overlapping chunks, and return them with page count."""
    reader = PdfReader(io.BytesIO(file_bytes))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
        add_start_index=True,
    )
    chunk_list: List[PageChunk] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        stripped = text.strip()
        if not stripped:
            continue
        section = infer_section_title(stripped)
        for chunk_text in splitter.split_text(stripped):
            chunk_list.append(
                PageChunk(
                    id=str(uuid.uuid4()),
                    text=chunk_text,
                    page=page_index,
                    section=section,
                    order=len(chunk_list),
                )
            )
    return chunk_list, len(reader.pages)


def infer_section_title(page_text: str) -> str:
    """Guess a section heading for a page by looking at prominent early lines."""
    lines: List[str] = [line.strip() for line in page_text.splitlines() if line.strip()]
    if not lines:
        return "Unknown Section"
    for line in lines[:5]:
        alpha_ratio = sum(char.isalpha() for char in line) / max(len(line), 1)
        if len(line) <= 80 and alpha_ratio > 0.5 and line.upper() == line:
            return normalize_title(line)
    return normalize_title(lines[0])


def normalize_title(title: str) -> str:
    """Collapse whitespace and title-case a heading-like string."""
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned.title()
