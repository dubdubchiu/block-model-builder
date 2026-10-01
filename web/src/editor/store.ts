import { useMemo } from "react";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";
import { ApiError, api } from "../api/client";
import type { BlockSpec, EvaluateResponse, Model } from "../api/types.gen";
import {
  type Clip,
  type Composite,
  type ConnectContext,
  compositeAsSpec,
  compositeRef,
  connect,
  copy,
  deleteItems,
  paste,
} from "./graph";
import type { KindGroups } from "./patterns";

const HISTORY_LIMIT = 100;
/** The compare-with value that means the base case (no scenario). */
export const BASE = "__base__";
const RECOMPUTE_DELAY_MS = 300;
/** Below this size, request every block's values; above it, only what's on screen. */
const ALL_VALUES_UNDER = 80;

interface Library {
  specs: Record<string, BlockSpec>;
  kindGroups: KindGroups;
}

export interface EditorState {
  library?: Library;
  model?: Model;
  result?: EvaluateResponse;
  loadError?: string;
  computing: boolean;
  evalError?: string;
  dirty: boolean;
  savedOnServer: boolean;
  selection: string[];
  selectedWires: string[];
  visible?: string[];
  past: Model[];
  future: Model[];
  clip?: Clip;
  /** One status sentence: a refused connection, a save, an import problem. */
  message?: { text: string; tone?: "danger" };
  /** The scenario being viewed and edited; undefined is the base case. */
  scenario?: string;
  compareScenario?: string;
  compareResult?: EvaluateResponse;
  /** Editing inside a subsystem: which definition, reached through which instance. */
  inside?: { compositeId: string; instance: string };

  init: () => Promise<void>;
  loadModel: (model: Model, options?: { savedOnServer?: boolean }) => void;
  /** Applies a change to what's on screen: the model, or the open subsystem's inside. */
  apply: (change: (m: Model) => Model) => void;
  /** Applies a change to the whole model, even while a subsystem is open (scenarios, subsystem titles). */
  applyTop: (change: (m: Model) => Model) => void;
  undo: () => void;
  redo: () => void;
  select: (blocks: string[], wires?: string[]) => void;
  setVisible: (ids: string[]) => void;
  connect: (from: { block: string; port: string }, to: { block: string; port: string }) => boolean;
  deleteSelection: () => void;
  copySelection: () => void;
  pasteClip: () => void;
  save: () => Promise<void>;
  say: (text: string, tone?: "danger") => void;
  recompute: () => void;
  setScenario: (id?: string) => void;
  setCompare: (id?: string) => void;
  enter: (instance: string) => void;
  leave: () => void;
}

let timer: ReturnType<typeof setTimeout> | undefined;
let sequence = 0;

