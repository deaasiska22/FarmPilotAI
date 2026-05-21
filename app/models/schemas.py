"""Pydantic v2 schemas used by the API layer and inter-agent messaging."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.orm import ProjectRiskTier, StrategyStatus, TaskKind, TaskStatus


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class ProjectBase(BaseModel):
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9\-_.]+$")
    name: str = Field(min_length=1, max_length=200)
    url: str
    chain: str = Field(min_length=2, max_length=60)
    description: str | None = None
    risk_tier: ProjectRiskTier = ProjectRiskTier.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------
class WalletBase(BaseModel):
    label: str
    address: str
    profile_dir: str
    secret_ref: str | None = None
    is_active: bool = True
    notes: str | None = None

    @field_validator("address")
    @classmethod
    def _checksum(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("0x") or len(v) != 42:
            raise ValueError("address must be a 0x-prefixed 20-byte hex string")
        return v


class WalletCreate(WalletBase):
    pass


class WalletRead(WalletBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Strategy / Plan
# ---------------------------------------------------------------------------
class PlanItem(BaseModel):
    """A single planned action emitted by the PlannerAgent."""

    kind: TaskKind
    title: str
    target_url: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)


class StrategyBase(BaseModel):
    name: str
    project_id: int
    wallet_id: int | None = None
    status: StrategyStatus = StrategyStatus.DRAFT
    rationale: str | None = None
    plan_json: dict[str, Any] = Field(default_factory=dict)


class StrategyCreate(StrategyBase):
    pass


class StrategyRead(StrategyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------
class TaskBase(BaseModel):
    strategy_id: int
    wallet_id: int | None = None
    kind: TaskKind
    title: str
    target_url: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    pass


class TaskRead(TaskBase):
    id: int
    status: TaskStatus
    attempts: int
    last_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    result_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TaskResult(BaseModel):
    """What an executor returns after running a task."""

    ok: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    earned_usd: float = 0.0
    gas_spent_usd: float = 0.0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
class ReportRead(BaseModel):
    id: int
    strategy_id: int
    summary: str
    tasks_total: int
    tasks_succeeded: int
    tasks_failed: int
    earned_usd: float
    gas_spent_usd: float
    artifacts_json: dict[str, Any]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
