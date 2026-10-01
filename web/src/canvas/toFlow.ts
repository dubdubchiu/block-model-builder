import type { Edge, Node } from "@xyflow/react";
import type { BlockSpec, EvaluateResponse, Model, PortResult, PortSpec } from "../api/types.gen";

export interface BlockNodeData extends Record<string, unknown> {
  uuid: string;
  title: string;
  label?: string | null;
  inputs: PortSpec[];
  outputs: PortSpec[];
  wiredInputs: string[];
  inline: Record<string, number | boolean | string>;
  /** Inferred type, unit and value per output port, from the last evaluation. */
  results?: Record<string, PortResult>;
  error?: string;
  warnings?: string[];
  /** A subsystem instance: double-click or "Open subsystem" to edit inside. */
  composite?: boolean;
  /** For inputs (Constant, Series input): illustrative figures, or a real figure with its source. */
  source?: { illustrative: boolean; text: string };
  readOnly?: boolean;
}

export type BlockFlowNode = Node<BlockNodeData, "block">;

/** Wire weight follows LabVIEW without color: scalar 1px, series 2px, bool dashed. */
export function edgeClass(type: string | undefined): string {
  if (!type) return "bm-edge";
  const classes = ["bm-edge"];
  if (type.startsWith("series<") || type.startsWith("annual<")) classes.push("bm-edge--series");
  if (type === "bool" || type.endsWith("<bool>")) classes.push("bm-edge--bool");
  return classes.join(" ");
}

const SOURCE_BLOCKS = new Set(["source.constant@1", "source.series@1"]);

function sourceOf(settings: Record<string, unknown> | undefined): BlockNodeData["source"] {
  const text = typeof settings?.source === "string" ? settings.source : "illustrative";
  return { illustrative: text === "illustrative", text };
}

export function toFlow(
  model: Model,
  specs: Record<string, BlockSpec>,
  result?: EvaluateResponse,
  options: { selection?: string[]; selectedWires?: string[]; readOnly?: boolean } = {},
): { nodes: BlockFlowNode[]; edges: Edge[] } {
  const selected = new Set(options.selection ?? []);
  const selectedWires = new Set(options.selectedWires ?? []);
  const errors = new Map((result?.errors ?? []).filter((e) => e.block).map((e) => [e.block as string, e.message]));
  const warnings = new Map<string, string[]>();
  for (const w of result?.warnings ?? []) if (w.block) warnings.set(w.block, [...(warnings.get(w.block) ?? []), w.message]);
  const wiredInputs = new Map<string, string[]>();
  for (const w of model.wires) {
    wiredInputs.set(w.to.block, [...(wiredInputs.get(w.to.block) ?? []), w.to.port]);
  }

  const nodes: BlockFlowNode[] = model.blocks.map((b) => {
    const spec = specs[b.spec];
    return {
      id: b.uuid,
      type: "block",
      position: b.position,
      selected: selected.has(b.uuid),
      data: {
        uuid: b.uuid,
        title: spec?.title ?? b.spec,
        label: b.label,
        inputs: spec?.inputs ?? [],
        outputs: spec?.outputs ?? [],
        wiredInputs: wiredInputs.get(b.uuid) ?? [],
        inline: b.inline ?? {},
        results: result?.outputs[b.uuid],
        error: errors.get(b.uuid) ?? (spec ? undefined : `Unknown block type ${b.spec}.`),
        warnings: warnings.get(b.uuid),
        composite: spec?.impl === "composite",
        source: SOURCE_BLOCKS.has(b.spec) ? sourceOf(b.settings) : undefined,
        readOnly: options.readOnly,
      },
    };
  });

  const blockSpec = new Map(model.blocks.map((b) => [b.uuid, specs[b.spec]]));
  const edges: Edge[] = model.wires.map((w) => {
    // Prefer the inferred type; fall back to the spec's port pattern before the first evaluation.
    const sourceType =
      result?.outputs[w.from.block]?.[w.from.port]?.type ??
      blockSpec.get(w.from.block)?.outputs.find((p) => p.name === w.from.port)?.type;
    return {
      id: w.uuid,
      source: w.from.block,
      sourceHandle: w.from.port,
      target: w.to.block,
      targetHandle: w.to.port,
      selected: selectedWires.has(w.uuid),
      className: edgeClass(sourceType),
    };
  });

  return { nodes, edges };
}
