"""Small OpenAI-compatible streaming client. No cloud SDK is required."""

import json
import time
from collections.abc import AsyncIterator

import httpx

from gemma_demo import config, schemas


class InferenceError(Exception):
    """An inference failure that can be displayed to the user."""


async def sse_data(response: httpx.Response) -> AsyncIterator[str]:
    """Parse event boundaries, including multi-line data and CRLF responses."""
    lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if lines:
                yield "\n".join(lines)
                lines = []
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
    if lines:
        yield "\n".join(lines)


def message_payload(message: schemas.Message) -> dict:
    """Convert an app message to text or OpenAI-compatible content parts."""
    content = message.content
    if message.images:
        content = [{"type": "text", "text": message.content}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image}}
            for image in message.images
        )
    return {"role": message.role, "content": content}


def conversation_payload(request: schemas.ChatRequest) -> list[dict]:
    """Prepend the system prompt to converted conversation messages."""
    messages = [message_payload(message) for message in request.messages]
    if request.system_prompt:
        messages.insert(0, {"role": "system", "content": request.system_prompt})
    return messages


def check_response(response: httpx.Response) -> None:
    """Raise a user-facing error for rejected inference requests."""
    if response.status_code == 400:
        raise InferenceError(
            "推論サーバーが入力を受け付けませんでした。"
            "画像付きの場合は画像対応モデルとmmprojの読み込み、"
            "会話長・生成上限・サーバーログを確認してください。"
        )
    if response.status_code >= 400:
        raise InferenceError(
            f"推論サーバーがHTTP {response.status_code}を返しました。"
        )


class InferenceClient:
    """Stream text responses from a local multimodal inference server."""

    def __init__(self, settings: config.Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http

    async def available(self) -> bool:
        """Return whether the configured model is advertised by the server."""
        try:
            response = await self.http.get("models", timeout=3)
            response.raise_for_status()
            return any(
                model.get("id") == self.settings.model
                for model in response.json().get("data", [])
            )
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return False

    async def generate(
        self, request: schemas.ChatRequest
    ) -> AsyncIterator[dict]:
        """Yield response text and metrics, translating transport failures."""
        payload = {
            "model": self.settings.model,
            "messages": conversation_payload(request),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "seed": request.seed,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        started = time.perf_counter()
        first_content_ms = None
        usage = None
        finish_reason = None
        completed = False
        try:
            async with self.http.stream(
                "POST", "chat/completions", json=payload
            ) as response:
                check_response(response)
                yield {"type": "start", "model": self.settings.model}
                async for data in sse_data(response):
                    if data == "[DONE]":
                        completed = True
                        break
                    try:
                        chunk = json.loads(data)
                        if "error" in chunk:
                            raise InferenceError(
                                "推論サーバーで生成エラーが発生しました。"
                            )
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        for choice in chunk.get("choices", []):
                            content = choice.get("delta", {}).get("content")
                            if content:
                                if not isinstance(content, str):
                                    raise ValueError("non-text content")
                                if first_content_ms is None:
                                    first_content_ms = (
                                        time.perf_counter() - started
                                    ) * 1000
                                yield {"type": "delta", "text": content}
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise InferenceError(
                            "推論サーバーの応答形式を解釈できませんでした。"
                        ) from exc
                if not completed:
                    raise InferenceError(
                        "回答の受信中に接続が終了しました。再実行してください。"
                    )
                yield {
                    "type": "done",
                    "metrics": {
                        "first_content_ms": first_content_ms,
                        "total_ms": round(
                            (time.perf_counter() - started) * 1000, 1
                        ),
                        "usage": usage,
                        "finish_reason": finish_reason,
                    },
                }
        except httpx.TimeoutException as exc:
            raise InferenceError(
                "推論がタイムアウトしました。生成上限またはタイムアウト設定を見直してください。"
            ) from exc
        except httpx.HTTPError as exc:
            raise InferenceError(
                "推論サーバーに接続できません。起動状態とGEMMA_BASE_URLを確認してください。"
            ) from exc
