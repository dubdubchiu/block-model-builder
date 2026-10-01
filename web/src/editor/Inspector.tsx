import type { BlockInstance, BlockSpec, Model, PortResult, PortSpec, SettingSpec } from "../api/types.gen";
import { formatValue } from "../lib/format";
import { CommitField, SelectField, parseNumber } from "./fields";
import { api } from "../api/client";
import {
  addReport,
  compositeRef,
  deleteScenario,
  disconnect,
  groupIntoComposite,
  inReport,
  removeReport,
  renameScenario,
  scenarioOverride,
  setInline,
  setLabel,
  setOverride,
  setSetting,
  sourceType,
  ungroup,
  wouldCycle,
} from "./graph";
import { refuseReason } from "./patterns";
import { type View, connectContext, useEditor, useView } from "./store";

const RETYPE_KINDS = ["float", "int", "count", "quantity", "percent"];
const NUMERIC = ["int", "float", "count", "quantity", "percent", "currency"];

export function Inspector({ readOnly = false }: { readOnly?: boolean }) {
  const view = useView();
  const selection = useEditor((s) => s.selection);
  const top = useEditor((s) => s.model);
  if (!view || !top) return null;
  const block = selection.length === 1 ? view.model.blocks.find((b) => b.uuid === selection[0]) : undefined;
  return (
    <section className="dt-panel bm-inspector" aria-label="Inspector">
      {block ? (
        <BlockInspector block={block} spec={view.specs[block.spec]} readOnly={readOnly} view={view} />
      ) : selection.length > 1 && !readOnly ? (
        <MultiInspector ids={selection} view={view} />
      ) : view.inside ? (
        <SubsystemPanel view={view} />
      ) : (
        <ModelInspector model={top} readOnly={readOnly} />
      )}
    </section>
  );
}

function MultiInspector({ ids, view }: { ids: string[]; view: View }) {
  const { deleteSelection, copySelection, apply, select, say } = useEditor.getState();
  return (
    <>
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">{ids.length} blocks selected</h2>
      </div>
      <div className="dt-panel__body bm-row">
        <button
          type="button"
          className="dt-btn"
          onClick={() => {
            let made = "";
            apply((m) => {
              const out = groupIntoComposite(m, ids, view.specs);
              made = out.instance;
              return out.model;
            });
            if (made) {
              select([made]);
              say("Grouped into a subsystem. Double-click it, or choose Open subsystem, to edit inside.");
            }
          }}
        >
          Group into subsystem
        </button>
        <button type="button" className="dt-btn" onClick={copySelection}>
          Copy blocks
        </button>
        <button type="button" className="dt-btn dt-btn--danger" onClick={deleteSelection}>
          Delete blocks
        </button>
      </div>
    </>
  );
}

function SubsystemPanel({ view }: { view: View }) {
  const { applyTop, leave } = useEditor.getState();
  const model = useEditor((s) => s.model);
  const composite = model?.composites?.find((c) => c.id === view.inside?.compositeId);
  if (!composite) return null;
  return (
    <>
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">Subsystem</h2>
        <span className="dt-panel__meta">{composite.blocks.length} blocks</span>
      </div>
      <div className="dt-panel__body bm-stack">
        <CommitField
          label="Subsystem title"
          value={composite.title}
          onCommit={(t) => {
            if (!t.trim()) return "Enter a title.";
            applyTop((m) => ({
              ...m,
              composites: (m.composites ?? []).map((c) => (c.id === composite.id ? { ...c, title: t.trim() } : c)),
            }));
          }}
        />
        <p className="bm-small">
          Inputs: {(composite.inputs ?? []).map((i) => i.name).join(", ") || "none"}. Outputs: {composite.outputs.map((o) => o.name).join(", ")}.
          To change the ports, go back to the model, ungroup, and group again.
        </p>
        <p className="bm-small">Values shown are for the instance you opened. Edits change every instance of this subsystem.</p>
        <div>
          <button type="button" className="dt-btn" onClick={leave}>
            Back to model
          </button>
        </div>
      </div>
    </>
  );
}

