from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import numpy as np


@dataclass
class Chunk:
    id: str
    text: str
    page: int
    section: str
    embedding: np.ndarray


@dataclass
class DocumentEntry:
    id: str
    filename: str
    page_count: int
    uploaded_at: datetime
    chunks: List[Chunk] = field(default_factory=list)

    def similarity_search(self, query_embedding: np.ndarray, top_k: int) -> List[Chunk]:
        if not self.chunks:
            return []
        embeddings = np.vstack([chunk.embedding for chunk in self.chunks])
        norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
        # Guard against zero division when embeddings are zero-vectors
        similarities = (
            embeddings @ query_embedding
        ) / np.where(norms == 0, 1e-10, norms)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [self.chunks[i] for i in top_indices]


class DocumentRegistry:
    def __init__(self) -> None:
        self._store: Dict[str, DocumentEntry] = {}

    def add(self, entry: DocumentEntry) -> None:
        self._store[entry.id] = entry

    def get(self, document_id: str) -> DocumentEntry | None:
        return self._store.get(document_id)

    def require(self, document_id: str) -> DocumentEntry:
        entry = self.get(document_id)
        if not entry:
            raise KeyError(f"Document {document_id} not found")
        return entry

    def list(self) -> List[DocumentEntry]:
        return list(self._store.values())


_registry: DocumentRegistry | None = None


def get_registry() -> DocumentRegistry:
    global _registry
    if _registry is None:
        _registry = DocumentRegistry()
    return _registry
