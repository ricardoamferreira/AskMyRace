from __future__ import annotations

from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from backend.app.config import get_settings
from backend.app.services.document_registry import Chunk

SYSTEM_PROMPT = (
    "You are a concise triathlon race assistant. Answer questions using only the provided context. "
    "If the answer is not contained in the context, respond with \"I couldn't find that in the athlete guide.\" "
    "Always include citations for each statement in the format [Section - p.X]. "
    "Synthesize the key facts (times, locations, requirements) in your own words instead of copying large blocks of text."
)


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "Context:\n{context}\n\nQuestion: {question}\n",
        ),
    ]
)


def answer_question(question: str, top_chunks: List[Chunk]) -> str:
    if not top_chunks:
        return "I couldn't find that in the athlete guide."

    context_blocks = []
    for chunk in top_chunks:
        context_blocks.append(
            f"Section: {chunk.section}\nPage: {chunk.page}\nExcerpt: {chunk.text}"
        )
    context_text = "\n---\n".join(context_blocks)

    settings = get_settings()
    llm = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.chat_model,
        temperature=1,
    )
    chain = prompt | llm
    response = chain.invoke(
        {
            "context": context_text,
            "question": question,
        }
    )
    return response.content
