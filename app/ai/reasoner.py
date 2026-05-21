"""Provider-agnostic reasoning client.

Two implementations:

* :class:`HeuristicReasoner` – deterministic, no network. Used as the default
  so the rest of the system has zero hard dependencies on an LLM API.
* :class:`RemoteReasoner` – thin async wrapper over the official
  :mod:`openai` / :mod:`anthropic` SDKs, selected via ``AI_PROVIDER``.

The interface is :meth:`generate_json` – callers always parse a JSON object.
"""
from __future__ import annotations

import abc
import json
from typing import Any

from app.config import AISettings
from app.core.logging import get_logger

logger = get_logger("ai.reasoner")


class BaseReasoner(abc.ABC):
    @abc.abstractmethod
    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Deterministic fallback (no external API calls)
# ---------------------------------------------------------------------------
class HeuristicReasoner(BaseReasoner):
    """Returns plausible, rule-based JSON. Used in tests and when AI is off."""

    async def generate_json(
        self, *, system: str, user: str, schema_hint: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        logger.debug("ai.heuristic_reasoner", system_chars=len(system), user_chars=len(user))
        # Detect "planner" vs "risk" prompts by sniffing the system message.
        if "risk analyst" in system.lower():
            return {"approved": True, "risk_score": 0.2, "reason": "heuristic default"}
        # Planner default: faucet + checkin + light quest.
        return {
            "rationale": "Heuristic plan: prioritise zero-cost actions before any signing.",
            "items": [
                {
                    "kind": "faucet",
                    "title": "Claim testnet faucet",
                    "target_url": None,
                    "params": {},
                    "rationale": "Risk-free, primes the wallet for further interactions.",
                    "risk_score": 0.05,
                },
                {
                    "kind": "checkin",
                    "title": "Daily check-in",
                    "target_url": None,
                    "params": {},
                    "rationale": "Anti-sybil pattern – consistent daily engagement.",
                    "risk_score": 0.05,
                },
                {
                    "kind": "quest",
                    "title": "Complete first social quest",
                    "target_url": None,
                    "params": {},
                    "rationale": "Cheap reputation builder; no on-chain signing.",
                    "risk_score": 0.15,
                },
            ],
        }


# ---------------------------------------------------------------------------
# Remote provider
# ---------------------------------------------------------------------------
class RemoteReasoner(BaseReasoner):
    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        if not settings.api_key:
            raise ValueError("AI_API_KEY is required for remote reasoner")

    async def generate_json(
        self, *, system: str, user: str, schema_hint: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.settings.provider == "openai":
            return await self._openai(system, user)
        if self.settings.provider == "anthropic":
            return await self._anthropic(system, user)
        raise ValueError(f"unsupported AI provider: {self.settings.provider}")

    # -- providers --------------------------------------------------------
    async def _openai(self, system: str, user: str) -> dict[str, Any]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.api_key)
        resp = await client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        return _safe_load_json(content)

    async def _anthropic(self, system: str, user: str) -> dict[str, Any]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.settings.api_key)
        resp = await client.messages.create(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            temperature=self.settings.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # anthropic returns a list of content blocks
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _safe_load_json(text)


def _safe_load_json(s: str) -> dict[str, Any]:
    s = s.strip()
    if s.startswith("```"):
        # strip fences (```json ... ``` or ``` ... ```)
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # last-ditch: find the first {...} block
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start : end + 1])
        raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_reasoner(settings: AISettings) -> BaseReasoner:
    if settings.provider == "none" or not settings.api_key:
        logger.info("ai.reasoner.heuristic_selected")
        return HeuristicReasoner()
    logger.info("ai.reasoner.remote_selected", provider=settings.provider, model=settings.model)
    return RemoteReasoner(settings)
