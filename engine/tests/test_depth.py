"""Phase 4 modeling depth: feedback loops, lookup tables, scenarios, subsystems, unit warnings."""

import json
from datetime import date
from pathlib import Path

import pytest
from blockmodel.builder import ModelBuilder
from blockmodel.compose import ScenarioError
from blockmodel.evaluate import evaluate
from blockmodel.examples import EXAMPLES, EXAMPLES_DIR, cash_interest_model
from blockmodel.model import Model, Timeline

TL = Timeline(start=date(2027, 1, 1), frequency="quarter", periods=6)
DEMO = json.loads((Path(__file__).resolve().parents[2] / "models" / "examples" / "demo.json").read_text())
PRICE, UNITS, PRODUCT, TOTAL = (b["uuid"] for b in DEMO["blocks"])


def value(result, block, port="result"):
    return result.outputs[str(block)][port].value


def by_label(model: Model, label: str):
    return next(b for b in model.blocks if b.label == label)


# ---------------------------------------------------------------- feedback


def test_feedback_loop_matches_a_hand_written_period_loop():
    model = cash_interest_model()
    result = evaluate(model)
    assert result.errors == []
    got = value(result, by_label(model, "Cash at end of quarter").uuid)
    flows = by_label(model, "Operating cash flow").settings["values"]
    cash, want = 1_000_000.0, []
    for f in flows:
        cash = cash + f + 0.02 * cash
        want.append(cash)
    assert got == pytest.approx(want, rel=1e-15)
    previous = value(result, by_label(model, "Cash at start of quarter").uuid, "value")
    assert previous[0] == 1_000_000 and previous[1:] == pytest.approx(want[:-1], rel=1e-15)


def test_loops_without_feedback_are_still_errors():
    b = ModelBuilder("loop", TL)
    x = b.series([1, 2, 3, 4, 5, 6])
    a = b.add("math.add", a=x, b=1, key="a")
    c = b.add("math.add", a=a, b=1, key="c")
    b.connect(c, a, "b")
    [error] = evaluate(b.build(layout=False)).errors
    assert error.block is None and "Feedback" in error.message


def test_feedback_checks_the_carried_type():
    b = ModelBuilder("types", TL)
    fb = b.add("series.feedback", initial=b.constant(5, kind="currency"), key="fb")
    pct = b.add("math.multiply", a=b.series([0.1] * 6, kind="percent"), b=fb, key="pct")
    ratio = b.add("math.divide", a=pct, b=b.constant(2, kind="currency"), key="ratio")
    b.connect(ratio, fb, "x")
    errors = {str(e.block): e.message for e in evaluate(b.build(layout=False)).errors}
    assert "this Feedback carries series<currency>" in errors[str(fb.block)]


def test_blocks_that_use_every_period_cant_sit_in_a_loop():
    b = ModelBuilder("noncausal", TL)
    fb = b.add("series.feedback", initial=0, key="fb")
    total = b.add("series.total", x=fb, key="total")
    plus = b.add("math.add", a=total, b=b.series([1] * 6), key="plus")
    b.connect(plus, fb, "x")
    errors = {str(e.block): e.message for e in evaluate(b.build(layout=False)).errors}
    assert "can't sit inside a feedback loop" in errors[str(total.block)]


def test_unwired_feedback_is_explained():
    b = ModelBuilder("unwired", TL)
    fb = b.add("series.feedback", initial=3, key="fb")
    errors = {str(e.block): e.message for e in evaluate(b.build()).errors}
    assert "Input x is not wired" in errors[str(fb.block)]


# ---------------------------------------------------------------- lookup


@pytest.mark.parametrize(
    "mode, want",
    [("step", [10, 10, 12, 12, 15, 15]), ("linear", [10, 11, 12, 13.5, 15, 15])],
)
def test_lookup_step_and_linear_with_clamping(mode, want):
    b = ModelBuilder("lookup", TL)
    x = b.series([0, 50, 100, 150, 200, 300])
    out = b.add(
        "lookup.table",
        x=x,
        settings={
            "keys": [0, 100, 200],
            "values": [10, 12, 15],
            "mode": mode,
            "kind": "currency",
            "unit": "USD/kg",
        },
    )
    result = evaluate(b.build())
    assert result.errors == []
    assert value(result, out.block) == pytest.approx(want)
    assert result.outputs[str(out.block)]["result"].unit == "USD/kg"


def test_lookup_table_errors():
    b = ModelBuilder("lookup errors", TL)
    bad = b.add("lookup.table", x=b.constant(1), settings={"keys": [2, 1], "values": [1, 2]})
    errors = {str(e.block): e.message for e in evaluate(b.build()).errors}
    assert "strictly ascending" in errors[str(bad.block)]


# ---------------------------------------------------------------- scenarios


def test_scenario_overrides_and_errors():
    model = cash_interest_model()
    cash = by_label(model, "Cash at end of quarter").uuid
    base = value(evaluate(model), cash)[-1]
    high = evaluate(model, scenario="high-rate")
    assert high.scenario == "high-rate"
    assert value(high, cash)[-1] > base
    with pytest.raises(ScenarioError, match="high-rate"):
        evaluate(model, scenario="nope")
    stale = model.model_copy(
        update={"blocks": [b for b in model.blocks if b.label != "Interest rate per quarter"]}
    )
    result = evaluate(stale, scenario="high-rate")
    assert any("no longer exists" in w.message for w in result.warnings)


