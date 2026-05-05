"""Template strategy. Copy and rename — registry skips files starting with ``_``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.trading.base_bot import Action, BaseBot, Bar, Hold


class TemplateParams(BaseModel):
    period: int = Field(default=14, ge=2, le=500, description="Look-back window")


class Template(BaseBot):
    name = "Template"
    description = "Replace me with a real strategy."
    params_schema = TemplateParams

    def on_bar(self, bar: Bar) -> list[Action]:
        return [Hold()]
