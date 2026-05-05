from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.exporters.datasets import BUILDERS

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{scope}/{ident}/{kind}.{fmt}")
async def export_dataset(scope: str, ident: int, kind: str, fmt: str):
    if scope not in ("bot", "run"):
        raise HTTPException(404, "scope must be bot|run")
    builder = BUILDERS.get(kind)
    if builder is None:
        raise HTTPException(404, f"unknown kind '{kind}'")
    if fmt not in ("csv", "parquet"):
        raise HTTPException(404, "fmt must be csv|parquet")

    df = await builder(scope, ident)
    buf: io.BytesIO | io.StringIO
    media: str
    if fmt == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        data = buf.getvalue().encode("utf-8")
        media = "text/csv"
    else:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        data = buf.getvalue()
        media = "application/octet-stream"

    filename = f"{scope}{ident}_{kind}.{fmt}"
    return StreamingResponse(
        iter([data]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
