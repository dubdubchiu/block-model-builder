"""Series: Accumulate, Lag, Running max, Total, Aggregate to year."""

import numpy as np

from ..types import Type, TypeRuleError, additive, numeric_float
from .registry import BlockFailure, Ctx, register


def _window_shape(t: Type) -> str:
    return t.shape if t.per_period else "series"


def _accumulate_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    kind = additive(x, ctx.types["opening"], "add")
    return {"result": Type(_window_shape(x), kind.kind, kind.unit)}


@register("series.accumulate", _accumulate_infer)
def accumulate(ctx: Ctx, inputs):
    x = ctx.per_period(inputs["x"], ctx.out["result"].shape)
    return {"result": inputs["opening"] + np.cumsum(x)}


def _lag_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    if x.kind not in ("bool",) and not x.numeric:
        raise TypeRuleError(f"Lag shifts numbers or TRUE/FALSE values, but gets {x.describe()}.")
    return {"result": x.with_(shape=_window_shape(x))}


@register("series.lag", _lag_infer)
def lag(ctx: Ctx, inputs):
    n = ctx.whole("n", inputs["n"])
    if n < 0:
        raise BlockFailure("Input n must be zero or more. Lag shifts values later in time, not earlier.")
    x = ctx.per_period(inputs["x"], ctx.out["result"].shape)
    out = np.zeros_like(x)
    if n < len(x):
        out[n:] = x[: len(x) - n]
    return {"result": out}


def _running_max_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    numeric_float(x)
    return {"result": x.with_(shape=_window_shape(x))}


@register("series.running_max", _running_max_infer)
def running_max(ctx: Ctx, inputs):
    x = ctx.per_period(inputs["x"], ctx.out["result"].shape).astype(float)
    return {"result": np.maximum.accumulate(x)}


def _total_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    numeric_float(x)
    return {"result": x.with_(shape="scalar")}


@register("series.total", _total_infer)
def total(ctx: Ctx, inputs):
    x = ctx.per_period(inputs["x"], ctx.types["x"].shape if ctx.types["x"].per_period else "series")
    return {"result": float(np.sum(x))}


def _annual_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    numeric_float(x)
    if x.shape == "annual":
        raise TypeRuleError("Input x is already per-year. Aggregate to year takes per-period values.")
    return {"result": x.with_(shape="annual")}


@register("series.annual", _annual_infer)
def annual(ctx: Ctx, inputs):
    tl = ctx.timeline
    x = ctx.per_period(inputs["x"], "series").astype(float)
    return {"result": np.bincount(tl.year_index, weights=x, minlength=len(tl.years))}


def _feedback_infer(ctx: Ctx) -> dict[str, Type]:
    """The carried type comes from `initial` when it's wired, else from the kind and unit settings.
    The evaluator checks x against it once the loop's types are known."""
    initial = ctx.types["initial"]
    if initial.literal:
        kind = ctx.settings.get("kind", "float")
        unit = ctx.settings.get("unit") or ("USD" if kind == "currency" else None)
        return {"value": Type("series", kind, unit)}
    numeric_float(initial)
    return {"value": initial.with_(shape="series")}


@register("series.feedback", _feedback_infer)
def feedback(ctx: Ctx, inputs):
    """Period 1 is `initial`; period t is x at t-1. On the first pass x isn't known yet."""
    n = ctx.timeline.periods
    out = np.full(n, float(inputs["initial"]))
    if "x" in inputs:
        x = ctx.per_period(inputs["x"], "series").astype(float)
        out[1:] = x[: n - 1]
    return {"value": out}
