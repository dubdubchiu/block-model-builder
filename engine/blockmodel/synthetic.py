"""Synthetic models for load and latency checks.

A layered DAG: a first layer of Series inputs, then layers of Add and Multiply
blocks with fan-in 2. Add takes both inputs from the previous layer; Multiply
takes one from the previous layer and scales it by a first-layer series near 1,
so values stay finite (at most about 2^layers). Seeded, so the same arguments give the
same model. The summary lists the last layer's blocks (the graph's end points), so the model
exports like a real one.
"""

import random
import uuid
from datetime import date

from .model import BlockInstance, Model, PortRef, Position, ReportLine, Timeline, Wire

LAYER_WIDTH = 10


def synthetic_model(blocks: int = 250, periods: int = 120, seed: int = 0) -> Model:
    if blocks < LAYER_WIDTH + 1:
        raise ValueError(f"blocks must be at least {LAYER_WIDTH + 1}")
    rng = random.Random(seed)
    ns = uuid.UUID(int=seed)

    def uid(kind: str, i: int) -> uuid.UUID:
        return uuid.uuid5(ns, f"{kind}-{i}")

    instances: list[BlockInstance] = []
    wires: list[Wire] = []
    constants: list[uuid.UUID] = []
    previous: list[uuid.UUID] = []
    layer: list[uuid.UUID] = []
    for i in range(blocks):
        column, row = divmod(i, LAYER_WIDTH)
        if row == 0 and i:
            previous, layer = layer, []
        u = uid("block", i)
        position = Position(x=column * 240.0, y=row * 120.0)
        if column == 0:
            instances.append(
                BlockInstance(
                    uuid=u,
                    spec="source.series@1",
                    settings={"values": [rng.uniform(0.9, 1.1) for _ in range(periods)]},
                    position=position,
                )
            )
            constants.append(u)
        else:
            spec = "math.add@1" if i % 2 else "math.multiply@1"
            instances.append(BlockInstance(uuid=u, spec=spec, position=position))
            prev_port = "value" if column == 1 else "result"
            if spec == "math.add@1":
                src_a, src_b = rng.sample(previous, 2)
                sources = (("a", src_a, prev_port), ("b", src_b, prev_port))
            else:
                sources = (("a", rng.choice(previous), prev_port), ("b", rng.choice(constants), "value"))
            for port, src, src_port in sources:
                wires.append(
                    Wire(
                        uuid=uid(f"wire-{port}", i),
                        from_=PortRef(block=src, port=src_port),
                        to=PortRef(block=u, port=port),
                    )
                )
        layer.append(u)

    return Model(
        schema_version=1,
        id=uid("model", blocks * 1000 + periods),
        name=f"Synthetic {blocks} blocks by {periods} periods",
        timeline=Timeline(start=date(2027, 1, 1), frequency="month", periods=periods),
        blocks=instances,
        wires=wires,
        report=[
            ReportLine(block=u, port="result", label=f"End block {n}") for n, u in enumerate(layer, start=1)
        ],
    )
