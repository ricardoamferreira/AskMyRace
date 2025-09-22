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
    id: str
    text: str
    page: int
    section: str


def load_pdf_chunks(file_bytes: bytes) -> Tuple[List[PageChunk], int]:
    reader = PdfReader(io.BytesIO(file_bytes))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
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
                )
            )
    return chunk_list, len(reader.pages)


def infer_section_title(page_text: str) -> str:
    lines: List[str] = [line.strip() for line in page_text.splitlines() if line.strip()]
    if not lines:
        return "Unknown Section"
    for line in lines[:5]:
        alpha_ratio = sum(char.isalpha() for char in line) / max(len(line), 1)
        if len(line) <= 80 and alpha_ratio > 0.5 and line.upper() == line:
            return normalize_title(line)
    return normalize_title(lines[0])


def normalize_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned.title()
