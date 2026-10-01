/**
 * Pure editing operations on a model. Each returns a new model (or a refusal reason) and never
 * mutates its input, so the store can keep snapshots for undo.
 */
import type { BlockInstance, BlockSpec, Model, Wire } from "../api/types.gen";
import { type KindGroups, refuseReason } from "./patterns";

export type Inline = number | boolean | string;

export function newId(): string {
  return crypto.randomUUID();
}

export function defaultSettings(spec: BlockSpec): Record<string, unknown> {
  const settings: Record<string, unknown> = {};
  for (const s of spec.settings ?? []) {
    if (s.default !== null && s.default !== undefined) settings[s.name] = structuredClone(s.default);
  }
  return settings;
}

export function addBlock(model: Model, spec: BlockSpec, position: { x: number; y: number }, id = newId()): Model {
  const block: BlockInstance = {
    uuid: id,
    spec: `${spec.id}@${spec.version}`,
    label: null,
    inline: {},
    settings: defaultSettings(spec),
    position: { x: Math.round(position.x), y: Math.round(position.y) },
  };
  return { ...model, blocks: [...model.blocks, block] };
}

export function moveBlocks(model: Model, positions: Record<string, { x: number; y: number }>): Model {
  return {
    ...model,
    blocks: model.blocks.map((b) =>
      positions[b.uuid] ? { ...b, position: { x: Math.round(positions[b.uuid].x), y: Math.round(positions[b.uuid].y) } } : b,
    ),
  };
}

export function updateBlock(model: Model, id: string, change: (b: BlockInstance) => BlockInstance): Model {
  return { ...model, blocks: model.blocks.map((b) => (b.uuid === id ? change(b) : b)) };
}

export function setLabel(model: Model, id: string, label: string): Model {
  return updateBlock(model, id, (b) => ({ ...b, label: label.trim() || null }));
}

export function setInline(model: Model, id: string, port: string, value: Inline | undefined): Model {
  return updateBlock(model, id, (b) => {
    const inline = { ...(b.inline ?? {}) };
    if (value === undefined) delete inline[port];
    else inline[port] = value;
    return { ...b, inline };
  });
}

export function setSetting(model: Model, id: string, key: string, value: unknown): Model {
  return updateBlock(model, id, (b) => {
    const settings = { ...(b.settings ?? {}) };
    if (value === undefined || value === null || value === "") delete settings[key];
    else settings[key] = value;
    return { ...b, settings };
  });
}

/** Removes blocks, every wire attached to them, report lines on them, and the given wires. */
export function deleteItems(model: Model, blockIds: string[], wireIds: string[] = []): Model {
  const blocks = new Set(blockIds);
  const wires = new Set(wireIds);
  return {
    ...model,
    blocks: model.blocks.filter((b) => !blocks.has(b.uuid)),
    wires: model.wires.filter((w) => !wires.has(w.uuid) && !blocks.has(w.from.block) && !blocks.has(w.to.block)),
    report: (model.report ?? []).filter((r) => !blocks.has(r.block)),
  };
}

export function disconnect(model: Model, block: string, port: string): Model {
  return { ...model, wires: model.wires.filter((w) => !(w.to.block === block && w.to.port === port)) };
}

export const FEEDBACK = "series.feedback@1";

function isFeedbackInput(model: Model, block: string, port: string): boolean {
  return port === "x" && model.blocks.some((b) => b.uuid === block && b.spec === FEEDBACK);
}

/**
 * Would a wire from `source` into `target` close a loop? True when target already feeds source.
 * A Feedback block's x input is where loops are allowed, so wires into it never count.
 */
export function wouldCycle(model: Model, source: string, target: string, targetPort?: string): boolean {
  if (targetPort && isFeedbackInput(model, target, targetPort)) return false;
  if (source === target) return true;
  const downstream = new Map<string, string[]>();
  for (const w of model.wires) {
    if (isFeedbackInput(model, w.to.block, w.to.port)) continue;
    downstream.set(w.from.block, [...(downstream.get(w.from.block) ?? []), w.to.block]);
  }
  const seen = new Set<string>();
  const stack = [target];
  while (stack.length) {
    const b = stack.pop()!;
    if (b === source) return true;
    if (seen.has(b)) continue;
    seen.add(b);
    stack.push(...(downstream.get(b) ?? []));
  }
  return false;
}

export interface ConnectContext {
  specs: Record<string, BlockSpec>;
  kindGroups: KindGroups;
  /** Inferred output types from the last evaluation: block uuid, then port, then type text. */
  types: Record<string, Record<string, string>>;
}

export function sourceType(model: Model, ctx: ConnectContext, block: string, port: string): string | undefined {
  const inferred = ctx.types[block]?.[port];
  if (inferred) return inferred;
  const b = model.blocks.find((x) => x.uuid === block);
  return b && ctx.specs[b.spec]?.outputs.find((p) => p.name === port)?.type;
}

