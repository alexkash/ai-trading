from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.bot import BotInstance
from app.models.equity import EquityPoint
from app.models.run import Run, RunStatus
from app.models.signal import Signal
from app.models.trade import Trade
from app.templating import templates

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request, run_id: int, session: AsyncSession = Depends(get_session)
):
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404)
    bot = await session.get(BotInstance, run.bot_instance_id)

    trades = (
        await session.execute(
            select(Trade).where(Trade.run_id == run_id).order_by(Trade.opened_at)
        )
    ).scalars().all()
    signals = (
        await session.execute(
            select(Signal).where(Signal.run_id == run_id).order_by(desc(Signal.ts)).limit(50)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "runs/detail.html",
        {"run": run, "bot": bot, "trades": trades, "signals": signals},
    )


@router.get("/{run_id}/progress", response_class=HTMLResponse)
async def progress_partial(
    request: Request, run_id: int, session: AsyncSession = Depends(get_session)
):
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "partials/run_progress.html", {"run": run})


@router.get("/{run_id}/equity.json")
async def equity_json(run_id: int, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(EquityPoint).where(EquityPoint.run_id == run_id).order_by(EquityPoint.ts)
        )
    ).scalars().all()
    return [
        {"time": int(r.ts.replace(tzinfo=timezone.utc).timestamp()), "value": r.equity}
        for r in rows
    ]


@router.get("/{run_id}/status")
async def run_status(run_id: int, session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404)
    return {
        "status": run.status.value if isinstance(run.status, RunStatus) else run.status,
        "progress": run.progress,
        "metrics": run.metrics,
        "error": run.error,
    }
