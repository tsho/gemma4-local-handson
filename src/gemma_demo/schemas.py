"""Validate text and local image inputs before contacting inference."""

import base64
import binascii
from typing import Literal

import pydantic

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def validate_image(value: str) -> str:
    """Validate a bounded image data URL without fetching remote resources."""
    header, separator, encoded = value.partition(",")
    allowed = {
        "data:image/png;base64": lambda data: data.startswith(
            b"\x89PNG\r\n\x1a\n"
        ),
        "data:image/jpeg;base64": lambda data: data.startswith(b"\xff\xd8\xff"),
        "data:image/webp;base64": lambda data: (
            data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        ),
    }
    if header not in allowed or not separator:
        raise ValueError("画像はPNG/JPEG/WebPのdata URLを指定してください。")
    if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError("画像は5MB以下にしてください。")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("画像のBase64が不正です。") from exc
    if len(data) > MAX_IMAGE_BYTES or not allowed[header](data):
        raise ValueError("画像の形式またはサイズが不正です。")
    return value


class Message(pydantic.BaseModel):
    """A text message with an optional user image."""

    model_config = pydantic.ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = pydantic.Field(min_length=1, max_length=20000)
    images: list[str] = pydantic.Field(default_factory=list, max_length=1)

    @pydantic.model_validator(mode="after")
    def validate_images(self) -> "Message":
        """Allow only bounded, embedded images on user messages."""
        if self.images and self.role != "user":
            raise ValueError("画像はuserメッセージにのみ添付できます。")
        for image in self.images:
            validate_image(image)
        return self


class ChatRequest(pydantic.BaseModel):
    """Generation settings and a bounded conversation."""

    model_config = pydantic.ConfigDict(extra="forbid")
    messages: list[Message] = pydantic.Field(min_length=1, max_length=40)
    system_prompt: str = pydantic.Field(
        default="あなたは親切なアシスタントです。日本語で簡潔かつ正確に答えてください。",
        max_length=4000,
    )
    temperature: float = pydantic.Field(default=1.0, ge=0, le=2)
    top_p: float = pydantic.Field(default=0.95, gt=0, le=1)
    max_tokens: int = pydantic.Field(default=512, ge=1, le=4096)
    seed: int = pydantic.Field(default=42, ge=0, le=2147483647)

    @pydantic.model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        """Bound text and image history and require a final user turn."""
        if sum(len(message.images) for message in self.messages) > 4:
            raise ValueError(
                "画像は会話全体で4枚までです。新しい会話を始めてください。"
            )
        if self.messages[-1].role != "user":
            raise ValueError("最後のメッセージはuserにしてください。")
        if sum(len(message.content) for message in self.messages) > 60000:
            raise ValueError("会話が長すぎます。新しい会話を始めてください。")
        return self
