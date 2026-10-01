"""Import a model written as rows: drivers, per-period series, and formula rows.

This is the format of the reference model's `generator/spec.py`:
module-level TIMELINE, DRIVERS, SERIES, CALCS, ANNUAL and REPORT. Each formula
becomes library blocks; each row's top block carries the row's label, and its
declared type is checked against the engine's inferred type:
- the shape must match;
- a different kind or unit becomes a retype (display_kind, display_unit);
- a retype the rules forbid (into or out of currency) fails the import.

    uv run python -m blockmodel.importers.rows <spec.py> <out.json> [--scenarios driver_a,driver_b]
"""

import runpy
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from uuid import UUID

from ..builder import Handle, ModelBuilder, Out
from ..evaluate import evaluate
from ..library import specs_by_ref
from ..model import Model, Timeline
from ..types import parse_type
from .formula import BUILTINS, parse

UNIT_KINDS = ("currency", "quantity", "count")

BINARY = {"+": "math.add", "-": "math.subtract", "*": "math.multiply", "/": "math.divide"}
COMPARE = {">", "<", ">=", "<=", "=="}
CALLS = {
    # function: (spec id, input ports in argument order)
    "min": ("math.min", ("a", "b")),
    "max": ("math.max", ("a", "b")),
    "pow": ("math.power", ("a", "b")),
    "safe_divide": ("math.safe_divide", ("a", "b", "fallback")),
    "ceiling": ("math.ceiling", ("x",)),
    "round": ("math.round", ("x", "digits")),
    "if": ("logic.if", ("condition", "then", "else")),
    "growth": ("source.growth", ("start", "rate")),
    "step": ("source.step", ("value", "from_period")),
    "flag": ("source.flag", ("start", "end")),
    "spread": ("source.spread", ("amount", "start", "periods")),
    "discount_factor": ("finance.discount_factor", ("rate",)),
    "npv": ("finance.npv", ("rate", "cash_flow")),
    "irr": ("finance.irr", ("cash_flow", "guess")),
    "depreciation_sl": ("finance.depreciation_sl", ("capex", "life")),
    "lag": ("series.lag", ("x", "n")),
    "cumulative": ("series.accumulate", ("x", "opening")),
    "running_max": ("series.running_max", ("x",)),
    "total": ("series.total", ("x",)),
    "annual": ("series.annual", ("x",)),
}


class ImportFailure(Exception):
    pass


@dataclass
class Imported:
    model: Model
    rows: dict[str, Out]  # row id -> the output holding its values
    retyped: dict[str, str] = field(default_factory=dict)  # row id -> "inferred -> declared"


def _unit(kind: str, unit: str | None) -> str | None:
    return unit if kind in UNIT_KINDS and unit else None


class FormulaBuilder:
    """Turns a formula into library blocks inside a ModelBuilder; names resolve through `env`."""

    def __init__(self, b: ModelBuilder, env: dict[str, Out]):
        self.b, self.env = b, env

    def formula(self, text: str, key: str, label: str | None = None) -> Out:
        out = self.node(parse(text), key=key, label=label)
        if not isinstance(out, Out):
            raise ImportFailure(f"{key}: a formula must compute something; {text!r} is a bare number")
        return out

    def node(self, node, key: str, label: str | None = None):
        """Returns an Out for wired values, or a Python number for literals."""
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "var":
            name = node[1]
            if name in BUILTINS:
                return self.b.timeline_block().port(name)
            if name not in self.env:
                raise ImportFailure(f"{key}: {name} is used before it is defined")
            return self.env[name]
        if kind == "neg":
            return self.b.add(
                "math.subtract", a=0, b=self.node(node[1], f"{key}.n"), label=label, key=key
            ).out
        if kind == "bin":
            op, left, right = node[1], node[2], node[3]
            a, b = self.node(left, f"{key}.l"), self.node(right, f"{key}.r")
            if op in COMPARE:
                return self.b.add("logic.compare", a=a, b=b, settings={"op": op}, label=label, key=key).out
            return self.b.add(BINARY[op], a=a, b=b, label=label, key=key).out
        name, args = node[1], node[2]
        if name == "sum":
            if len(args) > 8:
                raise ImportFailure(f"{key}: sum takes at most 8 inputs")
            inputs = {f"in{i + 1}": self.node(arg, f"{key}.{i}") for i, arg in enumerate(args)}
            return self.b.add("math.sum", label=label, key=key, **inputs).out
        spec, ports = CALLS[name]
        if len(args) > len(ports):
            raise ImportFailure(f"{key}: {name} takes at most {len(ports)} arguments")
        inputs = {
            port: self.node(arg, f"{key}.{i}") for i, (port, arg) in enumerate(zip(ports, args, strict=False))
        }
        return self.b.add(spec, label=label, key=key, **inputs).out