/** A new wire, replacing any wire already into that input; or a reason it can't be made. */
export function connect(
  model: Model,
  ctx: ConnectContext,
  from: { block: string; port: string },
  to: { block: string; port: string },
): { model: Model } | { refused: string } {
  const target = model.blocks.find((b) => b.uuid === to.block);
  const spec = target && ctx.specs[target.spec];
  const port = spec?.inputs?.find((p) => p.name === to.port);
  if (!port) return { refused: `That block has no input named ${to.port}.` };
  if (wouldCycle(model, from.block, to.block, to.port)) {
    return {
      refused:
        "Can't connect: this wire would form a loop. Loops need a Feedback block (it passes the previous period's value); or carry a value forward with Lag or Accumulate.",
    };
  }
  const type = sourceType(model, ctx, from.block, from.port);
  if (type) {
    const reason = refuseReason(port.name, port.type, type, ctx.kindGroups);
    if (reason) return { refused: `Can't connect: ${reason}` };
  }
  const wire: Wire = { uuid: newId(), from: { ...from }, to: { ...to } };
  const kept = model.wires.filter((w) => !(w.to.block === to.block && w.to.port === to.port));
  return { model: { ...model, wires: [...kept, wire] } };
}

export interface Clip {
  blocks: BlockInstance[];
  wires: Wire[];
}

/** The selected blocks and the wires among them. */
export function copy(model: Model, blockIds: string[]): Clip {
  const ids = new Set(blockIds);
  return {
    blocks: structuredClone(model.blocks.filter((b) => ids.has(b.uuid))),
    wires: structuredClone(model.wires.filter((w) => ids.has(w.from.block) && ids.has(w.to.block))),
  };
}

/** Pastes with new ids, offset so the copy is visible; returns the new block ids for selection. */
export function paste(model: Model, clip: Clip, offset = 40): { model: Model; ids: string[] } {
  const remap = new Map(clip.blocks.map((b) => [b.uuid, newId()]));
  const blocks = clip.blocks.map((b) => ({
    ...structuredClone(b),
    uuid: remap.get(b.uuid)!,
    position: { x: b.position.x + offset, y: b.position.y + offset },
  }));
  const wires = clip.wires.map((w) => ({
    uuid: newId(),
    from: { block: remap.get(w.from.block)!, port: w.from.port },
    to: { block: remap.get(w.to.block)!, port: w.to.port },
  }));
  return { model: { ...model, blocks: [...model.blocks, ...blocks], wires: [...model.wires, ...wires] }, ids: [...remap.values()] };
}

export function blankModel(): Model {
  const nextYear = new Date().getFullYear() + 1;
  return {
    schemaVersion: 1,
    id: newId(),
    name: "Untitled model",
    timeline: { start: `${nextYear}-01-01`, frequency: "quarter", periods: 8, fiscal_year_end: "12-31" },
    blocks: [],
    wires: [],
    report: [],
  };
}

// ---------------------------------------------------------------- summary (report) rows

export function inReport(model: Model, block: string, port: string): boolean {
  return (model.report ?? []).some((r) => r.block === block && r.port === port);
}

export function addReport(model: Model, block: string, port: string, label: string): Model {
  if (inReport(model, block, port)) return model;
  return { ...model, report: [...(model.report ?? []), { block, port, label, format: null }] };
}

export function removeReport(model: Model, block: string, port: string): Model {
  return { ...model, report: (model.report ?? []).filter((r) => !(r.block === block && r.port === port)) };
}

export function moveReport(model: Model, index: number, delta: -1 | 1): Model {
  const report = [...(model.report ?? [])];
  const to = index + delta;
  if (to < 0 || to >= report.length) return model;
  [report[index], report[to]] = [report[to], report[index]];
  return { ...model, report };
}

export function renameReport(model: Model, index: number, label: string): Model {
  const report = (model.report ?? []).map((r, i) => (i === index ? { ...r, label } : r));
  return { ...model, report };
}

// ---------------------------------------------------------------- scenarios

export type Scenario = NonNullable<Model["scenarios"]>[number];

export function scenarioOverride(model: Model, scenarioId: string, block: string) {
  return model.scenarios?.find((s) => s.id === scenarioId)?.overrides?.find((o) => o.block === block);
}

function updateScenario(model: Model, scenarioId: string, change: (s: Scenario) => Scenario): Model {
  return { ...model, scenarios: (model.scenarios ?? []).map((s) => (s.id === scenarioId ? change(s) : s)) };
}

