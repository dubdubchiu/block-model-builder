"""The registry of block implementations, keyed by a spec's `impl`.

Each implementation has two parts:
- `infer(ctx) -> {output port: Type}` applies the type rules to the input types;
- `compute(ctx, inputs) -> {output port: value}` does the numpy work.

Both raise `BlockFailure` (or `TypeRuleError` from infer) with a message that
says what happened and how to fix it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..timeline import TimelineCalc
from ..types import Type

Value = float | bool | np.ndarray


class BlockFailure(Exception):
    """A block could not compute. The message is shown to the user as-is."""


@dataclass
class Ctx:
    timeline: TimelineCalc
    settings: dict[str, Any]
    types: dict[str, Type]  # present inputs only; unwired optional ports are absent
    literals: dict[str, Any] = field(
        default_factory=dict
    )  # inline values of unwired inputs, known at infer time
    out: dict[str, Type] = field(default_factory=dict)  # inferred output types, set before compute

    def length(self, shape: str) -> int:
        return self.timeline.length(shape)

    def per_period(self, value: Value, shape: str | None = None) -> np.ndarray:
        """Broadcast a scalar to the block's per-period (or per-year) length."""
        shape = shape or next((t.shape for t in self.types.values() if t.per_period), "series")
        if isinstance(value, np.ndarray):
            return value
        return np.full(self.length(shape), value, dtype=bool if isinstance(value, bool) else float)

    def no_annual(self, *ports: str) -> None:
        for p in ports:
            if p in self.types and self.types[p].shape == "annual":
                raise BlockFailure(
                    f"Input {p} is per-year, but this block works per period. Wire per-period values instead."
                )

    def whole(self, name: str, value: Value) -> int:
        """A scalar integer input, checked."""
        v = float(value)
        if not v.is_integer():
            raise BlockFailure(f"Input {name} needs a whole number; {v:g} isn't one.")
        return int(v)


Infer = Callable[[Ctx], dict[str, Type]]
Compute = Callable[[Ctx, dict[str, Value]], dict[str, Value]]


@dataclass(frozen=True)
class BlockImpl:
    infer: Infer
    compute: Compute


REGISTRY: dict[str, BlockImpl] = {}


def register(key: str, infer: Infer) -> Callable[[Compute], Compute]:
    def wrap(compute: Compute) -> Compute:
        if key in REGISTRY:
            raise ValueError(f"impl {key} registered twice")
        REGISTRY[key] = BlockImpl(infer=infer, compute=compute)
        return compute

    return wrap
