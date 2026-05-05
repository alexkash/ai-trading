from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BotStatus(str, enum.Enum):
    idle = "idle"
    live = "live"
    backtesting = "backtesting"
    paused = "paused"
    error = "error"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BotInstance(Base):
    __tablename__ = "bot_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    primary_tf: Mapped[str] = mapped_column(String(8), nullable=False)
    extra_tfs: Mapped[list[str]] = mapped_column(JSON, default=list)
    bot_params: Mapped[dict] = mapped_column(JSON, default=dict)
    instance_config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[BotStatus] = mapped_column(
        Enum(BotStatus), default=BotStatus.idle, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    balance: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
