"""Sources: Constant, Series input, Timeline, Growth, Step, Period flag, Spread."""

from datetime import date

import numpy as np

from ..types import INTEGER, KINDS, NUMERIC, Type, TypeRuleError, not_currency, result_shape
from .registry import BlockFailure, Ctx, register


def _checked_value(value, kind: str, where: str):
    if kind in NUMERIC:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeRuleError(f"{where} must be a number for kind {kind}; got {value!r}.")
        if kind in INTEGER and not float(value).is_integer():
            raise TypeRuleError(f"{where} must be a whole number for kind {kind}; got {value!r}.")
        return float(value)
    if kind == "bool":
        if not isinstance(value, bool):
            raise TypeRuleError(f"{where} must be TRUE or FALSE for kind bool; got {value!r}.")
        return value
    if kind == "date":
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            raise TypeRuleError(f"{where} must be a date like 2027-01-01; got {value!r}.") from None
    return str(value)


def _kind(ctx: Ctx) -> str:
    kind = ctx.settings.get("kind", "float")
    if kind not in KINDS:
        raise TypeRuleError(f"Kind {kind!r} is not one of {', '.join(KINDS)}. Pick a kind in the inspector.")
    return kind


def _unit(ctx: Ctx, kind: str) -> str | None:
    unit = ctx.settings.get("unit") or None
    return unit or ("USD" if kind == "currency" else None)


# ---------------------------------------------------------------- Constant


def _constant_infer(ctx: Ctx) -> dict[str, Type]:
    kind = _kind(ctx)
    _checked_value(ctx.settings.get("value", 0), kind, "The value")
    return {"value": Type("scalar", kind, _unit(ctx, kind))}


@register("source.constant", _constant_infer)
def constant(ctx: Ctx, inputs):
    return {"value": _checked_value(ctx.settings.get("value", 0), _kind(ctx), "The value")}


# ---------------------------------------------------------------- Series input


def _series_values(ctx: Ctx, kind: str) -> list:
    values = ctx.settings.get("values")
    if not isinstance(values, list):
        raise TypeRuleError("Series input has no values. Enter one value per period in the inspector.")
    n = ctx.timeline.periods
    if len(values) != n:
        raise TypeRuleError(
            f"Series input has {len(values)} values; the timeline has {n} periods. Add or remove values to match."
        )
    return [_checked_value(v, kind, f"Value {i + 1}") for i, v in enumerate(values)]


def _series_infer(ctx: Ctx) -> dict[str, Type]:
    kind = _kind(ctx)
    if kind in ("str", "date"):
        raise TypeRuleError("Series input holds numbers or TRUE/FALSE values. Pick a number kind or bool.")
    _series_values(ctx, kind)
    return {"value": Type("series", kind, _unit(ctx, kind))}


@register("source.series", _series_infer)
def series_input(ctx: Ctx, inputs):
    kind = _kind(ctx)
    return {"value": np.array(_series_values(ctx, kind), dtype=bool if kind == "bool" else float)}


# ---------------------------------------------------------------- Timeline


def _timeline_infer(ctx: Ctx) -> dict[str, Type]:
    return {
        "t": Type("series", "int"),
        "period_start": Type("series", "date"),
        "period_end": Type("series", "date"),
        "year": Type("series", "int"),
        "fiscal_year": Type("series", "int"),
        "periods": Type("scalar", "int"),
    }


@register("source.timeline", _timeline_infer)
def timeline(ctx: Ctx, inputs):
    tl = ctx.timeline
    return {
        "t": tl.t.copy(),
        "period_start": np.array(tl.starts, dtype="datetime64[D]"),
        "period_end": np.array(tl.ends, dtype="datetime64[D]"),
        "year": tl.calendar_year.astype(float),
        "fiscal_year": tl.fiscal_year.astype(float),
        "periods": float(tl.periods),
    }


# ---------------------------------------------------------------- generators over t


def _growth_infer(ctx: Ctx) -> dict[str, Type]:
    ctx.no_annual("start", "rate")
    start, rate = ctx.types["start"], ctx.types["rate"]
    not_currency("rate", rate)
    start = start.with_(kind="float") if start.literal else start
    result_shape(start, rate)
    return {"value": Type("series", start.kind, start.unit)}


@register("source.growth", _growth_infer)
def growth(ctx: Ctx, inputs):
    return {"value": inputs["start"] * (1 + inputs["rate"]) ** (ctx.timeline.t - 1)}


def _step_infer(ctx: Ctx) -> dict[str, Type]:
    ctx.no_annual("value")
    value = ctx.types["value"]
    value = value.with_(kind="float") if value.literal else value
    return {"value": Type("series", value.kind, value.unit)}


@register("source.step", _step_infer)
def step(ctx: Ctx, inputs):
    from_period = ctx.whole("from_period", inputs["from_period"])
    value = ctx.per_period(inputs["value"], "series")
    return {"value": np.where(ctx.timeline.t >= from_period, value, 0.0)}


@register("source.flag", lambda ctx: {"value": Type("series", "bool")})
def flag(ctx: Ctx, inputs):
    start, end = ctx.whole("start", inputs["start"]), ctx.whole("end", inputs["end"])
    t = ctx.timeline.t
    return {"value": (t >= start) & (t <= end)}


def _spread_infer(ctx: Ctx) -> dict[str, Type]:
    ctx.no_annual("amount")
    amount = ctx.types["amount"]
    amount = amount.with_(kind="float") if amount.literal else amount
    return {"value": Type("series", amount.kind, amount.unit)}


@register("source.spread", _spread_infer)
def spread(ctx: Ctx, inputs):
    start, n = ctx.whole("start", inputs["start"]), ctx.whole("periods", inputs["periods"])
    if n < 1:
        raise BlockFailure(
            "Input periods must be at least 1. Set how many periods to spread the amount over."
        )
    t = ctx.timeline.t
    amount = ctx.per_period(inputs["amount"], "series")
    return {"value": np.where((t >= start) & (t < start + n), amount / n, 0.0)}
