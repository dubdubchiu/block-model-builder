"""Math: Add, Subtract, Multiply, Divide, Safe divide, Power, Min, Max, Ceiling, Round, Sum."""

import numpy as np

from ..types import (
    Type,
    TypeRuleError,
    additive,
    divide,
    integral,
    multiplicative,
    numeric_float,
    resolve_peers,
)
from .registry import BlockFailure, Ctx, register

CEILING_SNAP = 1e-9


def _pair(ctx: Ctx) -> tuple[Type, Type]:
    return ctx.types["a"], ctx.types["b"]


@register("math.add", lambda ctx: {"result": additive(*_pair(ctx), "add")})
def add(ctx: Ctx, inputs):
    return {"result": inputs["a"] + inputs["b"]}


@register("math.subtract", lambda ctx: {"result": additive(*_pair(ctx), "subtract")})
def subtract(ctx: Ctx, inputs):
    return {"result": inputs["a"] - inputs["b"]}


@register("math.multiply", lambda ctx: {"result": multiplicative(*_pair(ctx))})
def multiply(ctx: Ctx, inputs):
    return {"result": inputs["a"] * inputs["b"]}


@register("math.min", lambda ctx: {"result": additive(*_pair(ctx), "compare")})
def minimum(ctx: Ctx, inputs):
    return {"result": np.minimum(inputs["a"], inputs["b"])}


@register("math.max", lambda ctx: {"result": additive(*_pair(ctx), "compare")})
def maximum(ctx: Ctx, inputs):
    return {"result": np.maximum(inputs["a"], inputs["b"])}


@register("math.power", lambda ctx: {"result": numeric_float(*_pair(ctx))})
def power(ctx: Ctx, inputs):
    return {"result": np.power(inputs["a"], inputs["b"])}


def _first_zero(ctx: Ctx, den) -> str:
    if np.ndim(den) == 0:
        return "the denominator is zero"
    i = int(np.flatnonzero(np.asarray(den) == 0)[0])
    shape = ctx.out["result"].shape
    return f"the denominator is zero in period {ctx.timeline.label(shape, i)}"


@register("math.divide", lambda ctx: {"result": divide(*_pair(ctx))})
def div(ctx: Ctx, inputs):
    den = inputs["b"]
    if np.any(np.asarray(den) == 0):
        raise BlockFailure(
            f"Divide by zero: {_first_zero(ctx, den)}. Use Safe divide to return a fallback value there."
        )
    return {"result": inputs["a"] / den}


def _safe_divide_infer(ctx: Ctx) -> dict[str, Type]:
    result = divide(ctx.types["a"], ctx.types["b"])
    fallback = ctx.types["fallback"]
    if fallback.literal:
        return {"result": result}
    return {"result": additive(result.with_(literal=False), fallback, "return")}


@register("math.safe_divide", _safe_divide_infer)
def safe_divide(ctx: Ctx, inputs):
    num, den, fallback = inputs["a"], np.asarray(inputs["b"], dtype=float), inputs["fallback"]
    zero = den == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(zero, fallback, num / np.where(zero, 1.0, den))
    return {"result": result if result.ndim else float(result)}


def _one_numeric(ctx: Ctx) -> Type:
    t = ctx.types["x"]
    numeric_float(t)  # bool and text are errors
    return t


@register("math.ceiling", lambda ctx: {"result": integral(_one_numeric(ctx))})
def ceiling(ctx: Ctx, inputs):
    x = np.asarray(inputs["x"], dtype=float)
    nearest = np.round(x)
    snapped = np.where(np.abs(x - nearest) <= CEILING_SNAP * np.maximum(np.abs(x), 1.0), nearest, x)
    result = np.ceil(snapped)
    return {"result": result if result.ndim else float(result)}


def excel_round(x, digits: int):
    """Half away from zero, like Excel's ROUND."""
    m = 10.0**digits
    return np.sign(x) * np.floor(np.abs(x) * m + 0.5) / m


def _round_infer(ctx: Ctx) -> dict[str, Type]:
    t = _one_numeric(ctx)
    # Rounding to a whole number (a literal digits <= 0) makes values integral; wired or positive digits keep the kind.
    digits = ctx.literals.get("digits")
    return {"result": integral(t) if digits is not None and float(digits) <= 0 else t.with_()}


@register("math.round", _round_infer)
def round_(ctx: Ctx, inputs):
    digits = ctx.whole("digits", inputs["digits"])
    result = excel_round(np.asarray(inputs["x"], dtype=float), digits)
    return {"result": result if result.ndim else float(result)}


SUM_PORTS = tuple(f"in{i}" for i in range(1, 9))


def _sum_infer(ctx: Ctx) -> dict[str, Type]:
    present = [ctx.types[p] for p in SUM_PORTS if p in ctx.types]
    if not present:
        raise TypeRuleError("Sum has no inputs. Wire at least one input.")
    present = list(resolve_peers(*present))
    result = present[0].with_()
    for t in present[1:]:
        result = additive(result, t, "add")
    return {"result": result}


@register("math.sum", _sum_infer)
def total_of_inputs(ctx: Ctx, inputs):
    values = [inputs[p] for p in SUM_PORTS if p in inputs]
    result = values[0]
    for v in values[1:]:
        result = result + v
    return {"result": result}
