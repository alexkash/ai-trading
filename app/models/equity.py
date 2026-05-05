from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EquityPoint(Base):
    __tablename__ = "equity_points"
    __table_args__ = (
        Index("ix_equity_bot_run_ts", "bot_instance_id", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_instance_id: Mapped[int] = mapped_column(ForeignKey("bot_instances.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
