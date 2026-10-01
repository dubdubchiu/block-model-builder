"""The reference model's numpy evaluator (Chat's generator/dsl.py), loaded as a test oracle."""

import importlib.util
import sys
from pathlib import Path

GENERATOR = Path(__file__).resolve().parents[2] / "models" / "reference" / "saas_company" / "generator"


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, GENERATOR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dsl = _load("dsl")
reference_spec = _load("spec")
SPEC_PATH = GENERATOR / "spec.py"
