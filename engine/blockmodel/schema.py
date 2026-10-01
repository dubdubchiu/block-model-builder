"""Generate `schemas/api.schema.json` from the pydantic models.

uv run python -m blockmodel.schema          write the file
uv run python -m blockmodel.schema --check  exit 1 if the file is stale
"""

import json
import sys
from pathlib import Path

from pydantic.json_schema import models_json_schema

from .model import EvaluateResponse, Model
from .spec import LibraryResponse

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "api.schema.json"


def build_schema() -> dict:
    _, schema = models_json_schema(
        [(Model, "validation"), (EvaluateResponse, "serialization"), (LibraryResponse, "serialization")],
        by_alias=True,
        title="Block model builder API",
    )
    # Property titles only restate field names; json2ts would turn each into a type alias.
    for definition in schema["$defs"].values():
        for prop in definition.get("properties", {}).values():
            prop.pop("title", None)
    return schema


def render() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text() != text:
            print(f"{SCHEMA_PATH} is stale. Run: uv run python -m blockmodel.schema")
            return 1
        return 0
    SCHEMA_PATH.write_text(text)
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
