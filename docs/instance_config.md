# InstanceConfig

The risk-management knobs that apply to **every** strategy. Defined in
`app/trading/instance_config.py`. Edit them through the bot's detail page; the
platform enforces them on every action a bot returns.

## Capital and sizing

| Field                          | Type        | Default | Notes                                            |
|--------------------------------|-------------|---------|--------------------------------------------------|
| `initial_balance_usdt`         | `float`     | 1000    | Virtual starting balance.                         |
| `risk_mode`                    | `pct_of_equity` / `fixed_usdt` | `pct_of_equity` | How `risk_per_trade` is interpreted.   |
| `risk_per_trade`               | `float`     | 2.0     | `%` of equity, or USDT, used as notional/leverage. |
| `max_position_notional_usdt`   | `float`     | 5000    | Hard cap on a single position's notional.         |
| `max_concurrent_positions`     | `int`       | 1       | Reject new entries beyond this.                   |
| `leverage`                     | `float`     | 3.0     | 1–125. Multiplies notional sizing.                |
| `margin_mode`                  | `isolated` / `cross` | `isolated` | Stored, not yet enforced in v1 sim.       |

## Protective stops

| Field                  | Type                          | Default                          |
|------------------------|-------------------------------|----------------------------------|
| `stop_loss`            | `{mode, value, atr_period}`   | `pct` 2.0                        |
| `take_profit`          | same                          | `pct` 4.0                        |
| `trailing_stop`        | same                          | `off`                            |
| `daily_loss_limit_pct` | `float`                       | 0 (off) — auto-stop trading       |
| `max_drawdown_pct`     | `float`                       | 0 (off) — halt the instance      |

`StopConfig.mode = pct` interprets `value` as percent. `atr` interprets it as
ATR multiplier (with `atr_period`).

## Behavior

| Field                 | Type                                  | Default | Notes                                       |
|-----------------------|---------------------------------------|---------|---------------------------------------------|
| `allowed_sides`       | `long_only` / `short_only` / `both`   | `both`  |                                             |
| `cooldown_sec`        | `int`                                 | 0       | Min seconds between two entries.            |
| `default_order_type`  | `market` / `limit`                    | `market`|                                             |
| `limit_offset_bps`    | `float`                               | 0       | Used when bot returns LIMIT without `price`.|
| `max_slippage_bps`    | `float`                               | 20      | Order is rejected if simulated slippage exceeds. |
| `time_in_force`       | `GTC` / `IOC` / `FOK`                 | `GTC`   |                                             |

## Simulator

| Field            | Type    | Default | Notes                              |
|------------------|---------|---------|------------------------------------|
| `taker_fee_bps`  | `float` | 5.5     | Bybit USDT perpetuals taker fee.   |
| `maker_fee_bps`  | `float` | 2.0     | Bybit maker fee.                   |
| `slippage_bps`   | `float` | 1.0     | Fixed bps from mid for market fills.|
| `apply_funding`  | `bool`  | `true`  | Apply Bybit funding payments (live: WS; backtest: REST history). |
| `latency_ms`     | `int`   | 0       | Reserved — fill delay model.        |
