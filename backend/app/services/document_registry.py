"""Lightweight in-memory document registry used by the retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import numpy as np


@dataclass
class Chunk:
    """Single vectorized passage extracted from an uploaded PDF."""
    id: str
    text: str
    page: int
    section: str
    order: int
    embedding: np.ndarray


@dataclass
class ScheduleItem:
    """Structured schedule entry parsed from the athlete guide."""
    time: str
    activity: str
    location: str | None = None


@dataclass
class ScheduleDay:
    """Day-level grouping of schedule items for easier rendering."""
    title: str
    items: List[ScheduleItem] = field(default_factory=list)


@dataclass
class DocumentEntry:
    """Container for the uploaded PDF, its chunks, and extracted schedule."""
    id: str
    filename: str
    page_count: int
    uploaded_at: datetime
    chunks: List[Chunk] = field(default_factory=list)
    schedule: List[ScheduleDay] = field(default_factory=list)

    def similarity_search(self, query_embedding: np.ndarray, top_k: int) -> List[Chunk]:
        """Compute cosine similarity and return the highest scoring chunks with neighbors."""
        if not self.chunks:
            return []
        embeddings = np.vstack([chunk.embedding for chunk in self.chunks])
        norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
        similarities = (
            embeddings @ query_embedding
        ) / np.where(norms == 0, 1e-10, norms)
        anchor_indices = np.argsort(similarities)[::-1][:top_k]

        selected: List[Chunk] = []
        seen_ids: set[str] = set()

        for idx in anchor_indices:
            anchor = self.chunks[idx]
            if anchor.id in seen_ids:
                continue
            selected.append(anchor)
            seen_ids.add(anchor.id)

            for candidate in self.chunks:
                if candidate.page != anchor.page:
                    continue
                if candidate.id in seen_ids:
                    continue
                selected.append(candidate)
                seen_ids.add(candidate.id)
                break

        return selected


class DocumentRegistry:
    """In-memory store keyed by document id for quick lookups."""
    def __init__(self) -> None:
        self._store: Dict[str, DocumentEntry] = {}

    def add(self, entry: DocumentEntry) -> None:
        """Add a document entry, replacing any previous version."""
        self._store[entry.id] = entry

    def get(self, document_id: str) -> DocumentEntry | None:
        """Return the entry for the document id if it exists."""
        return self._store.get(document_id)

    def require(self, document_id: str) -> DocumentEntry:
        """Fetch an entry or raise if it is missing from the registry."""
        entry = self.get(document_id)
        if not entry:
            raise KeyError(f"Document {document_id} not found")
        return entry

    def list(self) -> List[DocumentEntry]:
        """Return all entries currently stored in the registry."""
        return list(self._store.values())


_registry: DocumentRegistry | None = None


def get_registry() -> DocumentRegistry:
    """Return the cached singleton registry instance."""
    global _registry
    if _registry is None:
        _registry = DocumentRegistry()
    return _registry
