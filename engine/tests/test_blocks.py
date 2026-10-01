"""Each block against the reference model's numpy evaluator (the oracle), plus edge cases.

A formula is turned into library blocks by FormulaBuilder, evaluated by the engine,
and compared with the oracle evaluating the same formula on the same inputs.
"""

from datetime import date

import numpy as np
import pytest
from blockmodel.builder import ModelBuilder
from blockmodel.evaluate import evaluate
from blockmodel.importers.formula import parse
from blockmodel.importers.rows import FormulaBuilder
from blockmodel.library.finance import solve_irr
from blockmodel.model import Timeline
from oracle import dsl

N = 12
TIMELINE = Timeline(start=date(2027, 1, 1), frequency="quarter", periods=N)
rng = np.random.default_rng(20260928)

ENV = {
    "x": rng.uniform(-5, 5, N),
    "y": rng.uniform(-5, 5, N),
    "pos": rng.uniform(0.5, 2.0, N),
    "z": np.array([0, 1.5, 0, -2, 3, 0, 1, 1, 0, 4, -1, 2.0]),
    "half": np.array([2.5, -2.5, 0.125, 1.005, -0.5, 0.5, 1.5, 2.675, -1.25, 10.05, 0.0, 3.14159]),
    "cash": np.array([-100, -50, -20, 10, 30, 60, 80, 90, 95, 100, 100, 400.0]),
    "cond": rng.uniform(0, 1, N) > 0.5,
    "s": 100.0,
    "r": 0.05,
    "k": 3,
    "kk": 7,
}


def run(formula: str):
    """(engine value, oracle value) for a formula over ENV."""
    names = {n[1] for n in _vars(parse(formula))}
    b = ModelBuilder("parity", TIMELINE, namespace=formula)
    env = {}
    for name in sorted(names):
        v = ENV[name]
        if isinstance(v, np.ndarray):
            kind = "bool" if v.dtype == bool else "float"
            env[name] = b.series(v.tolist(), kind=kind, label=name, key=name).out
        else:
            env[name] = b.constant(v, kind="int" if isinstance(v, int) else "float", label=name, key=name).out
    out = FormulaBuilder(b, env).formula(formula, key="f")
    result = evaluate(b.build())
    assert result.errors == [], result.errors
    got = result.outputs[str(out.block)][out.port].value
    ctx = dsl.NpCtx(dict(ENV), np.arange(1, N + 1), np.full(N, 2027))
    want = dsl.evaluate(dsl.parse(formula), ctx)
    return got, want


def _vars(node):
    if node[0] == "var":
        yield node
    elif node[0] in ("bin",):
        yield from _vars(node[2])
        yield from _vars(node[3])
    elif node[0] == "neg":
        yield from _vars(node[1])
    elif node[0] == "call":
        for a in node[2]:
            yield from _vars(a)


PARITY = [
    "x + y",
    "x - y",
    "x * y",
    "x / pos",
    "pow(pos, y)",
    "min(x, y)",
    "max(x, y)",
    "safe_divide(x, z, 7)",
    "ceiling(x)",
    "round(half, 2)",
    "round(half, 0)",
    "round(x, 1)",
    "sum(x, y, pos)",
    "if(cond, x, y)",
    "if(cond, x, 0)",
    "growth(s, r)",
    "step(s, k)",
    "flag(k, kk)",
    "spread(s, k, 4)",
    "discount_factor(r)",
    "lag(x, k)",
    "lag(x, 20)",
    "cumulative(x, s)",
    "running_max(x)",
    "depreciation_sl(pos, k)",
    "depreciation_sl(pos, 20)",
    "total(x)",
    "npv(r, cash)",
    "irr(cash)",
    "x > y",
    "x >= y",
    "x < 0",
    "x == x",
    "-x",
    "(x + y) * pos - s / 4",
]


@pytest.mark.parametrize("formula", PARITY)
def test_parity_with_oracle(formula):
    got, want = run(formula)
    want = np.asarray(want)
    if want.dtype == bool:
        assert list(np.atleast_1d(got)) == list(np.atleast_1d(want))
    else:
        np.testing.assert_allclose(np.asarray(got, dtype=float), want.astype(float), rtol=1e-12, atol=1e-12)


def test_round_is_half_away_from_zero():
    got, _ = run("round(half, 0)")
    assert got[:2] == [3, -3]  # Python's round gives 2 and -2
    assert run("round(half, 2)")[0][2] == 0.13


def test_ceiling_snaps_float_noise():
    b = ModelBuilder("ceiling", TIMELINE)
    noisy = b.series([3.0000000000000004, 2.9999999999999996, 3.1] + [1.0] * (N - 3), label="noisy")
    out = b.add("math.ceiling", x=noisy)
    result = evaluate(b.build())
    assert result.outputs[str(out.block)]["result"].value[:3] == [3, 3, 4]


def test_irr_picks_root_nearest_guess():
    # -100, +230, -132 has roots at 10% and 20%.
    flows = np.array([-100.0, 230.0, -132.0])
    assert solve_irr(flows, guess=0.1) == pytest.approx(0.1, abs=1e-12)
    assert solve_irr(flows, guess=0.25) == pytest.approx(0.2, abs=1e-12)


def test_irr_needs_both_signs():
    b = ModelBuilder("irr", TIMELINE)
    flows = b.series([10.0] * N, label="flows")
    out = b.add("finance.irr", cash_flow=flows)
    result = evaluate(b.build())
    [error] = result.errors
    assert error.block == out.block
    assert "both signs" in error.message


def test_aggregate_to_year_sums_fiscal_years():
    b = ModelBuilder(
        "annual", Timeline(start=date(2027, 1, 1), frequency="quarter", periods=8, fiscal_year_end="06-30")
    )
    x = b.series([1, 2, 3, 4, 5, 6, 7, 8], label="x")
    out = b.add("series.annual", x=x)
    result = evaluate(b.build())
    # FY ends June 30: Q1-Q2 2027 are FY2027, Q3 2027-Q2 2028 are FY2028, Q3-Q4 2028 are FY2029.
    assert result.timeline.years == [2027, 2028, 2029]
    assert result.outputs[str(out.block)]["result"].value == [3.0, 18.0, 15.0]
    assert result.outputs[str(out.block)]["result"].type == "annual<float>"


def test_timeline_block_outputs():
    b = ModelBuilder("timeline", Timeline(start=date(2027, 1, 1), frequency="month", periods=14))
    tl = b.timeline_block()
    result = evaluate(b.build())
    out = result.outputs[str(tl.block)]
    assert out["t"].value[:3] == [1, 2, 3]
    assert out["period_start"].value[1] == "2027-02-01"
    assert out["period_end"].value[1] == "2027-02-28"
    assert out["year"].value[-1] == 2028
    assert out["periods"].value == 14
    assert result.timeline.period_labels[:2] == ["2027-01", "2027-02"]
