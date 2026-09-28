"""Run sequential, reproducible requests against the local FastAPI app."""

import argparse
import asyncio
import datetime
import json
import pathlib

import httpx

from gemma_demo import inference


async def check_health(client: httpx.AsyncClient) -> dict:
    """Check whether the app and its inference server are ready.

    Args:
        client: HTTP client configured with the app's base URL.

    Returns:
        Server metadata for the comparison report.

    Raises:
        RuntimeError: The app is unreachable or inference is unavailable.
        httpx.HTTPError: Another HTTP failure occurs.
    """
    try:
        response = await client.get("/api/health", timeout=5)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"アプリに接続できません: {client.base_url}\n"
            "別ターミナルで bash scripts/serve_app.sh を実行してください。\n"
            "ポートを変更した場合は --url でアプリのURLを指定してください。"
        ) from exc
    if response.status_code == 503:
        raise RuntimeError(
            "アプリには接続できましたが、推論サーバーが未接続です。\n"
            "Macでは別ターミナルで bash scripts/serve_llamacpp.sh を実行し、"
            "モデルのロード完了を待ってください。\n"
            "起動済みなら GEMMA_BASE_URL と GEMMA_MODEL を確認してください。"
        )
    response.raise_for_status()
    return response.json()


async def main(args):
    examples = json.loads(pathlib.Path(args.prompts).read_text())
    runs = []
    async with httpx.AsyncClient(
        base_url=args.url, timeout=300, trust_env=False
    ) as client:
        metadata = await check_health(client)
        for temperature in args.temperatures:
            for example in examples:
                request = {
                    "messages": [
                        {"role": "user", "content": example["prompt"]}
                    ],
                    "temperature": temperature,
                    "seed": args.seed,
                    "max_tokens": args.max_tokens,
                }
                run = {
                    "example": example["id"],
                    "request": request,
                    "output": "",
                    "created_at": datetime.datetime.now(
                        datetime.UTC
                    ).isoformat(),
                }
                completed = False
                async with client.stream(
                    "POST", "/api/chat", json=request
                ) as response:
                    response.raise_for_status()
                    async for raw in inference.sse_data(response):
                        event = json.loads(raw)
                        if event["type"] == "error":
                            raise RuntimeError(event["message"])
                        if event["type"] == "delta":
                            run["output"] += event["text"]
                        if event["type"] == "done":
                            run["metrics"] = event["metrics"]
                            completed = True
                if not completed:
                    raise RuntimeError("Incomplete event stream")
                runs.append(run)
                print(
                    f"{example['id']} temperature={temperature}: "
                    f"{run['metrics']}"
                )
                output = pathlib.Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(
                        {"server": metadata, "runs": runs},
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompts", default="examples/prompts.json")
    parser.add_argument(
        "--temperatures", nargs="+", type=float, default=[0.2, 1.0]
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--output", default="results/comparison.json")
    try:
        asyncio.run(main(parser.parse_args()))
    except (httpx.HTTPError, RuntimeError) as exc:
        parser.exit(1, f"比較を中止しました: {exc}\n")
