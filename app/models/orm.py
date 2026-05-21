"""ORM models.

We keep the schema compact – everything we persist is centred on four
entities: ``Project`` (a Web3 protocol to farm), ``Wallet``, ``Strategy``
(planner output for a project+wallet pair), ``Task`` (atomic executable
unit), and ``Report`` (post-run summary).
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED_BY_RISK = "blocked_by_risk"


class TaskKind(str, enum.Enum):
    FAUCET = "faucet"
    QUEST = "quest"
    SWAP = "swap"
    BRIDGE = "bridge"
    CHECKIN = "checkin"
    CUSTOM = "custom"


class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    ABORTED = "aborted"


class StrategyVerdict(str, enum.Enum):
    PROCEED = "proceed"
    SKIP = "skip"
    NEEDS_REVIEW = "needs_review"


class ProjectRiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    chain: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tier: Mapped[ProjectRiskTier] = mapped_column(
        Enum(ProjectRiskTier, name="project_risk_tier"), default=ProjectRiskTier.UNKNOWN
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    strategies: Mapped[list[Strategy]] = relationship(back_populates="project")


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(120), unique=True)
    address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    profile_dir: Mapped[str] = mapped_column(String(500))
    # NEVER write production keys here; this only stores a vault reference.
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tasks: Mapped[list[Task]] = relationship(back_populates="wallet")


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("project_id", "wallet_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    wallet_id: Mapped[int | None] = mapped_column(
        ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, name="strategy_status"), default=StrategyStatus.DRAFT
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # --- Planner evaluation ---
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_gas_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_reward_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verdict: Mapped[StrategyVerdict] = mapped_column(
        Enum(StrategyVerdict, name="strategy_verdict"),
        default=StrategyVerdict.NEEDS_REVIEW,
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="strategies")
    tasks: Mapped[list[Task]] = relationship(back_populates="strategy")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    wallet_id: Mapped[int | None] = mapped_column(
        ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[TaskKind] = mapped_column(Enum(TaskKind, name="task_kind"))
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.PENDING, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    target_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    strategy: Mapped[Strategy] = relationship(back_populates="tasks")
    wallet: Mapped[Wallet | None] = relationship(back_populates="tasks")


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    summary: Mapped[str] = mapped_column(Text)
    tasks_total: Mapped[int] = mapped_column(Integer, default=0)
    tasks_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    earned_usd: Mapped[float] = mapped_column(Float, default=0.0)
    gas_spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    artifacts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
