from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.bot import BotInstance, BotStatus
from app.models.equity import EquityPoint
from app.models.run import Run
from app.models.signal import Signal
from app.models.trade import Trade
from app.templating import templates
from app.trading.backtest_engine import run_backtest, schedule_backtest
from app.trading.form_renderer import render
from app.trading.instance_config import InstanceConfig
from app.trading.live_engine import supervisor
from app.trading.registry import registry

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_class=HTMLResponse)
async def list_bots(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(BotInstance).order_by(desc(BotInstance.updated_at)))
    bots = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "bots/list.html",
        {"bots": bots, "strategies": registry.list()},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_bot_form(request: Request, strategy: str | None = None):
    strategies = registry.list()
    if not strategies:
        return templates.TemplateResponse(
            request, "bots/empty_strategies.html", {}
        )
    selected = registry.get(strategy) if strategy else strategies[0]
    if selected is None:
        raise HTTPException(404, "strategy not found")
    bot_form = render(selected.params_schema)
    cfg_form = render(InstanceConfig)
    return templates.TemplateResponse(
        request,
        "bots/new.html",
        {
            "strategies": strategies,
            "selected": selected,
            "bot_form": bot_form,
            "cfg_form": cfg_form,
            "default_symbol": "BTCUSDT",
            "default_tf": "5m",
        },
    )


def _parse_form(prefix: str, form: dict) -> dict:
    out: dict = {}
    for raw_key, value in form.items():
        if not raw_key.startswith(prefix + "."):
            continue
        key = raw_key[len(prefix) + 1 :]
        cur = out
        parts = key.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return out


@router.post("")
async def create_bot(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    data = dict(form)
    name = data.get("name") or "Untitled"
    strategy = data.get("strategy") or ""
    symbol = (data.get("symbol") or "BTCUSDT").upper()
    primary_tf = data.get("primary_tf") or "5m"

    entry = registry.get(strategy)
    if entry is None:
        raise HTTPException(400, "strategy not found")

    bot_dict = _parse_form("p", data)
    cfg_dict = _parse_form("c", data)

    try:
        params = entry.params_schema.model_validate(bot_dict)
    except Exception as e:
        raise HTTPException(400, f"bot params invalid: {e}") from e
    try:
        cfg = InstanceConfig.model_validate(cfg_dict)
    except Exception as e:
        raise HTTPException(400, f"instance config invalid: {e}") from e

    inst = BotInstance(
        name=name,
        strategy=strategy,
        symbol=symbol,
        primary_tf=primary_tf,
        bot_params=json.loads(params.model_dump_json()),
        instance_config=json.loads(cfg.model_dump_json()),
        balance=cfg.initial_balance_usdt,
        equity=cfg.initial_balance_usdt,
    )
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    return RedirectResponse(f"/bots/{inst.id}", status_code=303)


@router.get("/{bot_id}", response_class=HTMLResponse)
async def bot_detail(
    request: Request, bot_id: int, session: AsyncSession = Depends(get_session)
):
    inst = await session.get(BotInstance, bot_id)
    if inst is None:
        raise HTTPException(404)
    entry = registry.get(inst.strategy)
    bot_form = render(entry.params_schema, inst.bot_params) if entry else []
    cfg_form = render(InstanceConfig, inst.instance_config or {})

    runs_result = await session.execute(
        select(Run).where(Run.bot_instance_id == bot_id).order_by(desc(Run.id)).limit(20)
    )
    runs = runs_result.scalars().all()

    trades = (
        await session.execute(
            select(Trade)
            .where(Trade.bot_instance_id == bot_id, Trade.run_id.is_(None))
            .order_by(desc(Trade.opened_at))
            .limit(50)
        )
    ).scalars().all()

    signals = (
        await session.execute(
            select(Signal)
            .where(Signal.bot_instance_id == bot_id, Signal.run_id.is_(None))
            .order_by(desc(Signal.ts))
            .limit(20)
        )
    ).scalars().all()

    is_live = supervisor.is_running(bot_id)
    return templates.TemplateResponse(
        request,
        "bots/detail.html",
        {
            "bot": inst,
            "strategy": entry,
            "bot_form": bot_form,
            "cfg_form": cfg_form,
            "runs": runs,
            "trades": trades,
            "signals": signals,
            "is_live": is_live,
            "default_from": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
            "default_to": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
    )


@router.get("/{bot_id}/equity.json")
async def equity_json(bot_id: int, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(EquityPoint)
            .where(EquityPoint.bot_instance_id == bot_id, EquityPoint.run_id.is_(None))
            .order_by(EquityPoint.ts)
        )
    ).scalars().all()
    return [
        {"time": int(r.ts.replace(tzinfo=timezone.utc).timestamp()), "value": r.equity}
        for r in rows
    ]


@router.post("/{bot_id}/params")
async def update_params(
    request: Request, bot_id: int, session: AsyncSession = Depends(get_session)
):
    inst = await session.get(BotInstance, bot_id)
    if inst is None:
        raise HTTPException(404)
    entry = registry.get(inst.strategy)
    if entry is None:
        raise HTTPException(400, "strategy missing")
    data = dict(await request.form())
    bot_dict = _parse_form("p", data)
    cfg_dict = _parse_form("c", data)
    try:
        params = entry.params_schema.model_validate(bot_dict)
        cfg = InstanceConfig.model_validate(cfg_dict)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    inst.bot_params = json.loads(params.model_dump_json())
    inst.instance_config = json.loads(cfg.model_dump_json())
    if "symbol" in data:
        inst.symbol = data["symbol"].upper()
    if "primary_tf" in data:
        inst.primary_tf = data["primary_tf"]
    if "name" in data:
        inst.name = data["name"]
    await session.commit()
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/start")
async def start_live(bot_id: int, session: AsyncSession = Depends(get_session)):
    inst = await session.get(BotInstance, bot_id)
    if inst is None:
        raise HTTPException(404)
    try:
        await supervisor.start(bot_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e)) from e
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/stop")
async def stop_live(bot_id: int):
    await supervisor.stop(bot_id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/backtest")
async def start_backtest(
    bot_id: int,
    from_date: str = Form(...),
    to_date: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    inst = await session.get(BotInstance, bot_id)
    if inst is None:
        raise HTTPException(404)
    try:
        from_ts = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        to_ts = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if to_ts <= from_ts:
        raise HTTPException(400, "to_date must be after from_date")
    run_id = await schedule_backtest(bot_id, from_ts, to_ts)
    asyncio.create_task(run_backtest(run_id))
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@router.get("/cards", response_class=HTMLResponse)
async def cards_partial(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(BotInstance).order_by(desc(BotInstance.updated_at)))
    bots = result.scalars().all()
    return templates.TemplateResponse(request, "partials/bot_cards.html", {"bots": bots})


@router.post("/{bot_id}/delete")
async def delete_bot(bot_id: int, session: AsyncSession = Depends(get_session)):
    inst = await session.get(BotInstance, bot_id)
    if inst is None:
        raise HTTPException(404)
    if supervisor.is_running(bot_id):
        await supervisor.stop(bot_id)
    await session.delete(inst)
    await session.commit()
    return RedirectResponse("/bots", status_code=303)
