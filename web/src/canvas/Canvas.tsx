import {
  Background,
  BackgroundVariant,
  type Connection,
  type Edge,
  type NodeChange,
  type OnSelectionChangeParams,
  ReactFlow,
  applyNodeChanges,
  useNodesInitialized,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { type DragEvent, useCallback, useEffect, useMemo, useState } from "react";
import { addBlock, moveBlocks } from "../editor/graph";
import { useEditor, useView } from "../editor/store";
import { BlockNode } from "./BlockNode";
import { type BlockFlowNode, toFlow } from "./toFlow";

const nodeTypes = { block: BlockNode };
export const PALETTE_MIME = "application/x-blockmodel-spec";

const LARGE_MODEL = 40;
const COLUMN = 380;

/** Fit everything for small models; for large ones, start at the leftmost columns at a readable zoom. */
function initialView(flow: ReturnType<typeof useReactFlow>) {
  const all = flow.getNodes();
  if (all.length <= LARGE_MODEL) {
    flow.fitView({ padding: 0.2, maxZoom: 1, duration: 0 });
    return;
  }
  const left = Math.min(...all.map((n) => n.position.x));
  const first = all.filter((n) => n.position.x < left + 3 * COLUMN);
  flow.fitView({ nodes: first, padding: 0.05, maxZoom: 1, minZoom: 0.5, duration: 0 });
}

function FindBlock() {
  const view = useView();
  const model = view?.model;
  const select = useEditor((s) => s.select);
  const say = useEditor((s) => s.say);
  const flow = useReactFlow();
  const [text, setText] = useState("");
  const names = useMemo(
    () => (model?.blocks ?? []).map((b) => ({ id: b.uuid, name: b.label || view?.specs[b.spec]?.title || b.spec })),
    [model, view?.specs],
  );

  function find(query: string) {
    const q = query.trim().toLowerCase();
    if (!q) return;
    const lower = (n: { name: string }) => n.name.toLowerCase();
    const hit =
      names.find((n) => lower(n) === q) ?? names.find((n) => lower(n).startsWith(q)) ?? names.find((n) => lower(n).includes(q));
    const block = hit && model?.blocks.find((b) => b.uuid === hit.id);
    if (!hit || !block) {
      say(`No block is named like ${query}. Check the spelling, or clear the field.`, "danger");
      return;
    }
    select([hit.id]);
    flow.setCenter(block.position.x + 120, block.position.y + 80, { zoom: Math.max(flow.getZoom(), 0.9), duration: 0 });
    say(`Found ${hit.name}.`);
  }

  return (
    <div className="bm-find">
      <label className="dt-field__label" htmlFor="find-block">
        Find block
      </label>
      <input
        id="find-block"
        className="dt-input"
        list="find-block-names"
        value={text}
        placeholder="Block label"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") find(text);
        }}
      />
      <datalist id="find-block-names">
        {names.map((n) => (
          <option key={n.id} value={n.name} />
        ))}
      </datalist>
      <button type="button" className="dt-btn" onClick={() => find(text)}>
        Find block
      </button>
    </div>
  );
}

function ZoomControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <div className="bm-canvas__tools">
      <FindBlock />
      <button type="button" className="dt-btn" onClick={() => zoomIn({ duration: 0 })}>
        Zoom in
      </button>
      <button type="button" className="dt-btn" onClick={() => zoomOut({ duration: 0 })}>
        Zoom out
      </button>
      <button type="button" className="dt-btn" onClick={() => fitView({ padding: 0.2, duration: 0 })}>
        Fit view
      </button>
    </div>
  );
}

/** Ids of blocks whose boxes intersect the visible canvas area. */
function visibleIds(nodes: BlockFlowNode[], viewport: { x: number; y: number; zoom: number }, el: Element | null): string[] {
  if (!el) return nodes.map((n) => n.id);
  const { width, height } = el.getBoundingClientRect();
  const left = -viewport.x / viewport.zoom;
  const top = -viewport.y / viewport.zoom;
  const right = left + width / viewport.zoom;
  const bottom = top + height / viewport.zoom;
  return nodes
    .filter((n) => {
      const w = n.measured?.width ?? 240;
      const h = n.measured?.height ?? 160;
      return n.position.x + w >= left && n.position.x <= right && n.position.y + h >= top && n.position.y <= bottom;
    })
    .map((n) => n.id);
}

