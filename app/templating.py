from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.config import ROOT_DIR

templates = Jinja2Templates(directory=ROOT_DIR / "app" / "templates")
