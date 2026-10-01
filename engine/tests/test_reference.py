"""Acceptance: the reference model, imported from generator/spec.py, matches expected.json."""

import json
import time
from pathlib import Path

import numpy as np
import pytest
from blockmodel.evaluate import evaluate
from blockmodel.importers.formula import parse
from blockmodel.importers.rows import import_rows
from blockmodel.model import Model
from oracle import SPEC_PATH, dsl, reference_spec

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = json.loads((ROOT / "models" / "reference" / "saas_company" / "expected.json").read_text())
EXAMPLE = ROOT / "models" / "examples" / "saas_company.json"


# Churn and price carry most of a subscription business's uncertainty.
SCENARIO_DRIVERS = ("churn_rate_q", "arpa_monthly")


@pytest.fixture(scope="module")
def imported():
    return import_rows(SPEC_PATH, scenario_drivers=SCENARIO_DRIVERS)


@pytest.fixture(scope="module")
def result(imported):
    return evaluate(imported.model)


def test_parser_matches_the_generator():
    formulas = [r[5] for r in reference_spec.CALCS] + [r[4] for r in reference_spec.ANNUAL]
    for formula in formulas:
        assert parse(formula) == dsl.parse(formula), formula


def passes(got, row: dict, tolerance: dict) -> tuple[bool, float]:
    want = np.atleast_1d(np.asarray(row["value"], dtype=float))
    got = np.atleast_1d(np.asarray(got, dtype=float))
    if got.shape != want.shape:
        return False, float("inf")
    err = np.abs(got - want)
    rel = float((err / np.maximum(np.abs(want), 1.0)).max())
    if tolerance.get("exact"):
        return bool(np.array_equal(got, want)), rel
    return bool(np.all(err <= np.maximum(1e-6, tolerance["rel"] * np.abs(want)))), rel


def test_reference_model_matches_expected(imported, result):
    assert result.errors == []
    tolerances = {e["id"]: e["tolerance"] for e in EXPECTED["expected"]}
    roles = {e["id"]: e["role"] for e in EXPECTED["expected"]}
    failures, worst = [], (0.0, "")
    for ident, row in EXPECTED["rows"].items():
        out = imported.rows[ident]
        got = result.outputs[str(out.block)][out.port].value
        ok, rel = passes(got, row, tolerances.get(ident, {"rel": 1e-6}))
        worst = max(worst, (rel, ident))
        if not ok:
            failures.append(f"{ident} ({roles.get(ident, 'calculation')})")
    print(
        f"\nreference model: {len(EXPECTED['rows'])} rows, worst relative difference {worst[0]:.2e} ({worst[1]})"
    )
    required = [f for f in failures if "(required)" in f]
    assert not required, f"required rows differ: {required}"
    assert not failures, f"rows differ: {failures}"


def test_reference_timeline_matches(result):
    assert result.timeline.period_labels == EXPECTED["period_labels"]
    assert result.timeline.years == EXPECTED["years"]


def test_reference_types_match_declared(imported, result):
    declared = {r[0]: r[3] for r in reference_spec.CALCS}
    for ident, typ in declared.items():
        out = imported.rows[ident]
        assert result.outputs[str(out.block)][out.port].type == typ, ident


def test_reference_evaluates_quickly(imported):
    evaluate(imported.model)
    t0 = time.perf_counter()
    evaluate(imported.model)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"\nreference model: {len(imported.model.blocks)} blocks, evaluate {elapsed:.1f} ms")
    assert elapsed < 200


def test_committed_example_is_current(imported):
    committed = Model.model_validate_json(EXAMPLE.read_text())
    assert committed == imported.model, (
        "models/examples/saas_company.json is stale. Run: uv run python -m blockmodel.importers.rows "
        "models/reference/saas_company/generator/spec.py models/examples/saas_company.json "
        "--scenarios churn_rate_q,arpa_monthly"
    )


def test_reference_scenarios_move_npv(imported):
    npv = imported.rows["npv_value"]

    def npv_in(scenario):
        return evaluate(imported.model, scenario=scenario).outputs[str(npv.block)][npv.port].value

    base = npv_in(None)
    assert [s.id for s in imported.model.scenarios] == [
        "low-churn-rate-q",
        "high-churn-rate-q",
        "low-arpa-monthly",
        "high-arpa-monthly",
    ]
    assert npv_in("high-churn-rate-q") < base < npv_in("low-churn-rate-q")  # less churn is worth more
    assert npv_in("low-arpa-monthly") < base < npv_in("high-arpa-monthly")