function ModelInspector({ model, readOnly }: { model: Model; readOnly: boolean }) {
  const apply = useEditor((s) => s.apply);
  const tl = model.timeline;
  const setTimeline = (change: Partial<Model["timeline"]>) => apply((m) => ({ ...m, timeline: { ...m.timeline, ...change } }));
  return (
    <>
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">Model</h2>
        <span className="dt-panel__meta">{model.blocks.length} blocks</span>
      </div>
      <div className="dt-panel__body bm-stack">
        {readOnly ? (
          <p className="dt-prose">
            {model.name}: {tl.periods} periods, {tl.frequency}ly from {tl.start}.
          </p>
        ) : (
          <>
            <p className="bm-status">Select a block to see and edit its inputs, settings and values.</p>
            <CommitField
              label="Model name"
              value={model.name}
              onCommit={(t) => {
                if (!t.trim()) return "Enter a name for the model.";
                apply((m) => ({ ...m, name: t.trim() }));
              }}
            />
            <CommitField
              label="First period"
              type="month"
              value={tl.start.slice(0, 7)}
              help="Periods start on the first day of this month."
              onCommit={(t) => {
                if (!/^\d{4}-\d{2}$/.test(t)) return "Pick a month, e.g. 2027-01.";
                setTimeline({ start: `${t}-01` });
              }}
            />
            <SelectField
              label="Period length"
              value={tl.frequency}
              options={[
                { value: "month", label: "Month" },
                { value: "quarter", label: "Quarter" },
                { value: "year", label: "Year" },
              ]}
              onChange={(v) => setTimeline({ frequency: v as Model["timeline"]["frequency"] })}
            />
            <CommitField
              label="Number of periods"
              value={String(tl.periods)}
              help="Series inputs need one value per period."
              onCommit={(t) => {
                const n = parseNumber(t);
                if (!n || !Number.isInteger(n) || n < 1 || n > 600) return "Enter a whole number from 1 to 600.";
                setTimeline({ periods: n });
              }}
            />
            <ScenarioList model={model} />
            <CommitField
              label="Fiscal year end"
              value={tl.fiscal_year_end ?? "12-31"}
              help="Month and day, e.g. 12-31 or 06-30."
              onCommit={(t) => {
                if (!/^\d{2}-\d{2}$/.test(t)) return "Use month and day, e.g. 06-30.";
                setTimeline({ fiscal_year_end: t });
              }}
            />
          </>
        )}
      </div>
    </>
  );
}

function ScenarioList({ model }: { model: Model }) {
  const { applyTop: apply, setScenario } = useEditor.getState();
  const active = useEditor((s) => s.scenario);
  const scenarios = model.scenarios ?? [];
  return (
    <fieldset className="bm-fieldset">
      <legend className="bm-legend">Scenarios</legend>
      {!scenarios.length && <p className="bm-small">No scenarios yet. Choose New scenario in the toolbar to add one.</p>}
      {scenarios.map((sc) => (
        <div key={sc.id} className="bm-input-editor">
          <CommitField
            label={`Scenario name (${sc.overrides?.length ?? 0} ${sc.overrides?.length === 1 ? "block" : "blocks"} changed)`}
            value={sc.name}
            onCommit={(t) => {
              if (!t.trim()) return "Enter a name.";
              apply((m) => renameScenario(m, sc.id, t.trim()));
            }}
          />
          <div>
            <button
              type="button"
              className="dt-btn dt-btn--danger"
              onClick={() => {
                if (active === sc.id) setScenario(undefined);
                apply((m) => deleteScenario(m, sc.id));
              }}
            >
              Delete scenario
            </button>
          </div>
        </div>
      ))}
    </fieldset>
  );
}

