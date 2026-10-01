import { useReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { BlockSpec } from "../api/types.gen";
import { PALETTE_MIME } from "../canvas/Canvas";
import { type Composite, addBlock, compositeAsSpec, compositeRef, newId } from "./graph";
import { useEditor, useView } from "./store";

const CATEGORY_ORDER = ["My blocks", "Sources", "Math", "Series", "Finance", "Logic", "Lookup"];

export function Palette() {
  const view = useView();
  const apply = useEditor((s) => s.apply);
  const applyTop = useEditor((s) => s.applyTop);
  const [saved, setSaved] = useState<Composite[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api.blocks().then(
      (r) => setSaved(r.data),
      () => setSaved([]),
    );
  }, []);
  const say = useEditor((s) => s.say);
  const select = useEditor((s) => s.select);
  const flow = useReactFlow();
  const [filter, setFilter] = useState("");

  const groups = useMemo(() => {
    // The library and this model's subsystems, plus saved subsystems not yet in the model.
    const inModel = new Set(Object.keys(view?.specs ?? {}));
    const specs = [
      ...Object.values(view?.specs ?? {}),
      ...saved.filter((c) => !inModel.has(compositeRef(c))).map(compositeAsSpec),
    ];
    const q = filter.trim().toLowerCase();
    const shown = q ? specs.filter((s) => `${s.title} ${s.doc} ${s.id}`.toLowerCase().includes(q)) : specs;
    const byCategory = new Map<string, BlockSpec[]>();
    for (const s of shown) byCategory.set(s.category, [...(byCategory.get(s.category) ?? []), s]);
    const rank = (c: string) => (CATEGORY_ORDER.includes(c) ? CATEGORY_ORDER.indexOf(c) : CATEGORY_ORDER.length);
    return [...byCategory.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
  }, [view?.specs, saved, filter]);

  function ensureDefinition(spec: BlockSpec) {
    // A saved subsystem is copied into the model the first time it's used, so the model stays self-contained.
    const ref = `${spec.id}@${spec.version}`;
    const definition = saved.find((c) => compositeRef(c) === ref);
    if (definition && !view?.specs[ref]) applyTop((m) => ({ ...m, composites: [...(m.composites ?? []), definition] }));
  }

  function importBlock(file: File) {
    file
      .text()
      .then((text) => {
        const spec = JSON.parse(text) as Composite;
        if (!/^user\.[a-z0-9_]+$/.test(spec.id ?? "") || !Array.isArray(spec.blocks) || !Array.isArray(spec.outputs)) {
          throw new Error("it isn't a subsystem file (an id like user.name, blocks and outputs)");
        }
        applyTop((m) => ({ ...m, composites: [...(m.composites ?? []).filter((c) => c.id !== spec.id), spec] }));
        say(`Imported ${spec.title}. It's under My blocks.`);
      })
      .catch((e) => say(`Couldn't import ${file.name}: ${e instanceof Error ? e.message : String(e)}.`, "danger"));
  }

  function addAtCenter(spec: BlockSpec) {
    ensureDefinition(spec);
    const el = document.querySelector(".bm-canvas__surface")?.getBoundingClientRect();
    const at = el ? flow.screenToFlowPosition({ x: el.left + el.width / 2, y: el.top + el.height / 2 }) : { x: 0, y: 0 };
    const id = newId();
    apply((m) => addBlock(m, spec, { x: at.x - 100, y: at.y - 60 }, id));
    select([id]);
    say(`Added ${spec.title}. Its inputs are in the inspector.`);
  }

  return (
    <section className="dt-panel bm-palette" aria-label="Block palette">
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">Blocks</h2>
      </div>
      <div className="dt-panel__body bm-stack">
        <label className="dt-field">
          <span className="dt-field__label">Filter blocks</span>
          <input className="dt-input" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="e.g. npv" />
        </label>
        {groups.length === 0 && <p className="bm-status">No blocks match {filter}. Clear the filter to see all blocks.</p>}
        {groups.map(([category, specs]) => (
          <div key={category} className="bm-palette__group">
            <h3 className="bm-palette__category">{category}</h3>
            <ul className="bm-palette__list">
              {specs.map((spec) => (
                <li key={spec.id}>
                  <button
                    type="button"
                    className="dt-btn dt-btn--quiet bm-palette__item"
                    draggable
                    title={spec.doc}
                    onDragStart={(e) => {
                      ensureDefinition(spec);
                      e.dataTransfer.setData(PALETTE_MIME, `${spec.id}@${spec.version}`);
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={() => addAtCenter(spec)}
                    aria-label={`Add ${spec.title}`}
                  >
                    Add {spec.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div>
          <button type="button" className="dt-btn" onClick={() => fileInput.current?.click()}>
            Import block JSON
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) importBlock(file);
            }}
          />
        </div>
      </div>
    </section>
  );
}
