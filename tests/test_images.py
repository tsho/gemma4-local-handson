"""Image validation and multimodal payload integration tests."""

import base64
import json

import httpx
import pytest
from fastapi import testclient

from gemma_demo import config, main, schemas

PNG = (
    "data:image/png;base64,"
    + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"test").decode()
)


def test_image_and_text_forwarded_with_history():
    """Keep image context and translate attachments to content parts."""

    def upstream(request):
        messages = json.loads(request.content)["messages"]
        assert messages[1]["content"] == [
            {"type": "text", "text": "Describe this"},
            {"type": "image_url", "image_url": {"url": PNG}},
        ]
        assert messages[-1] == {"role": "user", "content": "What color?"}
        assert all("images" not in message for message in messages)
        return httpx.Response(200, text="data: [DONE]\n\n")

    app = main.create_app(
        config.Settings(_env_file=None), httpx.MockTransport(upstream)
    )
    with testclient.TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Describe this",
                        "images": [PNG],
                    },
                    {"role": "assistant", "content": "A shape"},
                    {"role": "user", "content": "What color?"},
                ]
            },
        )
    assert response.status_code == 200
    assert '"type": "done"' in response.text


@pytest.mark.parametrize(
    "images",
    [
        ["https://example.com/image.png"],
        ["data:image/svg+xml;base64,PHN2Zz4="],
        ["data:image/png;base64,!!!"],
        ["data:image/jpeg;base64,aGVsbG8="],
        [PNG, PNG],
        ["data:image/png;base64," + "A" * (7 * 1024 * 1024)],
    ],
)
def test_invalid_images_rejected(images):
    """Reject unsupported, remote, oversized and malformed images."""
    with pytest.raises(ValueError):
        schemas.Message(role="user", content="test", images=images)


def test_assistant_images_and_excessive_history_rejected():
    """Enforce image limits across the whole conversation."""
    with pytest.raises(ValueError):
        schemas.Message(role="assistant", content="test", images=[PNG])
    with pytest.raises(ValueError):
        schemas.ChatRequest(
            messages=[{"role": "user", "content": "test", "images": [PNG]}] * 5
        )