function CompositeActions({ block }: { block: BlockInstance }) {
  const { apply, enter, say, select } = useEditor.getState();
  const model = useEditor((s) => s.model);
  const composite = model?.composites?.find((c) => compositeRef(c) === block.spec);
  if (!composite) return null;
  return (
    <div className="bm-row bm-row--tight">
      <button type="button" className="dt-btn" onClick={() => enter(block.uuid)}>
        Open subsystem
      </button>
      <button
        type="button"
        className="dt-btn"
        onClick={() => {
          let ids: string[] = [];
          apply((m) => {
            const out = ungroup(m, block.uuid);
            ids = out.ids;
            return out.model;
          });
          select(ids);
        }}
      >
        Ungroup
      </button>
      <button
        type="button"
        className="dt-btn"
        onClick={() => {
          const url = URL.createObjectURL(new Blob([JSON.stringify(composite, null, 1)], { type: "application/json" }));
          const a = document.createElement("a");
          a.href = url;
          a.download = `${composite.id}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }}
      >
        Export subsystem JSON
      </button>
      <button
        type="button"
        className="dt-btn"
        onClick={() =>
          api.saveBlock(composite).then(
            () => say(`Saved ${composite.title} to My blocks.`),
            (e) => say(`Couldn't save the subsystem: ${e instanceof Error ? e.message : String(e)}`, "danger"),
          )
        }
      >
        Save to My blocks
      </button>
    </div>
  );
}

function BlockInspector({ block, spec, readOnly, view }: { block: BlockInstance; spec?: BlockSpec; readOnly: boolean; view: View }) {
  const { apply, say, deleteSelection } = useEditor.getState();
  const scenario = useEditor((s) => s.scenario);
  const scenarioName = useEditor((s) => s.model?.scenarios?.find((x) => x.id === s.scenario)?.name);
  const result = view.result;
  const error = result?.errors.find((e) => e.block === block.uuid);
  const warnings = (result?.warnings ?? []).filter((w) => w.block === block.uuid);
  const title = block.label || spec?.title || block.spec;

  return (
    <>
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">{title}</h2>
        <span className="dt-panel__meta">{spec?.title}</span>
      </div>
      <div className="dt-panel__body bm-stack">
        {spec?.doc && <p className="dt-prose bm-small">{spec.doc}</p>}
        {error && (
          <div className="dt-notice dt-notice--danger" role="alert">
            <span className="dt-tag dt-tag--danger">Error</span>
            <p className="dt-notice__text">{error.message}</p>
          </div>
        )}
        {warnings.map((w) => (
          <div key={w.message} className="dt-notice dt-notice--caution">
            <span className="dt-tag dt-tag--caution">Check units</span>
            <p className="dt-notice__text">{w.message}</p>
          </div>
        ))}
        {scenario && !view.inside && !readOnly && (
          <p className="bm-small">
            Editing values in the scenario {scenarioName}. Changed values apply only to this scenario; wiring and labels apply to all.
          </p>
        )}
        {spec?.impl === "composite" && !readOnly && !view.inside && <CompositeActions block={block} />}
        {!readOnly && (
          <CommitField label="Label" value={block.label ?? ""} placeholder={spec?.title} onCommit={(t) => apply((m) => setLabel(m, block.uuid, t))} />
        )}
        <div className="bm-row bm-row--tight">
          <span className="bm-mono" title="Block UUID">
            {block.uuid}
          </span>
          <button
            type="button"
            className="dt-btn dt-btn--quiet"
            onClick={() => navigator.clipboard?.writeText(block.uuid).then(() => say("Copied the block's UUID."), () => say("Couldn't copy; select the UUID text and copy it instead.", "danger"))}
          >
            Copy UUID
          </button>
        </div>

        {spec && spec.inputs && spec.inputs.length > 0 && (
          <fieldset className="bm-fieldset">
            <legend className="bm-legend">Inputs</legend>
            {spec.inputs.map((port) => (
              <InputEditor key={port.name} block={block} port={port} readOnly={readOnly} view={view} />
            ))}
          </fieldset>
        )}

        {spec && !readOnly && (spec.settings?.length ?? 0) > 0 && (
          <fieldset className="bm-fieldset">
            <legend className="bm-legend">Settings</legend>
            {spec.settings!.map((s) => (
              <SettingEditor key={s.name} block={block} setting={s} scenario={view.inside ? undefined : scenario} />
            ))}
          </fieldset>
        )}

        {spec && !readOnly && spec.outputs.length === 1 && <RetypeEditor block={block} result={result?.outputs[block.uuid]?.[spec.outputs[0].name]} />}

        {spec && (
          <fieldset className="bm-fieldset">
            <legend className="bm-legend">Outputs</legend>
            {spec.outputs.map((port) => (
              <OutputView
                key={port.name}
                block={block}
                name={port.name}
                result={result?.outputs[block.uuid]?.[port.name]}
                readOnly={readOnly || !!view.inside}
              />
            ))}
          </fieldset>
        )}

        {!readOnly && (
          <div>
            <button type="button" className="dt-btn dt-btn--danger" onClick={deleteSelection}>
              Delete block
            </button>
          </div>
        )}
      </div>
    </>
  );
}

