"""Finance: Discount factor, NPV, IRR, Straight-line depreciation.

Rates are per period. NPV discounts period t by (1 + rate)^t with t from 1, like
Excel's NPV. IRR brackets and bisects, so it doesn't diverge the way Newton's
method does on long burn-then-terminal-value profiles.
"""

import numpy as np

from ..types import Type, TypeRuleError, not_currency, numeric_float
from .registry import BlockFailure, Ctx, register

IRR_LOW, IRR_HIGH = -0.99, 10.0
# Dense near zero, where real-world rates live; coarse at the extremes.
IRR_GRID = np.unique(
    np.concatenate(
        [
            np.linspace(IRR_LOW, -0.2, 80, endpoint=False),
            np.linspace(-0.2, 1.0, 1201),
            np.linspace(1.0, IRR_HIGH, 181),
        ]
    )
)


def _rate(ctx: Ctx) -> Type:
    rate = ctx.types["rate"]
    not_currency("rate", rate)
    numeric_float(rate)
    return rate


def _discount_factor_infer(ctx: Ctx) -> dict[str, Type]:
    _rate(ctx)
    return {"result": Type("series", "float")}


@register("finance.discount_factor", _discount_factor_infer)
def discount_factor(ctx: Ctx, inputs):
    return {"result": 1.0 / (1.0 + inputs["rate"]) ** ctx.timeline.t}


def _npv_infer(ctx: Ctx) -> dict[str, Type]:
    _rate(ctx)
    cash = ctx.types["cash_flow"]
    numeric_float(cash)
    return {"result": cash.with_(shape="scalar")}


@register("finance.npv", _npv_infer)
def npv(ctx: Ctx, inputs):
    x = ctx.per_period(inputs["cash_flow"], "series").astype(float)
    t = np.arange(1, len(x) + 1)
    return {"result": float(np.sum(x / (1.0 + inputs["rate"]) ** t))}


def _irr_infer(ctx: Ctx) -> dict[str, Type]:
    cash = ctx.types["cash_flow"]
    numeric_float(cash)
    if "guess" in ctx.types:
        not_currency("guess", ctx.types["guess"])
    return {"result": Type("scalar", "percent")}


def _pv(x: np.ndarray, rates: np.ndarray) -> np.ndarray:
    k = np.arange(len(x))
    with np.errstate(all="ignore"):
        return (x[None, :] / (1.0 + rates[:, None]) ** k[None, :]).sum(axis=1)


def solve_irr(x: np.ndarray, guess: float = 0.1) -> float:
    """The per-period rate r with sum(x_k / (1 + r)^k) = 0, found by bracketing and bisection."""
    x = np.asarray(x, dtype=float)
    if not (np.any(x > 0) and np.any(x < 0)):
        raise BlockFailure(
            "IRR needs cash flows with both signs (some negative, some positive). Check the cash flow input."
        )
    values = _pv(x, IRR_GRID)
    roots: list[float] = list(IRR_GRID[values == 0])
    finite = np.isfinite(values)
    for i in range(len(IRR_GRID) - 1):
        a, b = values[i], values[i + 1]
        if finite[i] and finite[i + 1] and a * b < 0:
            lo, hi, f_lo = IRR_GRID[i], IRR_GRID[i + 1], a
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                f_mid = _pv(x, np.array([mid]))[0]
                if f_mid == 0 or hi - lo <= 1e-15 * max(1.0, abs(mid)):
                    break
                if (f_mid < 0) == (f_lo < 0):
                    lo, f_lo = mid, f_mid
                else:
                    hi = mid
            roots.append(0.5 * (lo + hi))
    if not roots:
        raise BlockFailure(
            f"IRR has no solution between {IRR_LOW:.0%} and {IRR_HIGH:.0%} per period. "
            "Check the cash flow input; NPV may be a better measure here."
        )
    return float(min(roots, key=lambda r: abs(r - guess)))


@register("finance.irr", _irr_infer)
def irr(ctx: Ctx, inputs):
    x = ctx.per_period(inputs["cash_flow"], "series")
    return {"result": solve_irr(x, float(inputs.get("guess", 0.1)))}


def _depreciation_infer(ctx: Ctx) -> dict[str, Type]:
    capex = ctx.types["capex"]
    numeric_float(capex)
    if capex.literal:
        raise TypeRuleError("Wire the capex input; depreciation needs spending per period.")
    return {"result": capex.with_(shape=capex.shape if capex.per_period else "series")}


@register("finance.depreciation_sl", _depreciation_infer)
def depreciation_sl(ctx: Ctx, inputs):
    life = ctx.whole("life", inputs["life"])
    if life < 1:
        raise BlockFailure("Input life must be at least 1 period. Set the asset life in periods.")
    capex = ctx.per_period(inputs["capex"], ctx.out["result"].shape).astype(float)
    # Each period's spend depreciates evenly over `life` periods, starting in the period it's spent.
    return {"result": np.convolve(capex, np.full(life, 1.0 / life))[: len(capex)]}