export function connectContext(state: Pick<EditorState, "library" | "result" | "model" | "inside">): ConnectContext {
  const view = currentView(state);
  const types: Record<string, Record<string, string>> = {};
  for (const [block, ports] of Object.entries(view?.result?.outputs ?? {})) {
    types[block] = Object.fromEntries(Object.entries(ports).map(([p, r]) => [p, r.type]));
  }
  return { specs: view?.specs ?? {}, kindGroups: state.library?.kindGroups ?? {}, types };
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export const useEditor = create<EditorState>((set, get) => ({
  computing: false,
  dirty: false,
  savedOnServer: false,
  selection: [],
  selectedWires: [],
  past: [],
  future: [],

  init: async () => {
    try {
      const [library, demo] = await Promise.all([api.library(), api.example("demo")]);
      const specs = Object.fromEntries(library.data.specs.map((s) => [`${s.id}@${s.version}`, s]));
      set({ library: { specs, kindGroups: library.data.kind_groups }, loadError: undefined });
      if (!get().model) get().loadModel(demo.data);
    } catch (e) {
      set({ loadError: errorText(e) });
    }
  },

  loadModel: (model, options) => {
    set({
      model,
      result: undefined,
      dirty: false,
      savedOnServer: options?.savedOnServer ?? false,
      selection: [],
      selectedWires: [],
      past: [],
      future: [],
      visible: undefined,
      message: undefined,
      scenario: undefined,
      compareScenario: undefined,
      compareResult: undefined,
      inside: undefined,
    });
    get().recompute();
  },

  apply: (change) => {
    const { inside, applyTop } = get();
    applyTop((m) => (inside ? applyInside(m, inside.compositeId, change) : change(m)));
  },

  applyTop: (change) => {
    const { model, past } = get();
    if (!model) return;
    const next = change(model);
    if (next === model) return;
    set({ model: next, past: [...past, model].slice(-HISTORY_LIMIT), future: [], dirty: true });
    get().recompute();
  },

  undo: () => {
    const { model, past, future } = get();
    if (!model || !past.length) return;
    set({ model: past[past.length - 1], past: past.slice(0, -1), future: [model, ...future], dirty: true });
    get().recompute();
  },

  redo: () => {
    const { model, past, future } = get();
    if (!model || !future.length) return;
    set({ model: future[0], past: [...past, model], future: future.slice(1), dirty: true });
    get().recompute();
  },

  select: (blocks, wires = []) => {
    const { selection, selectedWires } = get();
    if (blocks.join() === selection.join() && wires.join() === selectedWires.join()) return;
    set({ selection: blocks, selectedWires: wires });
    // A newly selected block off-screen may need its values.
    if (blocks.some((b) => !get().result?.outputs[b] || Object.values(get().result!.outputs[b]).some((p) => p.value == null))) {
      get().recompute();
    }
  },

  setVisible: (ids) => {
    const before = new Set(get().visible ?? []);
    set({ visible: ids });
    if (ids.some((id) => !before.has(id))) get().recompute();
  },

  connect: (from, to) => {
    const state = get();
    const view = currentView(state);
    if (!view) return false;
    const outcome = connect(view.model, connectContext(state), from, to);
    if ("refused" in outcome) {
      set({ message: { text: outcome.refused, tone: "danger" } });
      return false;
    }
    set({ message: undefined });
    get().apply((m) => ({ ...m, wires: outcome.model.wires }));
    return true;
  },

  deleteSelection: () => {
    const { selection, selectedWires } = get();
    if (!selection.length && !selectedWires.length) return;
    get().apply((m) => deleteItems(m, selection, selectedWires));
    set({ selection: [], selectedWires: [] });
  },

  copySelection: () => {
    const view = currentView(get());
    const { selection } = get();
    if (!view || !selection.length) return;
    set({ clip: copy(view.model, selection), message: { text: `Copied ${selection.length} block${selection.length > 1 ? "s" : ""}.` } });
  },

  pasteClip: () => {
    const { clip } = get();
    const view = currentView(get());
    if (!clip || !view) return;
    const out = paste(view.model, clip);
    get().apply((m) => ({ ...m, blocks: out.model.blocks, wires: out.model.wires }));
    set({ selection: out.ids, selectedWires: [] });
  },

  save: async () => {
    const { model } = get();
    if (!model) return;
    try {
      await api.saveModel(model);
      set({ dirty: false, savedOnServer: true, message: { text: `Saved ${model.name}.` } });
    } catch (e) {
      set({ message: { text: `Couldn't save: ${errorText(e)}`, tone: "danger" } });
    }
  },

  say: (text, tone) => set({ message: { text, tone } }),

  setScenario: (id) => {
    set({ scenario: id });
    get().recompute();
  },

  setCompare: (id) => {
    set({ compareScenario: id, compareResult: undefined });
    get().recompute();
  },

  enter: (instance) => {
    const { model } = get();
    const block = model?.blocks.find((b) => b.uuid === instance);
    const composite = model?.composites?.find((c) => block && compositeRef(c) === block.spec);
    if (!composite) return;
    set({ inside: { compositeId: composite.id, instance }, selection: [], selectedWires: [], visible: undefined });
    get().recompute();
  },

  leave: () => {
    const { inside } = get();
    set({ inside: undefined, selection: inside ? [inside.instance] : [], selectedWires: [], visible: undefined });
    get().recompute();
  },

  recompute: () => {
    clearTimeout(timer);
    set({ computing: true });
    timer = setTimeout(async () => {
      const { model, visible, selection, scenario, compareScenario, inside } = get();
      if (!model) return;
      const seq = ++sequence;
      const report = (model.report ?? []).map((r) => r.block);
      let values: string[] | "all" = "all";
      if (inside) values = [...new Set([inside.instance, ...report])];
      else if (visible && model.blocks.length >= ALL_VALUES_UNDER) {
        values = [...new Set([...visible, ...selection, ...report])];
      }
      try {
        const [result, compare] = await Promise.all([
          api.evaluate(model, values, scenario),
          compareScenario !== undefined
            ? api.evaluate(model, report.length ? report : "none", compareScenario === BASE ? undefined : compareScenario)
            : undefined,
        ]);
        if (seq !== sequence) return; // a newer edit is already on its way
        set({ result: result.data, compareResult: compare?.data, computing: false, evalError: undefined });
      } catch (e) {
        if (seq !== sequence) return;
        const text = e instanceof ApiError ? e.message : errorText(e);
        set({ computing: false, evalError: text });
      }
    }, RECOMPUTE_DELAY_MS);
  },
}));

/** Applies a change to a subsystem definition, presenting it to `change` as a model of its own. */
function applyInside(model: Model, compositeId: string, change: (m: Model) => Model): Model {
  const composite = model.composites?.find((c) => c.id === compositeId);
  if (!composite) return model;
  const view: Model = { ...model, blocks: composite.blocks, wires: composite.wires, report: [], scenarios: [] };
  const next = change(view);
  if (next === view) return model;
  const composites = (next.composites ?? model.composites ?? []).map((c) =>
    c.id === compositeId ? { ...c, blocks: next.blocks, wires: next.wires } : c,
  );
  return { ...model, composites };
}

/** Library specs plus the model's subsystems, keyed id@version. */
export function specsFor(library: Library | undefined, composites: Composite[] | undefined): Record<string, BlockSpec> {
  const specs = { ...(library?.specs ?? {}) };
  for (const c of composites ?? []) specs[compositeRef(c)] = compositeAsSpec(c);
  return specs;
}

export interface View {
  /** The graph being shown: the model, or a subsystem's inside presented as a model. */
  model: Model;
  result?: EvaluateResponse;
  specs: Record<string, BlockSpec>;
  inside?: { compositeId: string; instance: string; title: string };
}

/** What the canvas and inspector show: the model, or the inside of the open subsystem with its results. */
export function currentView(state: Pick<EditorState, "model" | "result" | "library" | "inside">): View | undefined {
  const { model, result, library, inside } = state;
  if (!model) return undefined;
  const specs = specsFor(library, model.composites);
  if (!inside) return { model, result, specs };
  const composite = model.composites?.find((c) => c.id === inside.compositeId);
  if (!composite) return { model, result, specs };
  const prefix = `${inside.instance}/`;
  const inner = (key: string) => (key.startsWith(prefix) && !key.slice(prefix.length).includes("/") ? key.slice(prefix.length) : undefined);
  const outputs: EvaluateResponse["outputs"] = {};
  for (const [key, ports] of Object.entries(result?.outputs ?? {})) {
    const id = inner(key);
    if (id) outputs[id] = ports;
  }
  const remap = (list: EvaluateResponse["errors"]) =>
    list.flatMap((e) => {
      const id = e.path ? inner(e.path) : undefined;
      return id ? [{ ...e, block: id, message: e.message.replace(/^Inside [^,]+, [^:]+: /, "") }] : [];
    });
  return {
    model: { ...model, blocks: composite.blocks, wires: composite.wires, report: [], scenarios: [] },
    result: result && { ...result, outputs, errors: remap(result.errors), warnings: remap(result.warnings ?? []) },
    specs,
    inside: { ...inside, title: composite.title },
  };
}

/** The current view for components, recomputed only when its inputs change. */
export function useView(): View | undefined {
  const { model, result, library, inside } = useEditor(
    useShallow((s) => ({ model: s.model, result: s.result, library: s.library, inside: s.inside })),
  );
  return useMemo(() => currentView({ model, result, library, inside }), [model, result, library, inside]);
}
