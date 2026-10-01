"""Build models in Python: the programmatic path into the editor.

    b = ModelBuilder("Revenue", Timeline(start=date(2027, 1, 1), frequency="quarter", periods=8))
    price = b.constant(12.5, kind="currency", unit="USD/unit", label="Price")
    units = b.series([40, 44, 48, 52, 56, 60, 64, 68], kind="count", unit="unit", label="Units")
    revenue = b.add("math.multiply", a=price, b=units, label="Revenue")
    b.report(revenue, "Revenue")
    model = b.build()   # a Model; save with model.model_dump_json(by_alias=True)

Inputs take a handle (wired from its output) or a literal (set as the inline value).
Block ids are deterministic: uuid5 of the builder's namespace and each block's key.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .library import specs_by_ref
from .model import BlockInstance, Model, Override, PortRef, Position, ReportLine, Scenario, Timeline, Wire
from .spec import BlockSpec

COLUMN_WIDTH = 380.0
ROW_GAP = 40.0


@dataclass(frozen=True)
class Out:
    block: uuid.UUID
    port: str


@dataclass(frozen=True)
class Handle:
    block: uuid.UUID
    spec: BlockSpec = field(compare=False)  # identity is the block id

    @property
    def out(self) -> Out:
        if len(self.spec.outputs) != 1:
            names = ", ".join(p.name for p in self.spec.outputs)
            raise ValueError(f"{self.spec.title} has several outputs ({names}); pick one with .port(name)")
        return Out(self.block, self.spec.outputs[0].name)

    def port(self, name: str) -> Out:
        if name not in {p.name for p in self.spec.outputs}:
            raise ValueError(f"{self.spec.title} has no output named {name}")
        return Out(self.block, name)


class ModelBuilder:
    def __init__(self, name: str, timeline: Timeline, *, namespace: str | None = None):
        self.name = name
        self.timeline = timeline
        self._ns = uuid.uuid5(uuid.NAMESPACE_URL, f"blockmodel:{namespace or name}")
        self._blocks: list[BlockInstance] = []
        self._wires: list[Wire] = []
        self._report: list[ReportLine] = []
        self._scenarios: list[Scenario] = []
        self._keys: set[str] = set()
        self._timeline_block: Handle | None = None

    def _uid(self, key: str) -> uuid.UUID:
        if key in self._keys:
            raise ValueError(f"duplicate block key {key}")
        self._keys.add(key)
        return uuid.uuid5(self._ns, key)

    def add(
        self,
        spec: str,
        *,
        label: str | None = None,
        key: str | None = None,
        settings: dict[str, Any] | None = None,
        **inputs: Any,
    ) -> Handle:
        ref = spec if "@" in spec else f"{spec}@1"
        block_spec = specs_by_ref().get(ref)
        if block_spec is None:
            raise ValueError(f"unknown block type {ref}")
        ports = {p.name for p in block_spec.inputs}
        unknown = set(inputs) - ports
        if unknown:
            raise ValueError(
                f"{block_spec.title} has no inputs named {sorted(unknown)}; it has {sorted(ports)}"
            )
        block_id = self._uid(key or f"{block_spec.id}#{len(self._blocks)}")
        inline: dict[str, Any] = {}
        for port, source in inputs.items():
            if isinstance(source, Handle):
                source = source.out
            if isinstance(source, Out):
                self._wires.append(
                    Wire(
                        uuid=uuid.uuid5(block_id, port),
                        from_=PortRef(block=source.block, port=source.port),
                        to=PortRef(block=block_id, port=port),
                    )
                )
            elif isinstance(source, bool | int | float | str):
                inline[port] = source
            else:
                raise TypeError(
                    f"input {port} takes a handle, an output, or a literal, not {type(source).__name__}"
                )
        self._blocks.append(
            BlockInstance(
                uuid=block_id,
                spec=ref,
                label=label,
                inline=inline,
                settings=settings or {},
                position=Position(x=0, y=0),
            )
        )
        return Handle(block_id, block_spec)

    def constant(self, value: Any, kind: str = "float", unit: str | None = None, **kw: Any) -> Handle:
        settings = {"value": value, "kind": kind, "unit": unit, **_source(kw)}
        return self.add("source.constant", settings=settings, **kw)

    def series(self, values: list, kind: str = "float", unit: str | None = None, **kw: Any) -> Handle:
        settings = {"values": list(values), "kind": kind, "unit": unit, **_source(kw)}
        return self.add("source.series", settings=settings, **kw)

    def timeline_block(self) -> Handle:
        """The model's one Timeline block, created on first use."""
        if self._timeline_block is None:
            self._timeline_block = self.add("source.timeline", label="Timeline", key="timeline")
        return self._timeline_block

    def set_settings(self, handle: Handle, **settings: Any) -> None:
        for i, b in enumerate(self._blocks):
            if b.uuid == handle.block:
                self._blocks[i] = b.model_copy(update={"settings": {**b.settings, **settings}})
                return
        raise ValueError("unknown block")

    def connect(self, source: Handle | Out, target: Handle, port: str) -> None:
        """Wires an existing block's input after the fact; how a Feedback block gets the value it carries."""
        source = source.out if isinstance(source, Handle) else source
        if port not in {p.name for p in target.spec.inputs}:
            raise ValueError(f"{target.spec.title} has no input named {port}")
        self._wires = [w for w in self._wires if not (w.to.block == target.block and w.to.port == port)]
        self._wires.append(
            Wire(
                uuid=uuid.uuid5(target.block, port),
                from_=PortRef(block=source.block, port=source.port),
                to=PortRef(block=target.block, port=port),
            )
        )

    def scenario(self, id: str, name: str, overrides: dict[Handle, dict[str, Any]]) -> None:
        """A named set of setting overrides, e.g. {price: {"value": 14.0}}."""
        self._scenarios.append(
            Scenario(
                id=id,
                name=name,
                overrides=[Override(block=h.block, settings=o) for h, o in overrides.items()],
            )
        )

    def report(self, out: Handle | Out, label: str, format: str | None = None) -> None:
        out = out.out if isinstance(out, Handle) else out
        self._report.append(ReportLine(block=out.block, port=out.port, label=label, format=format))

    def build(self, *, layout: bool = True) -> Model:
        blocks = _layered(self._blocks, self._wires) if layout else list(self._blocks)
        return Model(
            schema_version=1,
            id=uuid.uuid5(self._ns, "model"),
            name=self.name,
            timeline=self.timeline,
            blocks=blocks,
            wires=list(self._wires),
            report=list(self._report),
            scenarios=list(self._scenarios),
        )


