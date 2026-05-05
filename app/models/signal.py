from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_bot_run_ts", "bot_instance_id", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_instance_id: Mapped[int] = mapped_column(ForeignKey("bot_instances.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    bar_close: Mapped[float] = mapped_column(Float, nullable=False)

    actions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str] = mapped_column(String, default="")
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
