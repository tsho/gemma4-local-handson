"""Verify a running app and model, including cancellation and reuse."""

import asyncio
import json

import httpx

from gemma_demo.inference import sse_data


async def main():
    report = {}
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=180, trust_env=False
    ) as client:
        health = await client.get("/api/health")
        health.raise_for_status()
        report["health"] = health.json()
        assert report["health"]["ready"]
        page = await client.get("/")
        assert page.status_code == 200 and 'id="chat-form"' in page.text

        async def generate(content, max_tokens=80):
            output = ""
            metrics = None
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                },
            ) as response:
                response.raise_for_status()
                async for raw in sse_data(response):
                    event = json.loads(raw)
                    assert event["type"] != "error", event
                    if event["type"] == "delta":
                        output += event["text"]
                    if event["type"] == "done":
                        metrics = event["metrics"]
            assert output.strip() and metrics, (output, metrics)
            return {"output": output, "metrics": metrics}

        report["japanese"] = await generate(
            "こんにちは。日本語で短く自己紹介してください。"
        )
        print(json.dumps(report["japanese"], ensure_ascii=False), flush=True)

        async with client.stream(
            "POST",
            "/api/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "1から1000までの整数をすべて列挙してください。"
                        ),
                    }
                ],
                "max_tokens": 4096,
            },
        ) as response:
            response.raise_for_status()
            async for raw in sse_data(response):
                event = json.loads(raw)
                assert event["type"] != "error", event
                if event["type"] == "delta":
                    busy = await client.post(
                        "/api/chat",
                        json={
                            "messages": [{"role": "user", "content": "test"}],
                        },
                    )
                    assert busy.status_code == 429, busy.text
                    report["concurrent_request"] = 429
                    break
        await asyncio.sleep(1)
        report["after_cancel"] = await generate(
            "2足す3は？数字だけで答えてください。", 16
        )
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
