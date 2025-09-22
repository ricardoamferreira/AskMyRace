from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    chat_model: str = Field(
        default="gpt-4o-mini",
        alias="ASK_MY_RACE_CHAT_MODEL",
        description="OpenAI chat model used for answering questions.",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="ASK_MY_RACE_EMBEDDING_MODEL",
        description="OpenAI embedding model used for vectorizing chunks.",
    )
    top_k: int = Field(
        default=3,
        alias="ASK_MY_RACE_TOP_K",
        description="Number of chunks retrieved per question.",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
