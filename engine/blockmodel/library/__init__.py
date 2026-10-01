"""The built-in block library: JSON specs in `specs/`, implementations registered by `impl` key."""

import json
from functools import cache
from pathlib import Path

from ..spec import BlockSpec
from ..types import parse_pattern
from . import finance, logic, lookup, math, series, sources  # noqa: F401  (registers the implementations)
from .registry import REGISTRY, BlockImpl

SPECS_DIR = Path(__file__).parent / "specs"


@cache
def load_library() -> tuple[BlockSpec, ...]:
    specs = []
    for path in sorted(SPECS_DIR.glob("*.json")):
        spec = BlockSpec.model_validate(json.loads(path.read_text()))
        if path.stem != spec.id:
            raise ValueError(f"{path.name} holds spec {spec.id}; rename the file to {spec.id}.json")
        if spec.impl not in REGISTRY:
            raise ValueError(f"spec {spec.ref} names impl {spec.impl}, which is not registered")
        for port in (*spec.inputs, *spec.outputs):
            parse_pattern(port.type)
        specs.append(spec)
    missing = set(REGISTRY) - {s.impl for s in specs}
    if missing:
        raise ValueError(f"registered impls without a spec: {sorted(missing)}")
    return tuple(specs)


@cache
def specs_by_ref() -> dict[str, BlockSpec]:
    return {s.ref: s for s in load_library()}


def impl_for(spec: BlockSpec) -> BlockImpl:
    return REGISTRY[spec.impl]
