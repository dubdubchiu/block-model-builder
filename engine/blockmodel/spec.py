"""Block specs: the reusable definition of a block type, one JSON file per type.

Specs live in `blockmodel/library/specs/`. Each names a registered `impl` key;
the implementation lives in `blockmodel/library/*.py`. A spec never holds code.
"""

from pydantic import Field

from .model import InlineValue, _Strict


class PortSpec(_Strict):
    name: str
    type: str = Field(description="Port pattern, e.g. number, scalar<integer>, series<date>.")
    required: bool = True
    inline: InlineValue | None = Field(
        default=None, description="Default inline value when the port is unwired."
    )
    doc: str | None = None


class SettingSpec(_Strict):
    name: str
    type: str
    default: InlineValue | list[InlineValue] | None = None
    options: list[str] | None = Field(
        default=None, description="Allowed values, when the setting is a choice."
    )
    doc: str | None = None


class BlockSpec(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    version: int = Field(ge=1)
    title: str
    category: str
    doc: str
    inputs: list[PortSpec] = Field(default_factory=list)
    settings: list[SettingSpec] = Field(default_factory=list)
    outputs: list[PortSpec]
    impl: str = Field(description="Registered function key. Never code.")
    causal: bool = Field(
        default=True,
        description="False when a period's output depends on later periods (Total, NPV); such blocks can't sit inside a feedback loop.",
    )

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class LibraryResponse(_Strict):
    engine: str
    kind_groups: dict[str, list[str]] = Field(
        description="Kinds each pattern word accepts, e.g. number and integer."
    )
    specs: list[BlockSpec]