def _source(kw: dict[str, Any]) -> dict[str, Any]:
    return {k: kw.pop(k) for k in ("source", "notes") if k in kw}


def _height(block: BlockInstance, wired: set[str]) -> float:
    """Generous rendered height of a block node: header (which may wrap), kind line, one line per shown
    port, and a preview. Optional inputs that are unwired and unset are hidden except one free slot."""
    spec = specs_by_ref().get(block.spec)
    if spec is None:
        return 200.0
    shown = [p for p in spec.inputs if p.required or p.name in wired or p.name in block.inline]
    free = [p for p in spec.inputs if p not in shown]
    ports = len(shown) + min(len(free), 1) + len(spec.outputs)
    return 110 + 26 * ports + 56


def _layered(blocks: list[BlockInstance], wires: list[Wire]) -> list[BlockInstance]:
    """A layered layout that reads left to right.

    - Columns by dependency depth; a source (no inputs) sits one column left of its first consumer
      rather than in a single tall column of every source.
    - Within a column, blocks are ordered by the average row of their neighbours (parents, or
      children for sources), which keeps wires short.
    - Blocks stack by estimated height, so small blocks don't leave large gaps.
    """
    parents: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    children: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    wired: dict[uuid.UUID, set[str]] = defaultdict(set)
    feedback = {b.uuid for b in blocks if b.spec == "series.feedback@1"}
    for w in wires:
        wired[w.to.block].add(w.to.port)
        if w.to.block in feedback and w.to.port == "x":
            continue  # the loop's back edge; laying out by it would never settle
        parents[w.to.block].append(w.from_.block)
        children[w.from_.block].append(w.to.block)
    depth: dict[uuid.UUID, int] = {}
    for b in blocks:  # insertion order is a topological order: a block's inputs exist before it
        depth[b.uuid] = 1 + max((depth[p] for p in parents[b.uuid]), default=-1)
    for b in blocks:
        if not parents[b.uuid] and children[b.uuid]:
            depth[b.uuid] = max(0, min(depth[c] for c in children[b.uuid]) - 1)

    columns: dict[int, list[BlockInstance]] = defaultdict(list)
    for b in blocks:
        columns[depth[b.uuid]].append(b)
    rank: dict[uuid.UUID, float] = {}
    for d in sorted(columns):

        def key(b: BlockInstance, index: int) -> float:
            known = [rank[p] for p in parents[b.uuid] if p in rank]
            return sum(known) / len(known) if known else float(index)

        columns[d] = [b for _, b in sorted(((key(b, i), i), b) for i, b in enumerate(columns[d]))]
        for i, b in enumerate(columns[d]):
            rank[b.uuid] = float(i)
    # Sources were ranked before their consumers; re-rank them by their children's rows.
    for d in sorted(columns):

        def child_key(b: BlockInstance, index: int) -> float:
            if parents[b.uuid] or not children[b.uuid]:
                return rank[b.uuid]
            return sum(rank[c] for c in children[b.uuid]) / len(children[b.uuid])

        columns[d] = [b for _, b in sorted(((child_key(b, i), i), b) for i, b in enumerate(columns[d]))]

    placed = {}
    for d, column in columns.items():
        y = 0.0
        for b in column:
            placed[b.uuid] = b.model_copy(update={"position": Position(x=d * COLUMN_WIDTH, y=y)})
            y += _height(b, wired[b.uuid]) + ROW_GAP
    return [placed[b.uuid] for b in blocks]