/** Sets (or, with undefined, clears) one overridden inline value or setting on a block in a scenario. */
export function setOverride(
  model: Model,
  scenarioId: string,
  block: string,
  field: "inline" | "settings",
  key: string,
  value: unknown,
): Model {
  return updateScenario(model, scenarioId, (s) => {
    const overrides = [...(s.overrides ?? [])];
    const i = overrides.findIndex((o) => o.block === block);
    const current = i >= 0 ? overrides[i] : { block, inline: {}, settings: {} };
    const bucket: Record<string, unknown> = { ...(current[field] ?? {}) };
    if (value === undefined) delete bucket[key];
    else bucket[key] = value;
    const next = { ...current, [field]: bucket };
    const empty = !Object.keys(next.inline ?? {}).length && !Object.keys(next.settings ?? {}).length;
    if (i >= 0) {
      if (empty) overrides.splice(i, 1);
      else overrides[i] = next;
    } else if (!empty) overrides.push(next);
    return { ...s, overrides };
  });
}

export function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "scenario";
}

export function addScenario(model: Model, name: string): { model: Model; id: string } {
  const taken = new Set((model.scenarios ?? []).map((s) => s.id));
  let id = slug(name);
  for (let n = 2; taken.has(id); n++) id = `${slug(name)}-${n}`;
  return { model: { ...model, scenarios: [...(model.scenarios ?? []), { id, name, overrides: [] }] }, id };
}

export function renameScenario(model: Model, scenarioId: string, name: string): Model {
  return updateScenario(model, scenarioId, (s) => ({ ...s, name }));
}

export function deleteScenario(model: Model, scenarioId: string): Model {
  return { ...model, scenarios: (model.scenarios ?? []).filter((s) => s.id !== scenarioId) };
}

// ---------------------------------------------------------------- subsystems

export type Composite = NonNullable<Model["composites"]>[number];

export function compositeRef(c: Composite): string {
  return `${c.id}@${c.version ?? 1}`;
}

/** A subsystem seen as a block spec, so the canvas, inspector and wiring treat it like any block. */
export function compositeAsSpec(c: Composite): BlockSpec {
  return {
    id: c.id,
    version: c.version ?? 1,
    title: c.title,
    category: "My blocks",
    doc: c.doc || `A subsystem of ${c.blocks.length} blocks.`,
    impl: "composite",
    inputs: (c.inputs ?? []).map((i) => ({ name: i.name, type: i.type ?? "any", required: false })),
    outputs: c.outputs.map((o) => ({ name: o.name, type: "any" })),
    settings: [],
  };
}

function uniqueName(base: string, taken: Set<string>): string {
  const clean = base.replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "port";
  let name = clean;
  for (let n = 2; taken.has(name); n++) name = `${clean}_${n}`;
  taken.add(name);
  return name;
}

/**
 * Groups blocks into a new subsystem and replaces them with one instance.
 * Each distinct outside source feeding the group becomes an input port; each inside output used
 * outside (or on the summary) becomes an output port.
 */
