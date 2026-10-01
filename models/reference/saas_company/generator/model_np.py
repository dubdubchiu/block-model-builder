"""Evaluate the spec in numpy, independent of Excel."""
import datetime as dt
import numpy as np
import dsl
from spec import DRIVERS, SERIES, CALCS, ANNUAL, PERIODS, TIMELINE


def timeline():
    t = np.arange(1, PERIODS + 1)
    start = dt.date.fromisoformat(TIMELINE["start_date"])
    m = TIMELINE["months_per_period"]
    starts, ends = [], []
    for i in range(PERIODS):
        mm = start.month - 1 + i * m
        s = dt.date(start.year + mm // 12, mm % 12 + 1, 1)
        mm2 = mm + m
        e = dt.date(start.year + mm2 // 12, mm2 % 12 + 1, 1) - dt.timedelta(days=1)
        starts.append(s); ends.append(e)
    year = np.array([e.year for e in ends])
    return t, year, starts, ends


def run():
    t, year, _, _ = timeline()
    env = {}
    for d in DRIVERS:
        ident, value = d[0], d[5]
        env[ident] = np.array(SERIES[ident], dtype=float) if value == "series" else float(value)
    ctx = dsl.NpCtx(env, t, year)
    for row in CALCS:
        ident, typ, formula = row[0], row[3], row[5]
        v = dsl.evaluate(dsl.parse(formula), ctx)
        if typ.startswith("series<"):
            v = np.broadcast_to(np.asarray(v), (PERIODS,)).copy()
            if typ == "series<bool>":
                v = v.astype(bool)
        else:
            v = float(v)
        env[ident] = v
    years = sorted(set(year.tolist()))
    annual = {}
    for ident, _, _, _, formula in ANNUAL:
        node = dsl.parse(formula)
        src = env[node[2][0][1]]
        annual[ident] = np.array([src[year == y].sum() for y in years])
    return env, annual, years


if __name__ == "__main__":
    env, annual, years = run()
    np.set_printoptions(linewidth=250, suppress=True)

    def show(k, scale=1e6):
        v = env[k]
        print(f"{k:28s}", np.round(v / scale, 2) if isinstance(v, np.ndarray) else round(v / scale, 3))

    for k in ["new_customers", "churned_customers", "customers_end"]:
        show(k, 1)
    for k in ["revenue", "arr", "cogs_total", "opex_total", "ebitda", "free_cash_flow", "cash_balance", "tax"]:
        show(k)
    for k in ["gross_margin", "ebitda_margin", "rule_of_40"]:
        show(k, 0.01)
    for k in ["cac_fully_loaded", "ltv_to_cac", "cac_payback_months", "burn_multiple", "runway_quarters"]:
        show(k, 1)
    for k in ["npv_value", "npv_check", "terminal_value"]:
        show(k)
    print("irr_q", env["irr_quarterly"], "irr_a", env["irr_annual"])
    for k, v in annual.items():
        print(k, np.round(v / (1 if "customers" in k else 1e6), 1))
    print("cash ok", env["cash_above_minimum"].all())
