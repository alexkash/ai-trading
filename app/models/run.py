from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_instance_id: Mapped[int] = mapped_column(ForeignKey("bot_instances.id"), nullable=False)

    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.pending, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