export function groupIntoComposite(
  model: Model,
  blockIds: string[],
  specs: Record<string, BlockSpec>,
  title?: string,
): { model: Model; instance: string; compositeId: string } {
  const sel = new Set(blockIds);
  const inner = model.blocks.filter((b) => sel.has(b.uuid));
  const taken = new Set((model.composites ?? []).map((c) => c.id));
  let n = (model.composites ?? []).length + 1;
  const name = title ?? `Subsystem ${n}`;
  let id = `user.${slug(name).replace(/-/g, "_")}`;
  while (taken.has(id)) id = `user.${slug(name).replace(/-/g, "_")}_${++n}`;
  const instance = newId();
  const left = Math.min(...inner.map((b) => b.position.x));
  const top = Math.min(...inner.map((b) => b.position.y));
  const label = (b: BlockInstance) => b.label || specs[b.spec]?.title || "block";

  const inputNames = new Set<string>();
  const inputs = new Map<string, { name: string; targets: { block: string; port: string }[] }>();
  const outsideWires: Wire[] = [];
  const innerWires: Wire[] = [];
  const outputNames = new Set<string>();
  const outputs = new Map<string, { name: string; source: { block: string; port: string } }>();
  const outputFor = (block: string, port: string) => {
    const key = `${block}:${port}`;
    if (!outputs.has(key)) {
      const b = inner.find((x) => x.uuid === block)!;
      const nm = uniqueName(specs[b.spec]?.outputs.length === 1 ? label(b) : `${label(b)}_${port}`, outputNames);
      outputs.set(key, { name: nm, source: { block, port } });
    }
    return outputs.get(key)!.name;
  };

  for (const w of model.wires) {
    const fromIn = sel.has(w.from.block);
    const toIn = sel.has(w.to.block);
    if (fromIn && toIn) innerWires.push(w);
    else if (!fromIn && toIn) {
      const key = `${w.from.block}:${w.from.port}`;
      if (!inputs.has(key)) {
        inputs.set(key, { name: uniqueName(w.to.port, inputNames), targets: [] });
        outsideWires.push({ uuid: newId(), from: w.from, to: { block: instance, port: inputs.get(key)!.name } });
      }
      inputs.get(key)!.targets.push({ ...w.to });
    } else if (fromIn && !toIn) {
      outsideWires.push({ ...w, from: { block: instance, port: outputFor(w.from.block, w.from.port) } });
    } else outsideWires.push(w);
  }
  const report = (model.report ?? []).map((r) =>
    sel.has(r.block) ? { ...r, block: instance, port: outputFor(r.block, r.port) } : r,
  );
  if (outputs.size === 0) {
    // Nothing uses the group's results yet: expose the outputs of its end blocks, those not used inside.
    const usedInside = new Set(innerWires.map((w) => w.from.block));
    for (const b of inner) {
      if (usedInside.has(b.uuid)) continue;
      for (const p of specs[b.spec]?.outputs ?? []) outputFor(b.uuid, p.name);
    }
  }

  const composite: Composite = {
    id,
    version: 1,
    title: name,
    doc: "",
    inputs: [...inputs.values()].map((i) => ({ name: i.name, type: "any", targets: i.targets })),
    outputs: [...outputs.values()],
    blocks: inner.map((b) => ({ ...b, position: { x: b.position.x - left, y: b.position.y - top } })),
    wires: innerWires,
  };
  const instanceBlock: BlockInstance = {
    uuid: instance,
    spec: `${id}@1`,
    label: name,
    inline: {},
    settings: {},
    position: { x: left, y: top },
  };
  return {
    model: {
      ...model,
      blocks: [...model.blocks.filter((b) => !sel.has(b.uuid)), instanceBlock],
      wires: outsideWires,
      report,
      composites: [...(model.composites ?? []), composite],
      // Scenario overrides apply to top-level blocks only; overrides on grouped blocks are dropped.
      scenarios: (model.scenarios ?? []).map((s) => ({ ...s, overrides: (s.overrides ?? []).filter((o) => !sel.has(o.block)) })),
    },
    instance,
    compositeId: id,
  };
}

/** Replaces a subsystem instance with copies of its inner blocks; drops the definition if nothing else uses it. */
export function ungroup(model: Model, instance: string): { model: Model; ids: string[] } {
  const block = model.blocks.find((b) => b.uuid === instance);
  const composite = block && (model.composites ?? []).find((c) => compositeRef(c) === block.spec);
  if (!block || !composite) return { model, ids: [] };
  const remap = new Map(composite.blocks.map((b) => [b.uuid, newId()]));
  const blocks = composite.blocks.map((b) => {
    const inputFeeds = (composite.inputs ?? []).filter(
      (i) => block.inline?.[i.name] !== undefined && i.targets.some((t) => t.block === b.uuid),
    );
    const inline = { ...(b.inline ?? {}) };
    for (const i of inputFeeds) for (const t of i.targets) if (t.block === b.uuid) inline[t.port] = block.inline![i.name];
    return { ...b, uuid: remap.get(b.uuid)!, inline, position: { x: b.position.x + block.position.x, y: b.position.y + block.position.y } };
  });
  const mapRef = (r: { block: string; port: string }) => ({ block: remap.get(r.block)!, port: r.port });
  const wires: Wire[] = composite.wires.map((w) => ({ uuid: newId(), from: mapRef(w.from), to: mapRef(w.to) }));
  for (const w of model.wires) {
    if (w.to.block === instance) {
      const input = (composite.inputs ?? []).find((i) => i.name === w.to.port);
      for (const t of input?.targets ?? []) if (remap.has(t.block)) wires.push({ uuid: newId(), from: w.from, to: mapRef(t) });
    } else if (w.from.block === instance) {
      const output = composite.outputs.find((o) => o.name === w.from.port);
      if (output && remap.has(output.source.block)) wires.push({ ...w, from: mapRef(output.source) });
    } else wires.push(w);
  }
  const report = (model.report ?? []).flatMap((r) => {
    if (r.block !== instance) return [r];
    const output = composite.outputs.find((o) => o.name === r.port);
    return output && remap.has(output.source.block) ? [{ ...r, ...mapRef(output.source) }] : [];
  });
  const stillUsed = model.blocks.some((b) => b.uuid !== instance && b.spec === block.spec);
  return {
    model: {
      ...model,
      blocks: [...model.blocks.filter((b) => b.uuid !== instance), ...blocks],
      wires,
      report,
      composites: stillUsed ? model.composites : (model.composites ?? []).filter((c) => c !== composite),
    },
    ids: [...remap.values()],
  };
}