/** A block's label, or its type plus a short id when unlabelled, so menus can tell blocks apart. */
function blockName(b: BlockInstance, specs: Record<string, BlockSpec>): string {
  return b.label || `${specs[b.spec]?.title ?? b.spec} (${b.uuid.slice(0, 8)})`;
}

function InputEditor({ block, port, readOnly, view }: { block: BlockInstance; port: PortSpec; readOnly: boolean; view: View }) {
  const state = useEditor();
  const { library } = state;
  const model = view.model;
  const scenario = view.inside ? undefined : state.scenario;
  if (!library) return null;
  const wire = model.wires.find((w) => w.to.block === block.uuid && w.to.port === port.name);
  const ctx = connectContext(state);

  const options = [{ value: "", label: "Not wired (use a value)" }];
  for (const other of model.blocks) {
    if (other.uuid === block.uuid) continue;
    for (const out of view.specs[other.spec]?.outputs ?? []) {
      const key = `${other.uuid}:${out.name}`;
      const current = wire && wire.from.block === other.uuid && wire.from.port === out.name;
      const type = sourceType(model, ctx, other.uuid, out.name) ?? out.type;
      const ok =
        current ||
        (!refuseReason(port.name, port.type, type, library.kindGroups) && !wouldCycle(model, other.uuid, block.uuid, port.name));
      if (ok) {
        const outs = view.specs[other.spec]?.outputs.length ?? 1;
        options.push({ value: key, label: `${blockName(other, view.specs)}${outs > 1 ? `: ${out.name}` : ""}` });
      }
    }
  }
  const value = wire ? `${wire.from.block}:${wire.from.port}` : "";
  const override = scenario ? scenarioOverride(state.model!, scenario, block.uuid)?.inline?.[port.name] : undefined;
  const inline = override ?? block.inline?.[port.name];
  const shown = inline ?? port.inline;
  const setValue = (v: number | boolean | undefined) =>
    scenario
      ? state.apply((m) => setOverride(m, scenario, block.uuid, "inline", port.name, v))
      : state.apply((m) => setInline(m, block.uuid, port.name, v));
  const source = wire && model.blocks.find((b) => b.uuid === wire.from.block);

  if (readOnly) {
    return (
      <p className="bm-port-line">
        <span className="bm-port-line__name">{port.name}</span> <span className="bm-mono">{port.type}</span>{" "}
        {source ? `from ${blockName(source, view.specs)}` : shown != null ? `= ${formatValue(shown)}` : "not set"}
      </p>
    );
  }

  return (
    <div className="bm-input-editor">
      <p className="bm-port-line">
        <span className="bm-port-line__name">{port.name}</span> <span className="bm-mono">{port.type}</span>
        {port.doc && <span className="bm-small"> {port.doc}</span>}
      </p>
      <SelectField
        label={`Wire ${port.name} from`}
        value={value}
        options={options}
        onChange={(v) => {
          if (!v) {
            state.apply((m) => disconnect(m, block.uuid, port.name));
            return;
          }
          const [from, fromPort] = v.split(":");
          state.connect({ block: from, port: fromPort }, { block: block.uuid, port: port.name });
        }}
      />
      {!wire &&
        (port.type === "bool" ? (
          <SelectField
            label={`Value of ${port.name}`}
            value={shown == null ? "" : String(shown)}
            options={[
              { value: "", label: "Not set" },
              { value: "true", label: "TRUE" },
              { value: "false", label: "FALSE" },
            ]}
            onChange={(v) => setValue(v === "" ? undefined : v === "true")}
          />
        ) : (
          <div className="bm-row bm-row--tight bm-row--end">
            <CommitField
              label={`Value of ${port.name}`}
              value={inline != null ? String(inline) : ""}
              placeholder={port.inline != null ? `Default ${formatValue(port.inline)}` : "Required: enter a value"}
              mono
              onCommit={(t) => {
                if (!t.trim()) {
                  setValue(undefined);
                  return;
                }
                const n = parseNumber(t);
                if (n === undefined) return "Enter a number, e.g. 0.25 or 25%.";
                if (port.type.includes("integer") && !Number.isInteger(n)) return "Enter a whole number.";
                setValue(n);
              }}
            />
          </div>
        ))}
      {override !== undefined && <OverrideMark onClear={() => setValue(undefined)} />}
    </div>
  );
}

