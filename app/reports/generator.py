"""Report generator – renders DB rows into a markdown digest."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.container import Container
from app.db.repositories.report_repo import ReportRepository
from app.db.repositories.strategy_repo import StrategyRepository
from app.models.orm import Task, TaskStatus


class ReportGenerator:
    def __init__(self, container: Container, out_dir: Path | None = None) -> None:
        self.container = container
        self.out_dir = out_dir or container.settings.project_root / "reports" / "output"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    async def render_markdown(self, strategy_id: int) -> str:
        async with self.container.db.session() as session:
            strategies = StrategyRepository(session)
            reports = ReportRepository(session)
            strat = await strategies.get(strategy_id)
            if strat is None:
                raise ValueError(f"unknown strategy id {strategy_id}")
            stmt = (
                select(Task)
                .where(Task.strategy_id == strategy_id)
                .order_by(Task.id.asc())
            )
            all_tasks = list((await session.execute(stmt)).scalars().all())
            report = await reports.latest_for_strategy(strategy_id)

        lines: list[str] = []
        lines.append(f"# FarmPilot report – strategy `{strat.name}`")
        lines.append(f"_generated: {datetime.utcnow().isoformat()}Z_")
        lines.append("")
        lines.append(f"- status: **{strat.status.value}**")
        if report:
            lines += [
                f"- tasks: {report.tasks_succeeded}/{report.tasks_total} succeeded",
                f"- earned (USD): {report.earned_usd:.4f}",
                f"- gas (USD): {report.gas_spent_usd:.4f}",
            ]
        lines.append("")
        lines.append("## Plan rationale")
        lines.append(strat.rationale or "_(no rationale recorded)_")
        lines.append("")
        lines.append("## Tasks")
        if not all_tasks:
            lines.append("_(no tasks)_")
        for t in all_tasks:
            icon = {
                TaskStatus.SUCCEEDED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.SKIPPED: "⏭️",
                TaskStatus.BLOCKED_BY_RISK: "🛑",
                TaskStatus.PENDING: "⏳",
                TaskStatus.RUNNING: "▶️",
            }.get(t.status, "·")
            lines.append(f"- {icon} `{t.kind.value}` – {t.title}  (status={t.status.value})")
            if t.last_error:
                lines.append(f"    - error: `{t.last_error[:200]}`")
        return "\n".join(lines) + "\n"

    async def save_markdown(self, strategy_id: int) -> Path:
        md = await self.render_markdown(strategy_id)
        out = self.out_dir / f"strategy-{strategy_id}.md"
        out.write_text(md, encoding="utf-8")
        return out
