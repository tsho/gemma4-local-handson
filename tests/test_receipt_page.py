"""Verify routing and assets for the receipt workspace."""

from fastapi import testclient

import gemma_demo.config
import gemma_demo.main


def test_receipt_workspace_and_navigation():
    """Serve the new UI alongside the existing chat without inference."""
    with testclient.TestClient(
        gemma_demo.main.create_app(gemma_demo.config.Settings(_env_file=None))
    ) as client:
        page = client.get("/receipts")
        assert page.status_code == 200
        for field in ("store", "category", "amount", "items", "copy", "save"):
            assert f'id="{field}"' in page.text
        assert 'href="/receipts"' in client.get("/").text
        for asset in ("receipts.js", "receipts-core.mjs", "receipts.css"):
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200
            if asset.endswith("mjs"):
                assert "javascript" in response.headers["content-type"]
