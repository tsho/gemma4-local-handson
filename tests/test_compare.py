"""Tests for benchmark startup diagnostics."""

import asyncio
import pathlib
import runpy

import httpx
import pytest


@pytest.mark.parametrize("state", ["unreachable", "unavailable", "ready"])
def test_health_diagnostics(state):
    """Distinguish app connection failures from inference unavailability."""
    script = (
        pathlib.Path(__file__).resolve().parents[1] / "benchmarks/compare.py"
    )
    check_health = runpy.run_path(str(script))["check_health"]

    def upstream(request):
        if state == "unreachable":
            raise httpx.ConnectError("refused", request=request)
        if state == "unavailable":
            return httpx.Response(503, json={"ready": False})
        return httpx.Response(200, json={"ready": True, "model": "gemma4"})

    async def scenario():
        async with httpx.AsyncClient(
            base_url="http://app.test:8000",
            transport=httpx.MockTransport(upstream),
        ) as client:
            if state == "ready":
                assert await check_health(client) == {
                    "ready": True,
                    "model": "gemma4",
                }
            else:
                command = (
                    "serve_app.sh"
                    if state == "unreachable"
                    else "serve_llamacpp.sh"
                )
                with pytest.raises(RuntimeError, match=command):
                    await check_health(client)

    asyncio.run(scenario())
