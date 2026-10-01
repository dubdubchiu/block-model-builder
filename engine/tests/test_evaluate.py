"""The evaluator: wiring checks, ordering, error messages, filtering, and the demo and synthetic models."""

import json
import time
import uuid
from datetime import date
from pathlib import Path

import pytest
from blockmodel.builder import ModelBuilder
from blockmodel.evaluate import ENGINE, evaluate
from blockmodel.library import load_library
from blockmodel.model import Model, Timeline
from blockmodel.schema import main as schema_main
from blockmodel.synthetic import synthetic_model

DEMO = Path(__file__).resolve().parents[2] / "models" / "examples" / "demo.json"
PRICE, UNITS, PRODUCT, TOTAL = (
    "502cd728-7c8c-43e6-bd27-fa99e7f6ae87",
    "13d82785-1240-40f4-9ed6-8825fe03e2cd",
    "5c818392-f705-482c-a78b-cae77ebfc7ed",
    "121f5ae3-4f9c-4590-9b58-e332ae7e52b0",
)
TL = Timeline(start=date(2027, 1, 1), frequency="quarter", periods=4)


def demo_dict() -> dict:
    return json.loads(DEMO.read_text())


def errors_by_block(result) -> dict[str, str]:
    return {str(e.block): e.message for e in result.errors}


def test_library_has_31_blocks():
    assert len(load_library()) == 31


def test_demo_evaluates_with_types_and_units():
    result = evaluate(Model.model_validate(demo_dict()))
    assert result.errors == []
    assert result.engine == ENGINE
    out = result.outputs
    assert (out[PRICE]["value"].type, out[PRICE]["value"].unit, out[PRICE]["value"].value) == (
        "currency",
        "USD/unit",
        12.5,
    )
    assert out[UNITS]["value"].type == "series<count>"
    product = out[PRODUCT]["result"]
    assert (product.type, product.unit) == ("series<currency>", "USD")  # USD/unit x unit cancels
    assert product.value == [500.0, 550.0, 600.0, 650.0, 700.0, 750.0, 800.0, 850.0]
    # Add takes wire a and inline b = 150, which adopts currency.
    assert out[TOTAL]["result"].value[0] == 650.0
    assert out[TOTAL]["result"].type == "series<currency>"
    assert result.timeline.period_labels[:2] == ["2027Q1", "2027Q2"]


def test_model_round_trips_with_aliases():
    data = demo_dict()
    dumped = Model.model_validate(data).model_dump(mode="json", by_alias=True)
    assert dumped["schemaVersion"] == 1
    assert dumped["wires"][0]["from"] == data["wires"][0]["from"]


def test_unknown_fields_and_bad_timelines_are_rejected():
    data = demo_dict()
    data["blocks"][0]["colour"] = "red"
    with pytest.raises(ValueError):
        Model.model_validate(data)
    with pytest.raises(ValueError, match="first day of a month"):
        Timeline(start=date(2027, 1, 15), frequency="month", periods=3)
    with pytest.raises(ValueError):
        Timeline(start=date(2027, 1, 1), frequency="month", periods=3, fiscal_year_end="02-30")


def test_cycle_is_reported_with_fix():
    data = demo_dict()
    data["wires"][0]["from"] = {"block": TOTAL, "port": "result"}
    result = evaluate(Model.model_validate(data))
    assert result.outputs == {}
    [error] = result.errors
    assert error.block is None
    assert "loop" in error.message and "Feedback" in error.message
    assert "Product revenue" in error.message and "Total revenue" in error.message


def test_error_propagates_downstream():
    data = demo_dict()
    data["blocks"][0]["spec"] = "core.nonexistent@1"
    by_block = errors_by_block(evaluate(Model.model_validate(data)))
    assert "Unknown block type" in by_block[PRICE]
    assert "Fix that block first" in by_block[PRODUCT]
    assert "Fix that block first" in by_block[TOTAL]


def test_wire_checks():
    data = demo_dict()
    extra = dict(data["wires"][0], uuid=str(uuid.uuid4()))
    extra["to"] = data["wires"][1]["to"]
    data["wires"].append(extra)
    assert "more than one wire" in errors_by_block(evaluate(Model.model_validate(data)))[PRODUCT]

    data = demo_dict()
    data["wires"][0]["to"]["port"] = "c"
    assert "no input named c" in errors_by_block(evaluate(Model.model_validate(data)))[PRODUCT]


