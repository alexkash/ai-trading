from __future__ import annotations

from app.trading.registry import StrategyRegistry, registry


def test_registry_discovers_shipped_strategies() -> None:
    registry.reload()
    keys = {e.key for e in registry.list()}
    # Two example bots ship in bots/.
    assert any(k.endswith(":EMACrossover") for k in keys)
    assert any(k.endswith(":RSIMeanRev") for k in keys)
    # Underscore-prefixed files (templates) are skipped.
    assert all(":Template" not in k for k in keys)


def test_registry_isolated_in_temp_dir(tmp_path) -> None:
    bots_dir = tmp_path / "bots"
    bots_dir.mkdir()
    (bots_dir / "dummy.py").write_text(
        '''from pydantic import BaseModel
from app.trading.base_bot import Action, Bar, BaseBot, Hold


class DummyParams(BaseModel):
    pass


class Dummy(BaseBot):
    name = "Dummy"
    description = "for tests"
    params_schema = DummyParams

    def on_bar(self, bar):
        return [Hold()]
'''
    )
    reg = StrategyRegistry(bots_dir=bots_dir)
    reg.reload()
    keys = [e.key for e in reg.list()]
    assert any(k.endswith(":Dummy") for k in keys)