def _declare(
    b: ModelBuilder, row_id: str, out: Out, declared_text: str, unit: str | None, imported: Imported
):
    """Check the row's declared type against inference; retype where the rules allow."""
    model = b.build(layout=False)
    result = evaluate(model, compute=False)
    block_errors = [e.message for e in result.errors if e.block == out.block]
    if block_errors or str(out.block) not in result.outputs:
        raise ImportFailure(f"{row_id}: {block_errors or [e.message for e in result.errors]}")
    got = result.outputs[str(out.block)][out.port]
    declared = parse_type(declared_text)
    got_type = parse_type(got.type)
    if got_type.shape != declared.shape:
        raise ImportFailure(f"{row_id}: declared {declared_text}, but the engine infers {got.type}")
    want_unit = _unit(declared.kind, unit)
    settings = {}
    if got_type.kind != declared.kind:
        settings["display_kind"] = declared.kind
    if want_unit != got.unit and (declared.kind in UNIT_KINDS):
        settings["display_unit"] = want_unit
    if settings:
        b.set_settings(Handle(out.block, _spec_of(model, out.block)), **settings)
        imported.retyped[row_id] = f"{got.type} ({got.unit}) -> {declared_text} ({want_unit})"
        check = evaluate(b.build(layout=False), compute=False)
        problems = [e.message for e in check.errors if e.block == out.block]
        if problems:
            raise ImportFailure(f"{row_id}: can't retype {got.type} as {declared_text}: {problems[0]}")


def _spec_of(model: Model, block: UUID):
    ref = next(b.spec for b in model.blocks if b.uuid == block)
    return specs_by_ref()[ref]


def import_rows(
    path: str | Path,
    *,
    name: str | None = None,
    namespace: str | None = None,
    scenario_drivers: Sequence[str] = (),
) -> Imported:
    """`scenario_drivers` names scalar drivers whose low and high values become Low and High scenarios."""
    g = runpy.run_path(str(path))
    tl = g["TIMELINE"]
    timeline = Timeline(
        start=date.fromisoformat(tl["start_date"]),
        frequency=tl["frequency"],
        periods=tl["periods"],
        fiscal_year_end=tl.get("fiscal_year_end", "12-31"),
    )
    stem = Path(path).parent.parent.name if Path(path).parent.name == "generator" else Path(path).stem
    b = ModelBuilder(name or f"Reference model: {stem}", timeline, namespace=namespace or stem)
    env: dict[str, Out] = {}
    imported = Imported(model=None, rows={})  # type: ignore[arg-type]

    for ident, label, _group, typ, unit, value, *_rest in g["DRIVERS"]:
        source, notes = _rest[2], _rest[3]
        t = parse_type(typ)
        common = dict(
            kind=t.kind, unit=_unit(t.kind, unit), label=label, key=ident, source=source, notes=notes
        )
        if value == "series":
            h = b.series(g["SERIES"][ident], **common)
        else:
            h = b.constant(value, **common)
        env[ident] = h.out

    formulas = FormulaBuilder(b, env)
    formula_rows = [(r[0], r[1], r[3], r[4], r[5]) for r in g["CALCS"]]
    formula_rows += [(r[0], r[1], f"annual<{r[2]}>", r[3], r[4]) for r in g.get("ANNUAL", [])]
    for ident, label, declared, unit, formula in formula_rows:
        if ident in env:
            raise ImportFailure(f"{ident} is defined twice")
        out = formulas.node(parse(formula), key=ident, label=label)
        if not isinstance(out, Out):
            raise ImportFailure(f"{ident}: a row must compute something; {formula!r} is a bare number")
        if out in env.values():
            raise ImportFailure(f"{ident}: {formula!r} only renames another row; reference that row instead")
        _declare(b, ident, out, declared, unit, imported)
        env[ident] = out
        imported.rows[ident] = out

    labels = {r[0]: r[1] for r in (*g["DRIVERS"], *g["CALCS"], *g.get("ANNUAL", []))}
    for ident, fmt, *_ in g.get("REPORT", []):
        target = imported.rows.get(ident) or env.get(ident)
        if target is None:
            raise ImportFailure(f"report line {ident} is not a row")
        b.report(target, labels.get(ident, ident), fmt)

    drivers = {d[0]: d for d in g["DRIVERS"]}
    for ident in scenario_drivers:
        if ident not in drivers:
            raise ImportFailure(f"scenario driver {ident} is not a driver")
        _, label, *_x = drivers[ident]
        low, high = drivers[ident][6], drivers[ident][7]
        if low is None or high is None:
            raise ImportFailure(f"scenario driver {ident} has no low and high values")
        handle = Handle(env[ident].block, specs_by_ref()["source.constant@1"])
        slug = ident.replace("_", "-")
        b.scenario(f"low-{slug}", f"Low {label[0].lower()}{label[1:]}", {handle: {"value": low}})
        b.scenario(f"high-{slug}", f"High {label[0].lower()}{label[1:]}", {handle: {"value": high}})

    imported.model = b.build()
    return imported


def main(argv: list[str]) -> int:
    scenarios: list[str] = []
    if "--scenarios" in argv:
        i = argv.index("--scenarios")
        scenarios = [x for x in argv[i + 1].split(",") if x]
        argv = argv[:i] + argv[i + 2 :]
    if len(argv) != 2:
        print(__doc__)
        return 2
    imported = import_rows(argv[0], scenario_drivers=scenarios)
    Path(argv[1]).write_text(imported.model.model_dump_json(by_alias=True, indent=1) + "\n")
    print(f"wrote {argv[1]}: {len(imported.model.blocks)} blocks, {len(imported.model.wires)} wires")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