function kindOf(block: BlockInstance): string {
  return typeof block.settings?.kind === "string" ? block.settings.kind : "float";
}

const SCENARIO_SETTINGS = new Set(["value", "values", "keys"]);

function OverrideMark({ onClear }: { onClear: () => void }) {
  return (
    <div className="bm-row bm-row--tight">
      <span className="dt-tag dt-tag--caution">Overridden</span>
      <button type="button" className="dt-btn dt-btn--quiet" onClick={onClear}>
        Use base value
      </button>
    </div>
  );
}

function SettingEditor({ block, setting, scenario }: { block: BlockInstance; setting: SettingSpec; scenario?: string }) {
  const apply = useEditor((s) => s.apply);
  const model = useEditor((s) => s.model);
  const periods = model?.timeline.periods ?? 0;
  const scenarioField = scenario && SCENARIO_SETTINGS.has(setting.name) ? scenario : undefined;
  const override = scenarioField && model ? scenarioOverride(model, scenarioField, block.uuid)?.settings?.[setting.name] : undefined;
  const current = override ?? block.settings?.[setting.name];
  const set = (v: unknown) =>
    scenarioField
      ? apply((m) => setOverride(m, scenarioField, block.uuid, "settings", setting.name, v))
      : apply((m) => setSetting(m, block.uuid, setting.name, v));
  const label = setting.name === "op" ? "Operator" : setting.name[0].toUpperCase() + setting.name.slice(1);
  const mark = override !== undefined ? <OverrideMark onClear={() => set(undefined)} /> : null;

  if (setting.options) {
    return (
      <SelectField
        label={label}
        value={String(current ?? setting.default ?? "")}
        options={setting.options.map((o) => ({ value: o, label: o }))}
        onChange={set}
        help={setting.doc}
      />
    );
  }
  if (setting.name === "values" || setting.name === "keys") {
    const values = Array.isArray(current) ? (current as unknown[]) : [];
    const kind = setting.name === "keys" || block.spec === "lookup.table@1" ? "float" : kindOf(block);
    const lookup = block.spec === "lookup.table@1";
    return (
      <>
      <CommitField
        label={lookup ? (setting.name === "keys" ? "Keys, ascending" : "Values, one per key") : "Values, one per period"}
        multiline
        mono
        value={values.map((v) => (typeof v === "boolean" ? (v ? "TRUE" : "FALSE") : String(v))).join(", ")}
        help={
          lookup
            ? `${values.length} ${setting.name}. Separate them with commas or spaces.`
            : `${values.length} of ${periods} periods. Separate values with commas or spaces.`
        }
        onCommit={(t) => {
          const tokens = t.split(/[\s,;]+/).filter(Boolean);
          const parsed: (number | boolean)[] = [];
          for (const [i, tok] of tokens.entries()) {
            if (kind === "bool") {
              if (!/^(true|false)$/i.test(tok)) return `Value ${i + 1} must be TRUE or FALSE.`;
              parsed.push(/^true$/i.test(tok));
            } else {
              const n = Number(tok);
              if (!Number.isFinite(n)) return `Value ${i + 1} (${tok}) isn't a number.`;
              parsed.push(n);
            }
          }
          set(parsed);
        }}
      />
      {mark}
      </>
    );
  }
  if (setting.name === "value") {
    const kind = kindOf(block);
    if (kind === "bool") {
      return (
        <SelectField
          label="Value"
          value={String(current === true)}
          options={[
            { value: "true", label: "TRUE" },
            { value: "false", label: "FALSE" },
          ]}
          onChange={(v) => set(v === "true")}
        />
      );
    }
    return (
      <>
      <CommitField
        label="Value"
        mono
        value={current == null ? "" : String(current)}
        help={NUMERIC.includes(kind) ? "A number; 25% is read as 0.25." : kind === "date" ? "A date like 2027-01-01." : undefined}
        onCommit={(t) => {
          if (NUMERIC.includes(kind)) {
            const n = parseNumber(t);
            if (n === undefined) return "Enter a number, e.g. 1250000 or 12.5%.";
            if ((kind === "int" || kind === "count") && !Number.isInteger(n)) return "This kind needs a whole number.";
            set(n);
          } else set(t);
        }}
      />
      {mark}
      </>
    );
  }
  return (
    <CommitField
      label={label}
      value={current == null ? "" : String(current)}
      help={setting.doc}
      multiline={setting.name === "notes"}
      onCommit={(t) => set(t.trim() || undefined)}
    />
  );
}

