from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    chat_model: str = Field(
        default="gpt-4o-mini",
        env="ASK_MY_RACE_CHAT_MODEL",
        description="OpenAI chat model used for answering questions.",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        env="ASK_MY_RACE_EMBEDDING_MODEL",
        description="OpenAI embedding model used for vectorizing chunks.",
    )
    top_k: int = Field(
        default=5,
        env="ASK_MY_RACE_TOP_K",
        description="Number of anchor chunks retrieved per question",
    )


def get_settings() -> Settings:
    return Settings()
