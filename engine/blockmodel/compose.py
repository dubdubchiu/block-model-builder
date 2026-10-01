"""Scenarios and subsystems: turn a model into the flat graph the evaluator runs.

- A scenario overrides top-level blocks' inline values and settings.
- A subsystem (composite) instance is replaced by its inner blocks, with ids derived from the
  instance id, so every instance of a subsystem evaluates independently. Wires into the instance's
  input ports go to the inner targets; wires from its output ports come from the inner sources.
"""

import uuid
from dataclasses import dataclass, field

from .model import BlockInstance, CompositeSpec, Model, PortRef, Wire

MAX_DEPTH = 8


class ScenarioError(ValueError):
    """The requested scenario doesn't exist. The message says how to fix it."""


def apply_scenario(model: Model, scenario_id: str | None) -> tuple[Model, list[str]]:
    """The model with the scenario's overrides applied, plus warnings for overrides that no longer apply."""
    if not scenario_id:
        return model, []
    scenario = next((s for s in model.scenarios if s.id == scenario_id), None)
    if scenario is None:
        names = ", ".join(s.id for s in model.scenarios) or "none"
        raise ScenarioError(f"No scenario with id {scenario_id!r}. This model's scenarios: {names}.")
    by_block = {o.block: o for o in scenario.overrides}
    blocks = []
    for b in model.blocks:
        o = by_block.pop(b.uuid, None)
        if o:
            b = b.model_copy(
                update={"inline": {**b.inline, **o.inline}, "settings": {**b.settings, **o.settings}}
            )
        blocks.append(b)
    warnings = [
        f"Scenario {scenario.name} overrides a block that no longer exists ({block}). Remove the override."
        for block in by_block
    ]
    return model.model_copy(update={"blocks": blocks}), warnings


@dataclass
class Flat:
    blocks: list[BlockInstance]
    wires: list[Wire]
    path: dict[uuid.UUID, str] = field(default_factory=dict)  # inner flat id -> "instance/inner[/...]"
    owner: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)  # inner flat id -> top-level instance
    titles: dict[uuid.UUID, str] = field(default_factory=dict)  # top-level instance -> subsystem title
    instance_outputs: dict[uuid.UUID, dict[str, PortRef]] = field(default_factory=dict)  # top-level only
    errors: list[tuple[uuid.UUID | None, str]] = field(default_factory=list)


def _ref(c: CompositeSpec) -> str:
    return f"{c.id}@{c.version}"


def flatten(model: Model) -> Flat:
    composites = {_ref(c): c for c in model.composites}
    flat = Flat(blocks=[], wires=[])
    if not composites:
        flat.blocks, flat.wires = list(model.blocks), list(model.wires)
        return flat

    def expand(blocks, wires, prefix: str | None, owner: uuid.UUID | None, stack: tuple[str, ...], original):
        """`original` maps each block id at this level to its id in the definition, for paths."""
        out_blocks: list[BlockInstance] = []
        inputs: dict[tuple[uuid.UUID, str], list[PortRef]] = {}
        outputs: dict[tuple[uuid.UUID, str], PortRef] = {}
        for b in blocks:
            comp = composites.get(b.spec)
            key = f"{prefix}/{original.get(b.uuid, b.uuid)}" if prefix else None
            if comp is None:
                out_blocks.append(b)
                if key:
                    flat.path[b.uuid] = key
                    flat.owner[b.uuid] = owner  # type: ignore[assignment]
                continue
            top = owner or b.uuid
            if b.spec in stack or len(stack) >= MAX_DEPTH:
                flat.errors.append((top, f"Subsystem {comp.title} contains itself. Remove the inner copy."))
                continue
            remap = {ib.uuid: uuid.uuid5(b.uuid, str(ib.uuid)) for ib in comp.blocks}
            inner_blocks = [ib.model_copy(update={"uuid": remap[ib.uuid]}) for ib in comp.blocks]
            # The instance's inline values feed the targets of unwired input ports.
            by_id = {ib.uuid: ib for ib in inner_blocks}
            for port in comp.inputs:
                if port.name in b.inline:
                    for t in port.targets:
                        target = by_id.get(remap.get(t.block))  # type: ignore[arg-type]
                        if target is not None:
                            by_id[target.uuid] = target.model_copy(
                                update={"inline": {**target.inline, t.port: b.inline[port.name]}}
                            )
            inner_blocks = [by_id[ib.uuid] for ib in inner_blocks]
            inner_wires = [
                w.model_copy(
                    update={
                        "uuid": uuid.uuid5(b.uuid, str(w.uuid)),
                        "from_": PortRef(block=remap[w.from_.block], port=w.from_.port),
                        "to": PortRef(block=remap[w.to.block], port=w.to.port),
                    }
                )
                for w in comp.wires
                if w.from_.block in remap and w.to.block in remap
            ]
            here = f"{prefix}/{original.get(b.uuid, b.uuid)}" if prefix else str(b.uuid)
            inverse = {v: k for k, v in remap.items()}
            fb, fw, n_in, n_out = expand(inner_blocks, inner_wires, here, top, (*stack, b.spec), inverse)
            out_blocks += fb
            flat.wires += fw
            for port in comp.inputs:
                targets: list[PortRef] = []
                for t in port.targets:
                    if t.block not in remap:
                        continue
                    mapped = PortRef(block=remap[t.block], port=t.port)
                    targets += n_in.get((mapped.block, mapped.port), [mapped])
                inputs[(b.uuid, port.name)] = targets
            for port in comp.outputs:
                if port.source.block not in remap:
                    flat.errors.append(
                        (
                            top,
                            f"Output {port.name} of subsystem {comp.title} has no source inside. Open it and regroup.",
                        )
                    )
                    continue
                mapped = PortRef(block=remap[port.source.block], port=port.source.port)
                outputs[(b.uuid, port.name)] = n_out.get((mapped.block, mapped.port), mapped)
            if owner is None:
                flat.titles[b.uuid] = comp.title
                flat.instance_outputs[b.uuid] = {
                    port.name: outputs[(b.uuid, port.name)]
                    for port in comp.outputs
                    if (b.uuid, port.name) in outputs
                }

        out_wires: list[Wire] = []
        for w in wires:
            src = outputs.get((w.from_.block, w.from_.port), w.from_)
            if (w.from_.block, w.from_.port) not in outputs and w.from_.block in {
                b.uuid for b in blocks if b.spec in composites
            }:
                continue  # an output that failed to resolve; its error is already recorded
            targets = inputs.get((w.to.block, w.to.port))
            if targets is None:
                out_wires.append(w.model_copy(update={"from_": src}))
                continue
            for t in targets:
                out_wires.append(Wire(uuid=uuid.uuid5(w.uuid, f"{t.block}:{t.port}"), from_=src, to=t))
        return out_blocks, out_wires, inputs, outputs

    blocks, wires, _, _ = expand(model.blocks, model.wires, None, None, (), {})
    flat.blocks = blocks
    flat.wires = wires + flat.wires
    return flat
