from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.container import set_container
from app.main import create_app


@pytest.mark.asyncio
async def test_healthz_and_basic_routes(container):
    set_container(container)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = await client.post(
            "/api/v1/projects",
            json={
                "slug": "demo",
                "name": "Demo",
                "url": "https://demo.example",
                "chain": "ethereum",
                "tags": ["faucet"],
                "risk_tier": "low",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "demo"

        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
