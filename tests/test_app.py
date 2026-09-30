import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gemma_demo.config import Settings
from gemma_demo.inference import InferenceClient, sse_data
from gemma_demo.main import create_app
from gemma_demo.schemas import ChatRequest


def configured(**kwargs):
    return Settings(
        _env_file=None, base_url="http://inference.test/v1", **kwargs
    )


def events(response):
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_chat_stream_and_usage():
    def upstream(request):
        assert str(request.url) == "http://inference.test/v1/chat/completions"
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        assert body["seed"] == 7
        assert body["stream_options"]["include_usage"]
        assert body["model"] == "gemma4"
        assert request.headers["authorization"] == "Bearer test-secret"
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "hidden"}}]},
            {"choices": [{"delta": {"content": "こんにちは"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {
                "choices": [],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
            },
        ]
        text = (
            ": keep-alive\r\n\r\n"
            + "".join(
                "data: " + json.dumps(chunk) + "\r\n\r\n" for chunk in chunks
            )
            + "data: [DONE]\r\n\r\n"
        )
        return httpx.Response(200, text=text)

    app = create_app(
        configured(api_key="test-secret"), httpx.MockTransport(upstream)
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "こんにちは"}],
                "seed": 7,
            },
        )
        data = events(response)
        assert [event["type"] for event in data] == ["start", "delta", "done"]
        assert data[1]["text"] == "こんにちは"
        assert data[-1]["metrics"]["usage"]["completion_tokens"] == 3
        assert data[-1]["metrics"]["first_content_ms"] >= 0
        assert "hidden" not in response.text
        assert "test-secret" not in response.text
        assert not app.state.generation_lock.locked()


@pytest.mark.parametrize(
    "failure", ["connect", "timeout", "http", "truncated", "invalid"]
)
def test_upstream_errors_release_lock(failure):
    def upstream(request):
        if failure == "connect":
            raise httpx.ConnectError("secret internal URL", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret internal URL", request=request)
        if failure == "http":
            return httpx.Response(400, text="secret internal URL")
        if failure == "invalid":
            return httpx.Response(200, text="data: not-json\n\n")
        return httpx.Response(200, text='data: {"choices": []}\n\n')

    app = create_app(configured(), httpx.MockTransport(upstream))
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert events(response)[-1]["type"] == "error"
            assert "secret internal URL" not in response.text
            assert not app.state.generation_lock.locked()


@pytest.mark.parametrize("model,expected", [("gemma4", 200), ("other", 503)])
def test_health_checks_configured_model(model, expected):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": model}]})
    )
    with TestClient(create_app(configured(), transport)) as client:
        assert client.get("/api/health").status_code == expected
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "hi"}]},
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 9000},
        {"messages": [{"role": "user", "content": "hi"}], "temperature": -1},
    ],
)
def test_invalid_input_never_reaches_inference(body):
    def upstream(request):
        pytest.fail("invalid input must not reach the backend")

    with TestClient(
        create_app(configured(), httpx.MockTransport(upstream))
    ) as client:
        assert client.post("/api/chat", json=body).status_code == 422


def test_busy_request_rejected():
    app = create_app(configured())
    with TestClient(app) as client:
        client.portal.call(app.state.generation_lock.acquire)
        try:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert response.status_code == 429
        finally:
            client.portal.call(app.state.generation_lock.release)


def test_cancellation_closes_upstream():
    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'data: {"choices": [{"delta": {"content": "a"}}]}\n\n'
            await asyncio.sleep(60)

        async def aclose(self):
            self.closed = True

    async def scenario():
        stream = SlowStream()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, stream=stream)
        )
        async with httpx.AsyncClient(
            base_url="http://inference.test/v1/", transport=transport
        ) as http:
            inference = InferenceClient(configured(), http)
            request = ChatRequest(messages=[{"role": "user", "content": "hi"}])
            generator = inference.generate(request)
            assert (await anext(generator))["type"] == "start"
            assert (await anext(generator))["type"] == "delta"
            task = asyncio.create_task(anext(generator))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stream.closed

    asyncio.run(scenario())


def test_multiline_sse():
    async def scenario():
        response = httpx.Response(
            200, text=':comment\n\ndata: {"x":\ndata: 1}\n\n'
        )
        assert [json.loads(item) async for item in sse_data(response)] == [
            {"x": 1}
        ]

    asyncio.run(scenario())
