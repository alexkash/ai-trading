# Development

## Setup

```bash
uv sync
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

The DB is created automatically on first launch (`data/app.sqlite`). Hot-reload
of strategy modules is on by default — set `BOT_HOT_RELOAD=false` to disable.

## Tests

```bash
uv run pytest
```

## Layout

See [architecture.md](architecture.md).

## Docker

```bash
docker compose up
```

Mounts `./bots` and `./data` into the container so that you keep editing
strategies on the host.

## Static assets

The HTML templates reference:

- `/static/htmx.min.js`
- `/static/lightweight-charts.standalone.production.js`
- `/static/app.css`

Drop those JS files in `app/static/`. They are intentionally vendored (no CDN)
so the platform works offline.
