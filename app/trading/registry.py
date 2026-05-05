"""Auto-discovery of bot strategies from the ``bots/`` directory."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from app.config import BOTS_DIR
from app.trading.base_bot import BaseBot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyEntry:
    key: str           # unique key (module:ClassName)
    name: str          # human name from BaseBot.name
    description: str
    cls: type[BaseBot]
    module: str
    file: str
    params_schema: type[BaseModel]
    supported_timeframes: list[str]
    supports_multi_symbol: bool


class StrategyRegistry:
    """Загружает все подклассы BaseBot из ``bots/``.

    Перезагрузка осуществляется по запросу ``reload()`` — например, hot-reloader
    зовёт её на изменение файлов.
    """

    def __init__(self, bots_dir: Path = BOTS_DIR) -> None:
        self._dir = bots_dir
        self._lock = threading.Lock()
        self._entries: dict[str, StrategyEntry] = {}

    def reload(self) -> None:
        with self._lock:
            self._entries = {}
            if not self._dir.exists():
                return
            self._ensure_package()
            for path in sorted(self._dir.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                self._load_module(path)

    def _package_name(self) -> str:
        # Use a stable, dir-derived package name so multiple registries can coexist.
        if self._dir == BOTS_DIR:
            return "bots"
        return f"bots_{abs(hash(str(self._dir.resolve())))}"

    def _ensure_package(self) -> None:
        init = self._dir / "__init__.py"
        if not init.exists():
            init.write_text('"""User-supplied bot strategies."""\n')

    def _load_module(self, path: Path) -> None:
        pkg = self._package_name()
        mod_name = f"{pkg}.{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"no spec for {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as e:  # noqa: BLE001
            log.exception("failed to import strategy module %s: %s", path.name, e)
            return

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls is BaseBot or not issubclass(cls, BaseBot):
                continue
            if cls.__module__ != module.__name__:
                continue
            try:
                entry = StrategyEntry(
                    key=f"{cls.__module__}:{cls.__name__}",
                    name=getattr(cls, "name", cls.__name__),
                    description=getattr(cls, "description", ""),
                    cls=cls,
                    module=cls.__module__,
                    file=str(path),
                    params_schema=cls.params_schema,
                    supported_timeframes=list(cls.supported_timeframes),
                    supports_multi_symbol=cls.supports_multi_symbol,
                )
            except AttributeError as e:
                log.warning("strategy %s incomplete: %s", cls.__name__, e)
                continue
            self._entries[entry.key] = entry

    def list(self) -> list[StrategyEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name.lower())

    def get(self, key: str) -> StrategyEntry | None:
        return self._entries.get(key)


registry = StrategyRegistry()
