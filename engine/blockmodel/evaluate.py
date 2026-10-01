"""Evaluate a model: check wires, order blocks, infer types, compute values.

One failing block doesn't stop the run. Its error names what happened and how to
fix it, and blocks downstream of it report which upstream block to fix first.
"""

import time
from collections.abc import Collection
from datetime import date
from functools import cache
from graphlib import CycleError, TopologicalSorter
from typing import Any
from uuid import UUID

import numpy as np

from .compose import Flat, apply_scenario, flatten
from .library import impl_for, specs_by_ref
from .library.registry import BlockFailure, Ctx, Value
from .model import BlockError, BlockInstance, EvaluateResponse, Model, PortResult, TimelineInfo, Timing
from .spec import BlockSpec, PortSpec
from .timeline import TimelineCalc, build_timeline
from .types import INTEGER, Pattern, Type, TypeRuleError, additive, collect_warnings, parse_pattern, retype

ENGINE = "blockmodel 0.4.0"


@cache
def _pattern(text: str) -> Pattern:
    return parse_pattern(text)


def _name(block: BlockInstance, spec: BlockSpec | None) -> str:
    return block.label or (spec.title if spec else block.spec)


def _literal_type(port: PortSpec, value: Any) -> Type:
    pattern = _pattern(port.type)
    if isinstance(value, bool):
        t = Type("scalar", "bool")
    elif isinstance(value, int | float):
        if pattern.kinds == INTEGER:
            if not float(value).is_integer():
                raise TypeRuleError(f"Input {port.name} needs a whole number; {value:g} isn't one.")
            t = Type("scalar", "int")
        else:
            t = Type("scalar", "float", literal=True)
    else:
        t = Type("scalar", "str")
    pattern.check(port.name, t)
    return t


def _retype(block: BlockInstance, out: dict[str, Type]) -> dict[str, Type]:
    kind, unit = block.settings.get("display_kind"), block.settings.get("display_unit")
    if kind is None and unit is None:
        return out
    if len(out) != 1:
        raise TypeRuleError("Retype applies to blocks with one output. Remove display_kind and display_unit.")
    ((port, t),) = out.items()
    return {port: retype(t, kind, unit)}


def _normalize(value: Value, t: Type, tl: TimelineCalc) -> Value:
    """Per-period outputs become full-length arrays; scalar outputs become plain Python values."""
    if t.per_period:
        if not isinstance(value, np.ndarray) or value.ndim == 0:
            value = np.full(tl.length(t.shape), value, dtype=bool if t.kind == "bool" else float)
        return value
    if isinstance(value, np.ndarray):
        value = value.item()
    return value


def _check_values(value: Value, t: Type, tl: TimelineCalc) -> str | None:
    if t.kind in ("bool", "str", "date"):
        return None
    arr = np.atleast_1d(np.asarray(value, dtype=float))
    bad = np.flatnonzero(~np.isfinite(arr))
    if bad.size:
        where = f" in period {tl.label(t.shape, int(bad[0]))}" if t.per_period else ""
        return f"The result is not a finite number{where}. Check the inputs, for example a negative base in Power."
    if t.kind == "count" and not np.all(arr == np.round(arr)):
        return "A count must be whole numbers, but this result isn't. Round it first, or retype it as a quantity."
    return None


def _serialize(value: Value, t: Type):
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "M":
            return [str(d) for d in value.astype("datetime64[D]")]
        if t.kind == "bool":
            return value.astype(bool).tolist()
        if t.kind in INTEGER and np.all(value == np.round(value)):
            return value.astype(np.int64).tolist()
        return value.astype(float).tolist()
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if t.kind in INTEGER and float(value).is_integer():
        return int(value)
    return float(value)


FEEDBACK = "series.feedback@1"


