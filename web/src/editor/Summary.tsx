import { useState } from "react";
import { api } from "../api/client";
import type { EvaluateResponse, Model, PortResult, ReportLine } from "../api/types.gen";
import { saveBlob } from "../lib/download";
import { formatForSummary } from "../lib/format";
import { Callout } from "../shell/dt";
import { CommitField, SelectField } from "./fields";
import { moveReport, removeReport, renameReport } from "./graph";
import { parseType } from "./patterns";
import { BASE, useEditor } from "./store";

interface Line {
  index: number;
  line: ReportLine;
  result?: PortResult;
  error?: string;
}

function Table({ caption, columns, lines }: { caption: string; columns: string[]; lines: Line[] }) {
  if (!lines.length) return null;
  return (
    <div className="bm-table-scroll" role="region" aria-label={caption} tabIndex={0}>
      <table className="dt-table bm-summary-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="bm-sticky">
              Line
            </th>
            <th scope="col">Unit</th>
            {columns.map((c) => (
              <th scope="col" key={c} className="dt-num">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map(({ index, line, result, error }) => {
            const kind = result ? parseType(result.type).kind : "float";
            const values = result?.value == null ? [] : Array.isArray(result.value) ? result.value : [result.value];
            return (
              <tr key={`${line.block}:${line.port}`} data-testid={`summary-row-${index}`}>
                <th scope="row" className="bm-sticky">
                  {line.label}
                </th>
                <td>{result?.unit ?? ""}</td>
                {error || !values.length ? (
                  <td colSpan={columns.length} className={error ? "bm-status--danger" : "bm-status"}>
                    {error ?? "Computing"}
                  </td>
                ) : (
                  values.map((v, i) => (
                    <td key={columns[i] ?? i} className="dt-num">
                      {formatForSummary(v, kind, result?.unit, line.format)}
                    </td>
                  ))
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowEditor({ model }: { model: Model }) {
  const apply = useEditor((s) => s.apply);
  const report = model.report ?? [];
  return (
    <details className="bm-details">
      <summary>Edit summary rows ({report.length})</summary>
      <ol className="bm-list">
        {report.map((line, i) => (
          <li key={`${line.block}:${line.port}`} className="bm-list__item bm-row--end">
            <CommitField
              label={`Row ${i + 1} label`}
              value={line.label}
              onCommit={(t) => {
                if (!t.trim()) return "Enter a label for the row.";
                apply((m) => renameReport(m, i, t.trim()));
              }}
            />
            <div className="bm-row bm-row--tight">
              <button type="button" className="dt-btn" disabled={i === 0} onClick={() => apply((m) => moveReport(m, i, -1))}>
                Move up
              </button>
              <button type="button" className="dt-btn" disabled={i === report.length - 1} onClick={() => apply((m) => moveReport(m, i, 1))}>
                Move down
              </button>
              <button type="button" className="dt-btn dt-btn--danger" onClick={() => apply((m) => removeReport(m, line.block, line.port))}>
                Remove row
              </button>
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Comparison({ lines, current, other, otherResult }: { lines: Line[]; current: string; other: string; otherResult?: EvaluateResponse }) {
  const periods = otherResult?.timeline.period_labels ?? [];
  const last = periods[periods.length - 1];
  const rows = lines.flatMap(({ line, result }) => {
    if (!result || result.value == null) return [];
    const kind = parseType(result.type).kind;
    const shape = parseType(result.type).shape;
    const pick = (v: PortResult["value"]) => (Array.isArray(v) ? v[v.length - 1] : v);
    const a = pick(result.value);
    const b = pick(otherResult?.outputs[line.block]?.[line.port]?.value ?? null);
    if (typeof a !== "number" || typeof b !== "number") return [];
    const label = shape === "scalar" ? line.label : `${line.label}, ${shape === "annual" ? "last year" : last}`;
    return [{ label, a, b, kind, unit: result.unit, format: line.format }];
  });
  if (!rows.length) return <p className="bm-status">Computing the comparison.</p>;
  return (
    <div className="bm-table-scroll" role="region" aria-label="Scenario comparison" tabIndex={0}>
      <table className="dt-table bm-summary-table">
        <caption>Comparison: single values and the last period</caption>
        <thead>
          <tr>
            <th scope="col" className="bm-sticky">
              Line
            </th>
            <th scope="col" className="dt-num">
              {current}
            </th>
            <th scope="col" className="dt-num">
              {other}
            </th>
            <th scope="col" className="dt-num">
              Difference
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row" className="bm-sticky">
                {r.label}
              </th>
              <td className="dt-num">{formatForSummary(r.a, r.kind, r.unit, r.format)}</td>
              <td className="dt-num">{formatForSummary(r.b, r.kind, r.unit, r.format)}</td>
              <td className="dt-num">{formatForSummary(r.a - r.b, r.kind, r.unit, r.format)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Summary({ readOnly }: { readOnly: boolean }) {
  const { model, result, scenario, compareScenario, compareResult } = useEditor();
  const setCompare = useEditor((s) => s.setCompare);
  const say = useEditor((s) => s.say);
  const [exporting, setExporting] = useState<string>();
  if (!model) return null;
  const report = model.report ?? [];
  const errors = new Map((result?.errors ?? []).map((e) => [e.block, e.message]));
  const lines: Line[] = report.map((line, index) => ({
    index,
    line,
    result: result?.outputs[line.block]?.[line.port],
    error: errors.get(line.block) ?? undefined,
  }));
  const shape = (l: Line) => (l.result ? parseType(l.result.type).shape : "series");
  const sample = model.blocks.some(
    (b) => (b.spec === "source.constant@1" || b.spec === "source.series@1") && (b.settings?.source ?? "illustrative") === "illustrative",
  );

  async function download(format: "csv" | "xlsx") {
    if (!model) return;
    setExporting(format);
    try {
      const { blob, filename } = await api.exportFile(model, format, scenario);
      saveBlob(blob, filename);
      say(`Exported ${filename}.`);
    } catch (e) {
      say(`Couldn't export: ${e instanceof Error ? e.message : String(e)}`, "danger");
    } finally {
      setExporting(undefined);
    }
  }

  return (
    <section className="bm-stack bm-summary" aria-label="Summary">
      <div className="bm-row bm-row--tight">
        <button type="button" className="dt-btn" onClick={() => download("csv")} disabled={!report.length || !!exporting}>
          Export CSV
        </button>
        <button type="button" className="dt-btn" onClick={() => download("xlsx")} disabled={!report.length || !!exporting}>
          Export XLSX
        </button>
        {exporting && <span className="bm-status">Preparing {exporting.toUpperCase()}</span>}
        {sample && <Callout label="Sample data" note="Illustrative figures, not real data." side="left" />}
      </div>
      {(model.scenarios?.length ?? 0) > 0 && (
        <div className="bm-row bm-row--tight bm-row--end">
          <p className="bm-status">Showing {scenarioName(model, scenario)}.</p>
          <SelectField
            label="Compare with"
            value={compareScenario ?? ""}
            options={[
              { value: "", label: "No comparison" },
              ...(scenario ? [{ value: BASE, label: "Base case" }] : []),
              ...(model.scenarios ?? []).filter((sc) => sc.id !== scenario).map((sc) => ({ value: sc.id, label: sc.name })),
            ]}
            onChange={(v) => setCompare(v || undefined)}
          />
        </div>
      )}
      {compareScenario !== undefined && report.length > 0 && (
        <Comparison
          lines={lines}
          current={scenarioName(model, scenario)}
          other={scenarioName(model, compareScenario === BASE ? undefined : compareScenario)}
          otherResult={compareResult}
        />
      )}
      {!report.length ? (
        <p className="bm-status">
          The summary is empty. {readOnly ? "Open the model on a desktop to add rows." : "Select a block and choose Add to summary on an output."}
        </p>
      ) : (
        <>
          <Table caption="Per period" columns={result?.timeline.period_labels ?? []} lines={lines.filter((l) => shape(l) === "series")} />
          <Table caption="Per fiscal year" columns={(result?.timeline.years ?? []).map((y) => `FY${y}`)} lines={lines.filter((l) => shape(l) === "annual")} />
          <Table caption="Single values" columns={["Value"]} lines={lines.filter((l) => shape(l) === "scalar")} />
          {!readOnly && <RowEditor model={model} />}
        </>
      )}
    </section>
  );
}

function scenarioName(model: Model, id: string | undefined): string {
  return id ? (model.scenarios?.find((s) => s.id === id)?.name ?? id) : "Base case";
}
