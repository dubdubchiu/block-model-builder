"""Lookup: a table held in the block's settings, read by step (tiers) or linear interpolation."""

import numpy as np

from ..types import NUMERIC, Type, TypeRuleError, numeric_float
from .registry import Ctx, register


def _table(ctx: Ctx) -> tuple[np.ndarray, np.ndarray]:
    keys, values = ctx.settings.get("keys") or [], ctx.settings.get("values") or []
    if not keys:
        raise TypeRuleError("The lookup table is empty. Enter ascending keys and one value per key.")
    if len(keys) != len(values):
        raise TypeRuleError(
            f"The table has {len(keys)} keys and {len(values)} values. Give one value per key."
        )
    try:
        k, v = np.array(keys, dtype=float), np.array(values, dtype=float)
    except (TypeError, ValueError):
        raise TypeRuleError("Keys and values must be numbers.") from None
    if np.any(np.diff(k) <= 0):
        raise TypeRuleError("Keys must be in strictly ascending order. Sort them and remove duplicates.")
    return k, v


def _lookup_infer(ctx: Ctx) -> dict[str, Type]:
    x = ctx.types["x"]
    numeric_float(x)
    _table(ctx)
    mode = ctx.settings.get("mode", "step")
    if mode not in ("step", "linear"):
        raise TypeRuleError(f"Mode {mode!r} is not step or linear. Pick one in the inspector.")
    kind = ctx.settings.get("kind", "float")
    if kind not in NUMERIC:
        raise TypeRuleError(f"Kind {kind!r} is not a number kind. Pick one in the inspector.")
    unit = ctx.settings.get("unit") or ("USD" if kind == "currency" else None)
    return {"result": Type(x.shape, kind, unit)}


@register("lookup.table", _lookup_infer)
def lookup(ctx: Ctx, inputs):
    keys, values = _table(ctx)
    x = np.asarray(inputs["x"], dtype=float)
    if ctx.settings.get("mode", "step") == "linear":
        result = np.interp(x, keys, values)
    else:
        result = values[np.clip(np.searchsorted(keys, x, side="right") - 1, 0, len(keys) - 1)]
    return {"result": result if np.ndim(result) else float(result)}