def model_error(build) -> str:
    b = ModelBuilder("errors", TL)
    target = build(b)
    result = evaluate(b.build())
    return errors_by_block(result)[str(target.block)]


def test_divide_by_zero_names_the_period():
    message = model_error(lambda b: b.add("math.divide", a=b.series([1, 2, 3, 4]), b=b.series([1, 0, 1, 1])))
    assert "period 2027Q2" in message and "Safe divide" in message


def test_bool_in_arithmetic_points_to_if():
    message = model_error(lambda b: b.add("math.multiply", a=b.add("source.flag", start=1, end=2), b=3))
    assert "If block" in message


def test_whole_number_ports():
    message = model_error(lambda b: b.add("series.lag", x=b.series([1, 2, 3, 4]), n=2.5))
    assert "whole number" in message


def test_missing_input():
    message = model_error(lambda b: b.add("math.divide", b=2))
    assert "Input a is not wired and has no value" in message


def test_currency_mixing_is_explained():
    message = model_error(
        lambda b: b.add("math.add", a=b.constant(5, kind="currency"), b=b.constant(0.1, kind="percent"))
    )
    assert "Can't add currency and percent" in message


def test_mixed_frequencies():
    def build(b):
        x = b.series([1, 2, 3, 4])
        return b.add("math.add", a=x, b=b.add("series.annual", x=x))

    assert "per-period and per-year" in model_error(build)


def test_series_input_length():
    assert "has 3 values; the timeline has 4" in model_error(lambda b: b.series([1, 2, 3]))


def test_retype_rules_apply():
    message = model_error(
        lambda b: b.add(
            "math.add", a=b.constant(1, kind="currency"), b=1, settings={"display_kind": "percent"}
        )
    )
    assert "into or out of currency" in message
    message = model_error(
        lambda b: b.add("math.add", a=b.series([0.5, 1, 1, 1]), b=0, settings={"display_kind": "count"})
    )
    assert "whole numbers" in message


def test_non_finite_results_are_errors():
    message = model_error(lambda b: b.add("math.power", a=b.series([4, -1, 4, 4]), b=0.5))
    assert "not a finite number in period 2027Q2" in message


def test_include_and_compute_flags():
    model = Model.model_validate(demo_dict())
    some = evaluate(model, include=[TOTAL])
    assert some.outputs[TOTAL]["result"].value is not None
    assert some.outputs[PRICE]["value"].value is None
    assert some.outputs[PRICE]["value"].type == "currency"
    types_only = evaluate(model, compute=False)
    assert types_only.errors == []
    assert all(p.value is None for ports in types_only.outputs.values() for p in ports.values())
    assert types_only.outputs[TOTAL]["result"].type == "series<currency>"


def test_builder_ids_are_deterministic_and_inputs_checked():
    def build():
        b = ModelBuilder("same", TL)
        b.add("math.add", a=b.constant(1), b=2, key="sum")
        return b.build()

    assert build() == build()
    b = ModelBuilder("bad", TL)
    with pytest.raises(ValueError, match="no inputs named"):
        b.add("math.add", c=1)
    with pytest.raises(ValueError, match="unknown block type"):
        b.add("math.nope")


def test_builder_layout_places_sources_left():
    b = ModelBuilder("layout", TL)
    x = b.series([1, 2, 3, 4])
    y = b.add("math.add", a=x, b=1)
    z = b.add("math.add", a=y, b=x)
    positions = {blk.uuid: blk.position.x for blk in b.build().blocks}
    assert positions[x.block] < positions[y.block] < positions[z.block]


def test_synthetic_model_shape_and_speed():
    model = synthetic_model(blocks=250, periods=120)
    assert len(model.blocks) == 250
    assert len(model.wires) == 2 * (250 - 10)
    assert synthetic_model(blocks=250, periods=120) == model  # seeded

    evaluate(model)  # warm up
    runs = []
    for _ in range(5):
        t0 = time.perf_counter()
        result = evaluate(model)
        runs.append((time.perf_counter() - t0) * 1000)
    assert result.errors == []
    values = [p.value for ports in result.outputs.values() for p in ports.values()]
    assert all(isinstance(v, list) and len(v) == 120 for v in values)
    assert all(abs(x) < 1e12 for v in values for x in v), "synthetic values should stay finite"
    print(f"\nin-process evaluate, 250 blocks by 120 periods: min {min(runs):.2f} ms, max {max(runs):.2f} ms")
    assert min(runs) < 50


def test_schema_file_is_current():
    assert schema_main(["--check"]) == 0, "Run: uv run python -m blockmodel.schema"
