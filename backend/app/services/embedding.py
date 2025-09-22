from __future__ import annotations

from typing import Iterable, List

import numpy as np
from langchain_openai import OpenAIEmbeddings

from backend.app.config import get_settings


def embed_chunks(texts: Iterable[str]) -> List[np.ndarray]:
    settings = get_settings()
    embeddings = OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
    ).embed_documents(list(texts))
    return [np.array(vector, dtype="float32") for vector in embeddings]


def embed_query(text: str) -> np.ndarray:
    settings = get_settings()
    vector = OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
    ).embed_query(text)
    return np.array(vector, dtype="float32")
