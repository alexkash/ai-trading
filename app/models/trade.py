from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_bot_run", "bot_instance_id", "run_id"),
        Index("ix_trades_opened", "opened_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_instance_id: Mapped[int] = mapped_column(ForeignKey("bot_instances.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)

    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long | short
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[float] = mapped_column(Float, default=1.0)

    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fee: Mapped[float] = mapped_column(Float, default=0.0)
    funding: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)

    exit_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(80), nullable=True)
