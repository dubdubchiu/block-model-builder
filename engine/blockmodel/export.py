"""The summary worksheet: report rows evaluated and laid out for CSV and XLSX export.

Rows fall into three tables by shape: per period, per fiscal year, and single values.
Values only; formulas stay in the model. A row whose block failed keeps its place and
carries the error in its note.
"""

import csv
import io
from dataclasses import dataclass, field

import xlsxwriter

from .evaluate import evaluate
from .library import specs_by_ref
from .model import EvaluateResponse, Model
from .types import parse_type

DEFAULT_FORMATS = {
    "currency": "#,##0",
    "percent": "0.0%",
    "count": "#,##0",
    "int": "#,##0",
    "quantity": "#,##0.0",
    "float": "#,##0.00",
}


class ExportError(Exception):
    """The model can't be exported as asked. The message says how to fix it."""


@dataclass
class Row:
    label: str
    type: str
    unit: str | None
    format: str
    values: list  # one per column; empty when the block failed
    note: str = ""


@dataclass
class Summary:
    model_name: str
    period_labels: list[str]
    years: list[int]
    per_period: list[Row] = field(default_factory=list)
    per_year: list[Row] = field(default_factory=list)
    single: list[Row] = field(default_factory=list)
    sample: bool = False


def _format(kind: str, unit: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    if kind == "currency":
        code = (unit or "USD").split("/")[0]
        return "$#,##0" if code == "USD" else f'#,##0 "{code}"'
    return DEFAULT_FORMATS.get(kind, "General")


INPUT_BLOCKS = ("source.constant@1", "source.series@1")


def is_sample(model: Model) -> bool:
    """True when any input is illustrative; an input without a source counts as illustrative."""
    return any(
        b.settings.get("source", "illustrative") == "illustrative"
        for b in model.blocks
        if b.spec in INPUT_BLOCKS
    )


def build_summary(model: Model, result: EvaluateResponse | None = None) -> Summary:
    if not model.report:
        raise ExportError(
            "The summary is empty. Select a block and choose Add to summary for each output you want to export."
        )
    result = result or evaluate(model)
    errors = {str(e.block): e.message for e in result.errors if e.block}
    summary = Summary(
        model_name=model.name,
        period_labels=result.timeline.period_labels,
        years=result.timeline.years,
        sample=is_sample(model),
    )
    for line in model.report:
        block = str(line.block)
        port = result.outputs.get(block, {}).get(line.port)
        if port is None:
            row = Row(line.label, "", None, "General", [], errors.get(block, "This output has no value."))
            summary.per_period.append(row)
            continue
        t = parse_type(port.type)
        row = Row(line.label, port.type, port.unit, _format(t.kind, port.unit, line.format), [])
        if port.value is None:
            row.note = errors.get(block, "No value was computed for this output.")
        else:
            row.values = port.value if isinstance(port.value, list) else [port.value]
        {"series": summary.per_period, "annual": summary.per_year, "scalar": summary.single}[t.shape].append(
            row
        )
    return summary


def to_csv(summary: Summary) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([summary.model_name])
    if summary.sample:
        w.writerow(["Sample data: illustrative figures, not real data."])
    sections = [
        ("Per period", summary.period_labels, summary.per_period),
        ("Per fiscal year", [f"FY{y}" for y in summary.years], summary.per_year),
        ("Single values", ["Value"], summary.single),
    ]
    for title, columns, rows in sections:
        if not rows:
            continue
        w.writerow([])
        w.writerow([title])
        w.writerow(["Line", "Unit", *columns, "Note"])
        for r in rows:
            values = r.values or [""] * len(columns)
            w.writerow([r.label, r.unit or "", *values, r.note])
    return out.getvalue()


def to_xlsx(summary: Summary, model: Model, result: EvaluateResponse) -> bytes:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True})
    bold = book.add_format({"bold": True})
    head = book.add_format({"bold": True, "bottom": 2})
    note = book.add_format({"italic": True})
    formats: dict[str, object] = {}

    def fmt(code: str):
        if code not in formats:
            formats[code] = book.add_format({"num_format": code})
        return formats[code]

    # Summary
    sheet = book.add_worksheet("Summary")
    sheet.write(0, 0, summary.model_name, bold)
    row = 1
    if summary.sample:
        sheet.write(row, 0, "Sample data: illustrative figures, not real data.", note)
        row += 1
    sections = [
        ("Per period", summary.period_labels, summary.per_period),
        ("Per fiscal year", [f"FY{y}" for y in summary.years], summary.per_year),
        ("Single values", ["Value"], summary.single),
    ]
    first_header = None
    for title, columns, rows in sections:
        if not rows:
            continue
        row += 1
        sheet.write(row, 0, title, bold)
        row += 1
        sheet.write_row(row, 0, ["Line", "Unit", *columns, "Note"], head)
        first_header = first_header if first_header is not None else row
        row += 1
        for r in rows:
            sheet.write(row, 0, r.label)
            sheet.write(row, 1, r.unit or "")
            for i, v in enumerate(r.values):
                if isinstance(v, bool) or isinstance(v, str):
                    sheet.write(row, 2 + i, v)
                else:
                    sheet.write_number(row, 2 + i, v, fmt(r.format))
            if r.note:
                sheet.write(row, 2 + len(columns), r.note, note)
            row += 1
    sheet.set_column(0, 0, 42)
    sheet.set_column(1, 1, 14)
    sheet.set_column(2, 2 + max(len(summary.period_labels), 1), 14)
    if first_header is not None:
        sheet.freeze_panes(first_header + 1, 2)

    # Assumptions: every Constant and Series input.
    specs = specs_by_ref()
    sheet = book.add_worksheet("Assumptions")
    sheet.write_row(
        0, 0, ["Label", "Block", "Kind", "Unit", "Source", "Notes", "Value", *summary.period_labels], head
    )
    r = 1
    for b in model.blocks:
        if b.spec not in INPUT_BLOCKS:
            continue
        kind = b.settings.get("kind", "float")
        unit = b.settings.get("unit")
        code = _format(kind, unit, None)
        sheet.write_row(
            r,
            0,
            [
                b.label or specs[b.spec].title,
                specs[b.spec].title,
                kind,
                unit or "",
                b.settings.get("source", ""),
                b.settings.get("notes") or "",
            ],
        )
        if b.spec == "source.constant@1":
            v = b.settings.get("value")
            if isinstance(v, int | float) and not isinstance(v, bool):
                sheet.write_number(r, 6, v, fmt(code))
            else:
                sheet.write(r, 6, v)
        else:
            for i, v in enumerate(b.settings.get("values", [])):
                if isinstance(v, int | float) and not isinstance(v, bool):
                    sheet.write_number(r, 7 + i, v, fmt(code))
                else:
                    sheet.write(r, 7 + i, v)
        r += 1
    sheet.set_column(0, 0, 42)
    sheet.set_column(4, 5, 30)
    sheet.freeze_panes(1, 1)

    # Blocks: identity, types and errors.
    sheet = book.add_worksheet("Blocks")
    sheet.write_row(0, 0, ["UUID", "Label", "Block", "Output", "Type", "Unit", "Error"], head)
    errors = {str(e.block): e.message for e in result.errors if e.block}
    r = 1
    for b in model.blocks:
        spec = specs.get(b.spec)
        ports = result.outputs.get(str(b.uuid), {})
        names = list(ports) or [""]
        for name in names:
            p = ports.get(name)
            sheet.write_row(
                r,
                0,
                [
                    str(b.uuid),
                    b.label or "",
                    spec.title if spec else b.spec,
                    name,
                    p.type if p else "",
                    (p.unit or "") if p else "",
                    errors.get(str(b.uuid), ""),
                ],
            )
            r += 1
    sheet.set_column(0, 0, 38)
    sheet.set_column(1, 1, 42)
    sheet.freeze_panes(1, 0)

    book.close()
    return buffer.getvalue()


def export(model: Model, fmt: str, scenario: str | None = None) -> tuple[bytes, str]:
    """Returns (content, media type) for format csv or xlsx, for the base case or a scenario."""
    result = evaluate(model, scenario=scenario)
    summary = build_summary(model, result)
    if scenario:
        name = next(s.name for s in model.scenarios if s.id == scenario)
        summary.model_name = f"{summary.model_name} (scenario: {name})"
    if fmt == "csv":
        return to_csv(summary).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "xlsx":
        return to_xlsx(
            summary, model, result
        ), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    raise ExportError(f"Export format {fmt!r} isn't supported. Use csv or xlsx.")
