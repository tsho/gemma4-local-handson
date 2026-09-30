import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from gemma_demo.config import Settings
from gemma_demo.inference import InferenceClient, InferenceError
from gemma_demo.schemas import ChatRequest

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        headers = (
            {"Authorization": f"Bearer {settings.api_key}"}
            if settings.api_key
            else {}
        )
        async with httpx.AsyncClient(
            base_url=settings.base_url + "/",
            headers=headers,
            timeout=httpx.Timeout(settings.timeout_seconds, connect=5),
            trust_env=False,
            transport=transport,
        ) as client:
            app.state.inference = InferenceClient(settings, client)
            app.state.generation_lock = asyncio.Lock()
            yield

    app = FastAPI(title="Gemma Local Playground", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    async def health():
        ready = await app.state.inference.available()
        return JSONResponse(
            {
                "ready": ready,
                "backend": settings.backend,
                "model": settings.model,
                "message": "接続済み"
                if ready
                else "推論サーバー未接続、またはモデル名が不一致です。",
            },
            status_code=200 if ready else 503,
        )

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        # With one event loop, the unlocked acquire completes without yielding.
        # Reject concurrent requests instead of silently building a long queue.
        lock = app.state.generation_lock
        if lock.locked():
            return JSONResponse(
                {
                    "detail": (
                        "生成中です。完了または停止後に再実行してください。"
                    )
                },
                429,
            )
        await lock.acquire()

        async def events():
            try:
                async for event in app.state.inference.generate(body):
                    yield (
                        "data: "
                        + json.dumps(event, ensure_ascii=False)
                        + "\n\n"
                    )
            except InferenceError as exc:
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": str(exc)})
                    + "\n\n"
                )
            finally:
                lock.release()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
