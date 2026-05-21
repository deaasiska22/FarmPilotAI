"""Web3 project scanner.

The scanner takes a URL (or list of URLs) and produces :class:`ProjectCreate`
records. The first cut uses simple HTTP scraping + heuristics (chain, tags,
known platforms). An LLM is consulted to fill in the description and tag
list when the heuristics come up empty.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

import httpx

from app.agents.base import BaseAgent
from app.ai.reasoner import BaseReasoner
from app.core.exceptions import RetryableError
from app.models.orm import ProjectRiskTier
from app.models.schemas import ProjectCreate

_CHAIN_HINTS = {
    "ethereum": ["ethereum", "eth ", "mainnet"],
    "arbitrum": ["arbitrum", "arb "],
    "optimism": ["optimism", "op stack"],
    "base": ["base ", "coinbase l2", "base network"],
    "polygon": ["polygon", "matic"],
    "solana": ["solana"],
    "linea": ["linea"],
    "scroll": ["scroll"],
    "zksync": ["zksync", "zk sync"],
}

_FAUCET_RE = re.compile(r"faucet", re.I)
_QUEST_RE = re.compile(r"(quest|galxe|zealy|crew3|task)", re.I)


def _detect_chain(text: str) -> str:
    lower = text.lower()
    for chain, hints in _CHAIN_HINTS.items():
        if any(h in lower for h in hints):
            return chain
    return "ethereum"


def _detect_tags(text: str) -> list[str]:
    tags: list[str] = []
    if _FAUCET_RE.search(text):
        tags.append("faucet")
    if _QUEST_RE.search(text):
        tags.append("quests")
    if "testnet" in text.lower():
        tags.append("testnet")
    if "airdrop" in text.lower():
        tags.append("airdrop")
    if "swap" in text.lower():
        tags.append("dex")
    if "bridge" in text.lower():
        tags.append("bridge")
    return tags


def _slugify(url: str) -> str:
    host = urlparse(url).hostname or url
    host = host.replace("www.", "")
    return re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "project"


class ScannerAgent(BaseAgent):
    name = "scanner"

    def __init__(self, reasoner: BaseReasoner, http_timeout_s: float = 12.0) -> None:
        super().__init__()
        self.reasoner = reasoner
        self.http_timeout_s = http_timeout_s

    async def run(self, urls: Iterable[str]) -> list[ProjectCreate]:  # type: ignore[override]
        out: list[ProjectCreate] = []
        async with httpx.AsyncClient(
            timeout=self.http_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "FarmPilotAI/0.1"},
        ) as http:
            for url in urls:
                try:
                    project = await self._scan_one(http, url)
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    self.log.warning("scanner.fetch_failed", url=url, error=str(exc))
                    raise RetryableError(f"scanner fetch failed: {url}") from exc
                if project is not None:
                    out.append(project)
        return out

    async def _scan_one(self, http: httpx.AsyncClient, url: str) -> ProjectCreate | None:
        resp = await http.get(url)
        resp.raise_for_status()
        body = resp.text[:50_000]   # cap so a misbehaving site can't blow memory
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        title = (title_match.group(1).strip() if title_match else _slugify(url))[:200]
        slug = _slugify(url)
        chain = _detect_chain(title + " " + body)
        tags = _detect_tags(title + " " + body)
        risk = ProjectRiskTier.LOW if "testnet" in tags else ProjectRiskTier.MEDIUM
        # Trim description to a leading paragraph if present
        desc_match = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\'](.+?)["\']', body, re.I
        )
        description = desc_match.group(1)[:600] if desc_match else None

        project = ProjectCreate(
            slug=slug,
            name=title,
            url=url,
            chain=chain,
            description=description,
            risk_tier=risk,
            tags=tags,
            metadata_json={"source": "scanner.v1"},
        )
        self.log.info("scanner.project_extracted", slug=slug, chain=chain, tags=tags)
        return project