export function Canvas({ readOnly }: { readOnly: boolean }) {
  const { selection, selectedWires, message } = useEditor();
  const view = useView();
  const { apply, connect, select, setVisible, enter } = useEditor.getState();
  const flow = useReactFlow();

  const derived = useMemo(
    () => (view ? toFlow(view.model, view.specs, view.result, { selection, selectedWires, readOnly }) : undefined),
    [view, selection, selectedWires, readOnly],
  );
  const [nodes, setNodes] = useState<BlockFlowNode[]>([]);
  useEffect(() => setNodes(derived?.nodes ?? []), [derived]);
  const edges: Edge[] = derived?.edges ?? [];

  // Set the view once a newly opened model (or subsystem) is measured, not on every edit.
  const modelId = view ? `${view.model.id}:${view.inside?.compositeId ?? ""}` : undefined;
  const measured = useNodesInitialized();
  const [viewFor, setViewFor] = useState<string>();
  useEffect(() => {
    if (modelId && measured && viewFor !== modelId) {
      initialView(flow);
      setViewFor(modelId);
    }
  }, [modelId, measured, viewFor, flow]);

  const onNodesChange = useCallback((changes: NodeChange<BlockFlowNode>[]) => {
    // Positions and selection flags change locally while dragging; the model commits on drag stop.
    setNodes((current) => applyNodeChanges(changes.filter((c) => c.type !== "remove"), current));
  }, []);

  const onNodeDragStop = useCallback(
    (_: unknown, __: unknown, dragged: BlockFlowNode[]) => {
      apply((m) => moveBlocks(m, Object.fromEntries(dragged.map((n) => [n.id, n.position]))));
    },
    [apply],
  );

  const onSelectionChange = useCallback(
    ({ nodes: n, edges: e }: OnSelectionChangeParams) => select(n.map((x) => x.id), e.map((x) => x.id)),
    [select],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source && c.target && c.sourceHandle && c.targetHandle) {
        connect({ block: c.source, port: c.sourceHandle }, { block: c.target, port: c.targetHandle });
      }
    },
    [connect],
  );

  const reportVisible = useCallback(() => {
    const el = document.querySelector(".bm-canvas__surface");
    setVisible(visibleIds(flow.getNodes() as BlockFlowNode[], flow.getViewport(), el));
  }, [flow, setVisible]);
  useEffect(() => {
    if (nodes.length) requestAnimationFrame(reportVisible);
  }, [modelId, nodes.length, reportVisible]);

  const onDragOver = (e: DragEvent) => {
    if (readOnly) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };
  const onDrop = (e: DragEvent) => {
    const ref = e.dataTransfer.getData(PALETTE_MIME);
    const spec = ref && view?.specs[ref];
    if (!spec || readOnly) return;
    e.preventDefault();
    const at = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    apply((m) => addBlock(m, spec, at));
  };

  return (
    <div className="bm-canvas">
      <ZoomControls />
      <div className="bm-canvas__surface" onDragOver={onDragOver} onDrop={onDrop}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStop={onNodeDragStop}
          onSelectionChange={onSelectionChange}
          onConnect={onConnect}
          onNodeDoubleClick={(_, node) => {
            if ((node as BlockFlowNode).data.composite && !readOnly) enter(node.id);
          }}
          onMoveEnd={reportVisible}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable
          deleteKeyCode={null}
          minZoom={0.1}
          aria-label="Model diagram"
        >
          <Background variant={BackgroundVariant.Lines} gap={24} color="var(--construction)" />
        </ReactFlow>
      </div>
      <p className="bm-status" aria-live="polite" data-testid="canvas-message">
        {message && <span className={message.tone === "danger" ? "bm-status--danger" : undefined}>{message.text}</span>}
      </p>
    </div>
  );
}