# ---------------------------------------------------------------- subsystems


def demo_with_subsystem(nest: bool = False) -> Model:
    """The demo with Product revenue and Total revenue grouped into a subsystem."""
    data = json.loads(json.dumps(DEMO))
    inner_blocks = [b for b in data["blocks"] if b["uuid"] in (PRODUCT, TOTAL)]
    inner_wires = [w for w in data["wires"] if w["from"]["block"] == PRODUCT]
    composite = {
        "id": "user.revenue",
        "title": "Revenue",
        "inputs": [
            {"name": "price", "targets": [{"block": PRODUCT, "port": "a"}]},
            {"name": "units", "targets": [{"block": PRODUCT, "port": "b"}]},
            {"name": "other", "targets": [{"block": TOTAL, "port": "b"}]},
        ],
        "outputs": [{"name": "total", "source": {"block": TOTAL, "port": "result"}}],
        "blocks": inner_blocks,
        "wires": inner_wires,
    }
    instance = "9a1b6f7e-0000-4000-8000-000000000001"
    data["composites"] = [composite]
    data["blocks"] = [b for b in data["blocks"] if b["uuid"] in (PRICE, UNITS)] + [
        {
            "uuid": instance,
            "spec": "user.revenue@1",
            "label": "Revenue",
            "inline": {"other": 150},
            "position": {"x": 300, "y": 0},
        }
    ]
    data["wires"] = [
        {
            "uuid": "9a1b6f7e-0000-4000-8000-0000000000a1",
            "from": {"block": PRICE, "port": "value"},
            "to": {"block": instance, "port": "price"},
        },
        {
            "uuid": "9a1b6f7e-0000-4000-8000-0000000000a2",
            "from": {"block": UNITS, "port": "value"},
            "to": {"block": instance, "port": "units"},
        },
    ]
    if nest:
        outer = {
            "id": "user.outer",
            "title": "Outer",
            "inputs": [
                {"name": "price", "targets": [{"block": instance, "port": "price"}]},
                {"name": "units", "targets": [{"block": instance, "port": "units"}]},
            ],
            "outputs": [{"name": "total", "source": {"block": instance, "port": "total"}}],
            "blocks": [data["blocks"][2]],
            "wires": [],
        }
        outer_instance = "9a1b6f7e-0000-4000-8000-000000000002"
        data["composites"].append(outer)
        data["blocks"] = data["blocks"][:2] + [
            {"uuid": outer_instance, "spec": "user.outer@1", "position": {"x": 300, "y": 0}}
        ]
        for w in data["wires"]:
            w["to"]["block"] = outer_instance
    return Model.model_validate(data)


def test_subsystem_evaluates_like_the_flat_model():
    flat = evaluate(Model.model_validate(DEMO))
    model = demo_with_subsystem()
    result = evaluate(model)
    assert result.errors == []
    instance = model.blocks[2].uuid
    assert value(result, instance, "total") == value(flat, TOTAL)
    assert result.outputs[str(instance)]["total"].type == "series<currency>"
    # Inner blocks report under instance/inner keys, for viewing inside the subsystem.
    assert value(result, f"{instance}/{PRODUCT}") == value(flat, PRODUCT)


def test_nested_subsystems():
    flat = evaluate(Model.model_validate(DEMO))
    model = demo_with_subsystem(nest=True)
    result = evaluate(model)
    assert result.errors == []
    assert value(result, model.blocks[2].uuid, "total") == value(flat, TOTAL)


def test_errors_inside_a_subsystem_name_the_inner_block():
    model = demo_with_subsystem()
    composite = model.composites[0]
    broken = composite.model_copy(
        update={
            "blocks": [
                b.model_copy(update={"spec": "math.nope@1"}) if str(b.uuid) == PRODUCT else b
                for b in composite.blocks
            ]
        }
    )
    result = evaluate(model.model_copy(update={"composites": [broken]}))
    inside = [e for e in result.errors if e.path]
    assert inside and inside[0].block == model.blocks[2].uuid
    assert inside[0].path == f"{model.blocks[2].uuid}/{PRODUCT}"
    assert inside[0].message.startswith("Inside Revenue, Product revenue: Unknown block type")


def test_a_subsystem_cant_contain_itself():
    model = demo_with_subsystem()
    composite = model.composites[0]
    selfish = composite.model_copy(
        update={
            "blocks": [*composite.blocks, model.blocks[2].model_copy(update={"uuid": model.blocks[0].uuid})]
        }
    )
    result = evaluate(model.model_copy(update={"composites": [selfish]}))
    assert any("contains itself" in e.message for e in result.errors)


# ---------------------------------------------------------------- units and examples


def test_unit_mismatches_are_warnings_not_errors():
    b = ModelBuilder("units", TL)
    out = b.add(
        "math.min",
        a=b.constant(3, kind="count", unit="orders"),
        b=b.constant(4, kind="count", unit="vehicles"),
    )
    result = evaluate(b.build())
    assert result.errors == []
    [warning] = result.warnings
    assert warning.block == out.block and "Check units" in warning.message


def test_code_built_examples_are_current():
    for name, make in EXAMPLES.items():
        committed = Model.model_validate_json((EXAMPLES_DIR / f"{name}.json").read_text())
        assert committed == make(), (
            f"models/examples/{name}.json is stale. Run: uv run python -m blockmodel.examples"
        )
