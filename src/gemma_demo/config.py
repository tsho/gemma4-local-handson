from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GEMMA_", env_file=".env", extra="ignore"
    )

    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "gemma4"
    backend: Literal["llama.cpp", "vllm"] = "llama.cpp"
    api_key: str = ""
    timeout_seconds: float = Field(default=180, gt=0)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        return value.rstrip("/")
