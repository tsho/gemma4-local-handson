"""Small OpenAI-compatible streaming client. No cloud SDK is required."""

import json
from collections.abc import AsyncIterator
from time import perf_counter

import httpx

from gemma_demo.config import Settings
from gemma_demo.schemas import ChatRequest


class InferenceError(Exception):
    pass


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


class InferenceClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http

    async def available(self) -> bool:
        try:
            response = await self.http.get("models", timeout=3)
            response.raise_for_status()
            return any(
                model.get("id") == self.settings.model
                for model in response.json().get("data", [])
            )
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return False

    async def generate(self, request: ChatRequest) -> AsyncIterator[dict]:
        messages = [message.model_dump() for message in request.messages]
        if request.system_prompt:
            messages.insert(
                0, {"role": "system", "content": request.system_prompt}
            )
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "seed": request.seed,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        started = perf_counter()
        first_content_ms = None
        usage = None
        finish_reason = None
        completed = False
        try:
            async with self.http.stream(
                "POST", "chat/completions", json=payload
            ) as response:
                if response.status_code >= 400:
                    if response.status_code == 400:
                        raise InferenceError(
                            "推論サーバーが入力を受け付けませんでした。"
                            "会話長・生成上限・サーバーログを確認してください。"
                        )
                    raise InferenceError(
                        f"推論サーバーがHTTP {response.status_code}"
                        "を返しました。"
                    )
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
                                        perf_counter() - started
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
                        "total_ms": round((perf_counter() - started) * 1000, 1),
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
