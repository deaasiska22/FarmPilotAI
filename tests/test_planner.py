from __future__ import annotations

import pytest

from app.ai.reasoner import HeuristicReasoner
from app.ai.strategy import StrategySynthesiser


@pytest.mark.asyncio
async def test_heuristic_planner_returns_items():
    synth = StrategySynthesiser(HeuristicReasoner())
    rationale, items = await synth.design(
        project={
            "name": "Sample",
            "slug": "sample",
            "url": "https://example.com",
            "chain": "ethereum",
            "risk_tier": "low",
            "tags": ["faucet"],
            "description": "Demo",
        },
        wallet_address="0x" + "1" * 40,
        wallet_liquidity=0.0,
        max_usd=25.0,
        dry_run=True,
    )
    assert rationale
    assert len(items) >= 1
    assert all(0.0 <= it.risk_score <= 1.0 for it in items)
