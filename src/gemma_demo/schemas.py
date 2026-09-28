from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[Message] = Field(min_length=1, max_length=40)
    system_prompt: str = Field(
        default="あなたは親切なアシスタントです。日本語で簡潔かつ正確に答えてください。",
        max_length=4000,
    )
    temperature: float = Field(default=1.0, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    seed: int = Field(default=42, ge=0, le=2147483647)

    @model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("最後のメッセージはuserにしてください。")
        if sum(len(message.content) for message in self.messages) > 60000:
            raise ValueError("会話が長すぎます。新しい会話を始めてください。")
        return self