function RetypeEditor({ block, result }: { block: BlockInstance; result?: PortResult }) {
  const apply = useEditor((s) => s.apply);
  const kind = typeof block.settings?.display_kind === "string" ? block.settings.display_kind : "";
  const unit = typeof block.settings?.display_unit === "string" ? block.settings.display_unit : "";
  return (
    <fieldset className="bm-fieldset">
      <legend className="bm-legend">Retype output</legend>
      <SelectField
        label="Show output as"
        value={kind}
        options={[{ value: "", label: `As inferred${result ? ` (${result.type})` : ""}` }, ...RETYPE_KINDS.map((k) => ({ value: k, label: k }))]}
        onChange={(v) => apply((m) => setSetting(m, block.uuid, "display_kind", v || undefined))}
        help="Changes how the output is typed downstream. Currency can't be retyped."
      />
      <CommitField
        label="Unit label"
        value={unit}
        placeholder={result?.unit ?? "none"}
        onCommit={(t) => apply((m) => setSetting(m, block.uuid, "display_unit", t.trim() || undefined))}
      />
    </fieldset>
  );
}

function OutputView({ block, name, result, readOnly }: { block: BlockInstance; name: string; result?: PortResult; readOnly: boolean }) {
  const timeline = useEditor((s) => s.result?.timeline);
  const model = useEditor((s) => s.model);
  const apply = useEditor((s) => s.apply);
  const listed = model ? inReport(model, block.uuid, name) : false;
  const summaryButton = readOnly ? null : (
    <button
      type="button"
      className="dt-btn"
      onClick={() =>
        apply((m) => (listed ? removeReport(m, block.uuid, name) : addReport(m, block.uuid, name, block.label || name)))
      }
    >
      {listed ? "Remove from summary" : "Add to summary"}
    </button>
  );
  if (!result) return <p className="bm-status">Output {name}: not computed yet.</p>;
  const value = result.value;
  const labels = result.type.startsWith("annual<") ? timeline?.years.map((y) => `FY${y}`) : timeline?.period_labels;
  return (
    <div className="bm-output">
      <p className="bm-port-line">
        <span className="bm-port-line__name">{name}</span> <span className="bm-mono">{result.type}</span>
        {result.unit && <span className="bm-mono"> {result.unit}</span>}
      </p>
      <div>{summaryButton}</div>
      {value == null ? (
        <p className="bm-status">Values load when the block is on screen or selected.</p>
      ) : Array.isArray(value) ? (
        <div className="bm-table-scroll bm-table-scroll--short">
          <table className="dt-table">
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col" className="dt-num">
                  Value
                </th>
              </tr>
            </thead>
            <tbody>
              {value.map((v, i) => (
                <tr key={labels?.[i] ?? i}>
                  <td className="dt-code">{labels?.[i] ?? i + 1}</td>
                  <td className="dt-num">{formatValue(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="bm-mono">{formatValue(value)}</p>
      )}
    </div>
  );
}