def evaluate(
    model: Model,
    *,
    compute: bool = True,
    include: Collection[str] | None = None,
    scenario: str | None = None,
) -> EvaluateResponse:
    """Infer types for every block and, when `compute`, their values.

    - `scenario` applies that scenario's overrides first (ScenarioError if it doesn't exist).
    - Subsystems are flattened; blocks inside them report under "instance/inner" keys.
    - Cycles are allowed only through Feedback blocks; loops are solved by iterating until stable,
      which is exact after at most one pass per period because each pass fixes one more period.
    - `include` limits which blocks' values are returned (types, errors and warnings always are).
    """
    started = time.perf_counter()
    model, scenario_warnings = apply_scenario(model, scenario)
    tl = build_timeline(model.timeline)
    flat = flatten(model)
    run = _Run(flat, tl, compute)
    for message in scenario_warnings:
        run.warn(None, message)
    for block, message in flat.errors:
        run.fail(block, message)
    if run.wire_up():
        run.evaluate()
    return run.response(started, include, scenario)


class _Run:
    def __init__(self, flat: Flat, tl: TimelineCalc, compute: bool):
        library = specs_by_ref()
        self.flat, self.tl, self.compute = flat, tl, compute
        self.blocks = {b.uuid: b for b in flat.blocks}
        self.specs = {u: library.get(b.spec) for u, b in self.blocks.items()}
        self.errors: dict[UUID | None, list[str]] = {}
        # Wire problems stay reported even when the block itself evaluates.
        self.structural: dict[UUID | None, list[str]] = {}
        self.warnings: dict[UUID | None, list[str]] = {}
        self.types: dict[UUID, dict[str, Type]] = {}
        self.values: dict[UUID, dict[str, Value]] = {}
        self.failed: set[UUID] = set()
        self.incoming: dict[UUID, dict[str, tuple[UUID, str]]] = {u: {} for u in self.blocks}
        self.feedback = {u for u, b in self.blocks.items() if b.spec == FEEDBACK}
        self.order: list[UUID] = []

    # ------------------------------------------------------------ bookkeeping

    def fail(self, block: UUID | None, message: str) -> None:
        if block is None:
            self.errors.setdefault(None, []).append(message)
        else:
            self.errors[block] = [message]  # the latest attempt's error replaces an earlier one
            self.failed.add(block)
            self.types.pop(block, None)
            self.values.pop(block, None)

    def structure(self, block: UUID | None, message: str) -> None:
        self.structural.setdefault(block, []).append(message)

    def warn(self, block: UUID | None, message: str) -> None:
        bucket = self.warnings.setdefault(block, [])
        if message not in bucket:
            bucket.append(message)

    def name(self, u: UUID) -> str:
        return _name(self.blocks[u], self.specs[u])

    # ------------------------------------------------------------ structure

    def wire_up(self) -> bool:
        """Checks wires and orders blocks. False when the order can't be found (a loop without Feedback)."""
        for w in self.flat.wires:
            src, dst = w.from_, w.to
            if src.block not in self.blocks or dst.block not in self.blocks:
                self.structure(None, f"Wire {w.uuid} connects a block that doesn't exist. Delete the wire.")
                continue
            dst_spec, src_spec = self.specs[dst.block], self.specs[src.block]
            if dst_spec and dst.port not in {p.name for p in dst_spec.inputs}:
                self.structure(dst.block, f"{dst_spec.title} has no input named {dst.port}. Delete the wire.")
                continue
            if src_spec and src.port not in {p.name for p in src_spec.outputs}:
                self.structure(
                    dst.block,
                    f"Input {dst.port} is wired to {src_spec.title}'s {src.port}, which doesn't exist. Rewire it.",
                )
                continue
            if dst.port in self.incoming[dst.block]:
                self.structure(
                    dst.block, f"Input {dst.port} has more than one wire. Keep one and delete the others."
                )
                continue
            self.incoming[dst.block][dst.port] = (src.block, src.port)

        self.graph = {
            u: {src for port, (src, _) in ports.items() if not (u in self.feedback and port == "x")}
            for u, ports in self.incoming.items()
        }
        try:
            self.order = list(TopologicalSorter(self.graph).static_order())
        except CycleError as exc:
            names = ", ".join(self.name(u) for u in dict.fromkeys(exc.args[1]))
            self.fail(
                None,
                f"Wires form a loop through {names}. Break it with a Feedback block (it passes the previous "
                "period's value), or carry values forward with Lag or Accumulate.",
            )
            return False
        return True

    # ------------------------------------------------------------ evaluation

    def evaluate(self) -> None:
        for u in self.order:
            self.run_block(u)
        if self.feedback:
            self.solve_loops()

    def run_block(self, u: UUID, *, with_x: bool = False) -> None:
        block, spec = self.blocks[u], self.specs[u]
        if spec is None:
            self.fail(u, f"Unknown block type {block.spec}. Replace it with a block from the library.")
            return
        try:
            with collect_warnings() as unit_warnings:
                ctx, in_values = self.gather(u, block, spec, with_x)
                impl = impl_for(spec)
                ctx.out = _retype(block, impl.infer(ctx))
            for message in unit_warnings:
                self.warn(u, message)
            if self.compute:
                with np.errstate(all="ignore"):  # non-finite results are reported by _check_values
                    raw = impl.compute(ctx, in_values)
                out_values = {p: _normalize(raw[p], t, self.tl) for p, t in ctx.out.items()}
                for p, t in ctx.out.items():
                    problem = _check_values(out_values[p], t, self.tl)
                    if problem:
                        raise BlockFailure(problem if len(ctx.out) == 1 else f"Output {p}: {problem}")
                self.values[u] = out_values
            self.types[u] = ctx.out
            self.failed.discard(u)
            self.errors.pop(u, None)
        except (TypeRuleError, BlockFailure) as exc:
            self.fail(u, str(exc))
        except Exception as exc:  # a bug, not a modeling error: report it on the block and keep going
            self.fail(u, f"Internal error in {spec.title} ({type(exc).__name__}: {exc}). Please report this.")

    def gather(self, u, block, spec, with_x: bool):
        in_types: dict[str, Type] = {}
        in_values: dict[str, Value] = {}
        literals: dict[str, Any] = {}
        wired = self.incoming[u]
        for port in spec.inputs:
            if port.name in wired:
                if u in self.feedback and port.name == "x" and not with_x:
                    continue  # the loop's value isn't known on the first pass
                src, src_port = wired[port.name]
                if src in self.failed or src not in self.types:
                    raise BlockFailure(
                        f"Input {port.name} comes from {self.name(src)}, which has an error. Fix that block first."
                    )
                t = self.types[src][src_port]
                _pattern(port.type).check(port.name, t)
                in_types[port.name] = t
                if self.compute:
                    in_values[port.name] = self.values[src][src_port]
                continue
            literal = block.inline.get(port.name, port.inline)
            if literal is None:
                if port.required:
                    raise BlockFailure(
                        f"Input {port.name} is not wired and has no value. Wire it or set a value in the inspector."
                    )
                continue
            in_types[port.name] = _literal_type(port, literal)
            literals[port.name] = literal
            in_values[port.name] = literal if isinstance(literal, bool | str) else float(literal)
        return Ctx(timeline=self.tl, settings=block.settings, types=in_types, literals=literals), in_values

    def solve_loops(self) -> None:
        downstream: dict[UUID, set[UUID]] = {u: set() for u in self.blocks}
        for u, parents in self.graph.items():
            for p in parents:
                downstream[p].add(u)

        def reach(starts, edges) -> set[UUID]:
            seen, stack = set(), list(starts)
            while stack:
                u = stack.pop()
                for v in edges[u]:
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            return seen

        live = []
        for fb in self.feedback:
            if fb in self.failed:
                continue
            if "x" not in self.incoming[fb]:
                self.fail(fb, "Input x is not wired. Wire the value to carry into the next period.")
                continue
            src, port = self.incoming[fb]["x"]
            if src in self.failed or src not in self.types:
                self.fail(
                    fb, f"Input x comes from {self.name(src)}, which has an error. Fix that block first."
                )
                continue
            carried, fed = self.types[fb]["value"], self.types[src][port]
            try:
                additive(fed, carried, "feed back")
            except TypeRuleError as exc:
                self.fail(
                    fb, f"Input x is {fed.describe()}, but this Feedback carries {carried.describe()}. {exc}"
                )
                continue
            # Blocks on the loop itself: downstream of the feedback and upstream of what it carries.
            loop = reach([fb], downstream) & (reach([src], self.graph) | {src})
            bad = [u for u in loop if self.specs[u] is not None and not self.specs[u].causal]
            for u in bad:
                self.fail(
                    u,
                    f"{self.specs[u].title} uses every period at once, so it can't sit inside a feedback loop. "
                    "Move it outside the loop.",
                )
            if not bad:
                live.append(fb)
        if not self.compute or not live:
            return
        region = [u for u in self.order if u in reach(live, downstream) and u not in self.feedback]
        for _ in range(self.tl.periods + 1):
            changed = False
            for fb in live:
                before = self.values.get(fb, {}).get("value")
                self.run_block(fb, with_x=True)
                after = self.values.get(fb, {}).get("value")
                if before is None or after is None or not np.array_equal(before, after):
                    changed = True
            if not changed:
                return
            for u in region:
                self.run_block(u)

    # ------------------------------------------------------------ response

    def response(self, started: float, include, scenario: str | None) -> EvaluateResponse:
        flat = self.flat
        wanted = None if include is None else set(include)

        def key(u: UUID) -> str:
            return flat.path.get(u, str(u))

        def shown(k: str) -> bool:
            return wanted is None or k.split("/")[0] in wanted

        def port_results(u: UUID) -> dict[str, PortResult]:
            show = u in self.values and shown(key(u))
            return {
                p: PortResult.model_construct(
                    type=t.render(), unit=t.unit, value=_serialize(self.values[u][p], t) if show else None
                )
                for p, t in self.types[u].items()
            }

        outputs = {key(u): port_results(u) for u in self.types}
        for instance, ports in flat.instance_outputs.items():
            mapped = {}
            for name, ref in ports.items():
                if ref.block in self.types and ref.port in self.types[ref.block]:
                    t = self.types[ref.block][ref.port]
                    show = ref.block in self.values and shown(str(instance))
                    mapped[name] = PortResult.model_construct(
                        type=t.render(),
                        unit=t.unit,
                        value=_serialize(self.values[ref.block][ref.port], t) if show else None,
                    )
            if mapped:
                outputs[str(instance)] = mapped

        def entries(bucket: dict[UUID | None, list[str]]) -> list[BlockError]:
            out = []
            for u, messages in bucket.items():
                for message in messages:
                    if u is not None and u in flat.owner:
                        owner = flat.owner[u]
                        out.append(
                            BlockError(
                                block=owner,
                                path=flat.path[u],
                                message=f"Inside {flat.titles.get(owner, 'a subsystem')}, {self.name(u)}: {message}",
                            )
                        )
                    else:
                        out.append(BlockError(block=u, message=message))
            return out

        return EvaluateResponse.model_construct(
            engine=ENGINE,
            timeline=TimelineInfo(period_labels=list(self.tl.labels), years=list(self.tl.years)),
            outputs=outputs,
            errors=entries(
                {
                    k: self.structural.get(k, []) + self.errors.get(k, [])
                    for k in {**self.structural, **self.errors}
                }
            ),
            warnings=entries(self.warnings),
            scenario=scenario,
            timing=Timing(evaluate_ms=(time.perf_counter() - started) * 1000),
        )
