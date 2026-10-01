"""The model file and API payloads as pydantic models.

These classes are the single source of truth for `schemas/` and, through it, the
TypeScript types in `web/src/api/types.gen.ts`. Regenerate both after a change:
`uv run python -m blockmodel.schema` then `npm run gen:types` in `web/`.
"""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SPEC_REF_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*@[0-9]+$"

InlineValue = float | int | bool | str


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Timeline(_Strict):
    start: date = Field(description="First day of period 1; must be the first day of a month.")
    frequency: Literal["month", "quarter", "year"]
    periods: int = Field(ge=1, le=600)
    fiscal_year_end: str = Field(default="12-31", pattern=r"^[0-1][0-9]-[0-3][0-9]$")

    @field_validator("start")
    @classmethod
    def _first_of_month(cls, v: date) -> date:
        if v.day != 1:
            raise ValueError("start must be the first day of a month, e.g. 2027-01-01")
        return v

    @field_validator("fiscal_year_end")
    @classmethod
    def _real_day(cls, v: str) -> str:
        month, day = (int(x) for x in v.split("-"))
        date(2001, month, day)  # raises for 02-30 and the like; 2001 is not a leap year
        return v


class Position(_Strict):
    x: float
    y: float


class BlockInstance(_Strict):
    uuid: UUID
    spec: str = Field(pattern=SPEC_REF_PATTERN, description="Block type as id@version, e.g. math.add@1.")
    label: str | None = None
    inline: dict[str, InlineValue] = Field(
        default_factory=dict, description="Values for unwired input ports, keyed by port name."
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Values that are never wired, e.g. a Constant's value."
    )
    position: Position


class PortRef(_Strict):
    block: UUID
    port: str


class Wire(_Strict):
    uuid: UUID
    from_: PortRef = Field(alias="from")
    to: PortRef


class ReportLine(_Strict):
    block: UUID
    port: str
    label: str
    format: str | None = None


class Override(_Strict):
    block: UUID
    inline: dict[str, InlineValue] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class Scenario(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str
    overrides: list[Override] = Field(
        default_factory=list,
        description="Changes to top-level blocks' inline values and settings in this scenario.",
    )


class CompositeInput(_Strict):
    name: str
    type: str = Field(default="any", description="Port pattern shown on the subsystem block.")
    targets: list[PortRef] = Field(description="Inner block inputs this port feeds.")


class CompositeOutput(_Strict):
    name: str
    source: PortRef = Field(description="The inner block output this port exposes.")


class CompositeSpec(_Strict):
    """A subsystem: a reusable group of blocks with its own ports, like a LabVIEW subVI."""

    id: str = Field(pattern=r"^user\.[a-z0-9_]+$")
    version: int = Field(default=1, ge=1)
    title: str
    doc: str = ""
    inputs: list[CompositeInput] = Field(default_factory=list)
    outputs: list[CompositeOutput]
    blocks: list["BlockInstance"]
    wires: list["Wire"]


class Model(_Strict):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    id: UUID
    name: str
    timeline: Timeline
    blocks: list[BlockInstance]
    wires: list[Wire]
    report: list[ReportLine] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    composites: list[CompositeSpec] = Field(default_factory=list)


class BlockError(_Strict):
    block: UUID | None = Field(description="The block at fault, or null for a model-level error.")
    message: str = Field(description="What happened and how to fix it.")
    path: str | None = Field(
        default=None, description="Inside a subsystem: the inner block's key, instance/inner."
    )


class Timing(_Strict):
    evaluate_ms: float


Scalar = float | int | bool | str
OutputValue = Scalar | list[float] | list[int] | list[bool] | list[str]


class PortResult(_Strict):
    type: str = Field(description="Inferred type, e.g. series<currency>.")
    unit: str | None = None
    value: OutputValue | None = Field(
        default=None,
        description="A scalar or one value per period (or year); null when not computed or not requested.",
    )


class TimelineInfo(_Strict):
    period_labels: list[str]
    years: list[int] = Field(description="Fiscal years, the columns of annual values.")


class EvaluateResponse(_Strict):
    engine: str = Field(description="Engine name and version.")
    timeline: TimelineInfo
    outputs: dict[str, dict[str, PortResult]] = Field(
        description="Block uuid (or instance/inner for blocks inside a subsystem), then output port name, then its type and value."
    )
    errors: list[BlockError]
    warnings: list[BlockError] = Field(
        default_factory=list, description="Things to check, such as mismatched units."
    )
    scenario: str | None = None
    timing: Timing
