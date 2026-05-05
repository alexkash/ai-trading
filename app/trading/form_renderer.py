"""Render a Pydantic schema as a list of HTML form field descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


@dataclass
class FormField:
    name: str
    label: str
    description: str
    kind: str  # number | text | select | checkbox | nested
    value: Any
    options: list[tuple[str, str]] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    nested: list["FormField"] | None = None


def _is_enum_type(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, Enum)


def _options_from_enum(tp: type[Enum]) -> list[tuple[str, str]]:
    return [(e.value, e.name.replace("_", " ")) for e in tp]


def _resolve_value(values: dict | None, name: str, default: Any) -> Any:
    if values is None or name not in values:
        return default
    return values[name]


def render(schema: type[BaseModel], values: dict | None = None) -> list[FormField]:
    fields: list[FormField] = []
    for name, info in schema.model_fields.items():
        fields.append(_render_field(name, info, _resolve_value(values, name, info.default)))
    return fields


def _render_field(name: str, info: FieldInfo, value: Any) -> FormField:
    annotation = info.annotation
    label = name.replace("_", " ").title()
    description = info.description or ""

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        nested_values = value.model_dump() if isinstance(value, BaseModel) else value
        return FormField(
            name=name,
            label=label,
            description=description,
            kind="nested",
            value=None,
            nested=render(annotation, nested_values if isinstance(nested_values, dict) else None),
        )

    if _is_enum_type(annotation):
        return FormField(
            name=name,
            label=label,
            description=description,
            kind="select",
            value=value.value if isinstance(value, Enum) else value,
            options=_options_from_enum(annotation),
        )

    origin = get_origin(annotation)
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1 and _is_enum_type(args[0]):
            return FormField(
                name=name,
                label=label,
                description=description,
                kind="select",
                value=value.value if isinstance(value, Enum) else value,
                options=_options_from_enum(args[0]),
            )

    if annotation is bool:
        return FormField(
            name=name, label=label, description=description, kind="checkbox", value=bool(value)
        )

    if annotation in (int, float):
        meta = _numeric_meta(info)
        return FormField(
            name=name,
            label=label,
            description=description,
            kind="number",
            value=value,
            min=meta["min"],
            max=meta["max"],
            step=1 if annotation is int else 0.01,
        )

    return FormField(name=name, label=label, description=description, kind="text", value=value)


def _numeric_meta(info: FieldInfo) -> dict[str, float | None]:
    meta: dict[str, float | None] = {"min": None, "max": None}
    for m in info.metadata:
        if hasattr(m, "ge") and m.ge is not None:
            meta["min"] = float(m.ge)
        if hasattr(m, "gt") and m.gt is not None:
            meta["min"] = float(m.gt)
        if hasattr(m, "le") and m.le is not None:
            meta["max"] = float(m.le)
        if hasattr(m, "lt") and m.lt is not None:
            meta["max"] = float(m.lt)
    return meta
