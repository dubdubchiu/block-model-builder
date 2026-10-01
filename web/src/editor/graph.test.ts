import { describe, expect, it } from "vitest";
import demo from "../../../models/examples/demo.json";
import type { BlockSpec, Model } from "../api/types.gen";
import {
  type ConnectContext,
  addBlock,
  blankModel,
  connect,
  copy,
  deleteItems,
  disconnect,
  moveBlocks,
  paste,
  setInline,
  setSetting,
  wouldCycle,
} from "./graph";
import { parseType, refuseReason } from "./patterns";

const model = demo as Model;
const [PRICE, UNITS, PRODUCT, TOTAL] = model.blocks.map((b) => b.uuid);
const GROUPS = {
  number: ["int", "float", "count", "quantity", "percent", "currency"],
  integer: ["int", "count"],
  any: ["int", "float", "count", "quantity", "percent", "currency", "bool", "str", "date"],
};
const port = (name: string, type: string, inline?: number) => ({ name, type, ...(inline !== undefined ? { inline } : {}) });
const spec = (id: string, inputs: ReturnType<typeof port>[], output = "number", settings: BlockSpec["settings"] = []): BlockSpec => ({
  id,
  version: 1,
  title: id,
  category: "Test",
  doc: "",
  impl: id,
  inputs,
  settings,
  outputs: [port(output === "series<bool>" ? "value" : "result", output)],
});
const SPECS: Record<string, BlockSpec> = {
  "source.constant@1": { ...spec("source.constant", [], "any"), outputs: [port("value", "any")] },
  "source.series@1": { ...spec("source.series", [], "series<any>"), outputs: [port("value", "series<any>")] },
  "math.multiply@1": spec("math.multiply", [port("a", "number", 1), port("b", "number", 1)]),
  "math.add@1": spec("math.add", [port("a", "number", 0), port("b", "number", 0)]),
  "series.lag@1": spec("series.lag", [port("x", "number"), port("n", "scalar<integer>", 1)], "series<number>"),
  "source.flag@1": spec("source.flag", [], "series<bool>"),
};
const CTX: ConnectContext = {
  specs: SPECS,
  kindGroups: GROUPS,
  types: { [UNITS]: { value: "series<count>" }, [PRICE]: { value: "currency" } },
};

describe("patterns", () => {
  it("parses types", () => {
    expect(parseType("series<currency>")).toEqual({ shape: "series", kind: "currency" });
    expect(parseType("count")).toEqual({ shape: "scalar", kind: "count" });
  });

  it("refuses per-period values on single-value ports, wrong kinds, and TRUE/FALSE in arithmetic", () => {
    expect(refuseReason("n", "scalar<integer>", "series<int>", GROUPS)).toContain("single value");
    expect(refuseReason("n", "scalar<integer>", "float", GROUPS)).toContain("whole number");
    expect(refuseReason("x", "number", "series<bool>", GROUPS)).toContain("If block");
    expect(refuseReason("x", "number", "series<currency>", GROUPS)).toBeNull();
    expect(refuseReason("n", "scalar<integer>", "count", GROUPS)).toBeNull();
  });

  it("allows patterns before evaluation unless they can't match", () => {
    expect(refuseReason("n", "scalar<integer>", "number", GROUPS)).toBeNull();
    expect(refuseReason("x", "number", "series<bool>", GROUPS)).not.toBeNull();
  });
});

describe("graph operations", () => {
  it("adds a block with default settings and never mutates the input", () => {
    const withSettings = { ...SPECS["source.constant@1"], settings: [{ name: "kind", type: "str", default: "float" }] };
    const next = addBlock(model, withSettings, { x: 10.4, y: 20.6 }, "new");
    expect(next.blocks).toHaveLength(5);
    expect(next.blocks[4]).toMatchObject({ uuid: "new", spec: "source.constant@1", settings: { kind: "float" }, position: { x: 10, y: 21 } });
    expect(model.blocks).toHaveLength(4);
  });

  it("moves, sets inline values and settings, and clears them", () => {
    let m = moveBlocks(model, { [PRICE]: { x: 5, y: 6 } });
    expect(m.blocks[0].position).toEqual({ x: 5, y: 6 });
    m = setInline(m, TOTAL, "b", 200);
    expect(m.blocks[3].inline).toEqual({ b: 200 });
    m = setInline(m, TOTAL, "b", undefined);
    expect(m.blocks[3].inline).toEqual({});
    m = setSetting(m, PRICE, "unit", "EUR");
    expect(m.blocks[0].settings?.unit).toBe("EUR");
    m = setSetting(m, PRICE, "unit", "");
    expect(m.blocks[0].settings).not.toHaveProperty("unit");
  });

  it("deletes blocks with their wires and report lines", () => {
    const withReport = { ...model, report: [{ block: PRODUCT, port: "result", label: "Revenue" }] };
    const m = deleteItems(withReport, [PRODUCT]);
    expect(m.blocks.map((b) => b.uuid)).toEqual([PRICE, UNITS, TOTAL]);
    expect(m.wires).toHaveLength(0);
    expect(m.report).toHaveLength(0);
    expect(deleteItems(model, [], [model.wires[0].uuid]).wires).toHaveLength(2);
  });

  it("detects loops", () => {
    expect(wouldCycle(model, TOTAL, PRODUCT)).toBe(true);
    expect(wouldCycle(model, PRICE, TOTAL)).toBe(false);
    expect(wouldCycle(model, TOTAL, TOTAL)).toBe(true);
  });

  it("connects, replacing an existing wire into the same input", () => {
    const out = connect(model, CTX, { block: UNITS, port: "value" }, { block: PRODUCT, port: "a" });
    if (!("model" in out)) throw new Error(out.refused);
    const into = out.model.wires.filter((w) => w.to.block === PRODUCT && w.to.port === "a");
    expect(into).toHaveLength(1);
    expect(into[0].from.block).toBe(UNITS);
    expect(out.model.wires).toHaveLength(3);
  });

  it("refuses loops and type mismatches with a reason", () => {
    const loop = connect(model, CTX, { block: TOTAL, port: "result" }, { block: PRODUCT, port: "a" });
    expect("refused" in loop && loop.refused).toContain("loop");
    const lagged = addBlock(model, SPECS["series.lag@1"], { x: 0, y: 0 }, "lag");
    const wrong = connect(lagged, CTX, { block: UNITS, port: "value" }, { block: "lag", port: "n" });
    expect("refused" in wrong && wrong.refused).toContain("single value");
  });

  it("disconnects an input", () => {
    expect(disconnect(model, PRODUCT, "a").wires).toHaveLength(2);
  });

  it("copies and pastes with new ids, keeping only wires among the copied blocks", () => {
    const clip = copy(model, [PRICE, PRODUCT]);
    expect(clip.wires).toHaveLength(1);
    const out = paste(model, clip);
    expect(out.ids).toHaveLength(2);
    expect(out.ids).not.toContain(PRICE);
    const pasted = out.model.blocks.filter((b) => out.ids.includes(b.uuid));
    expect(pasted[0].position.x).toBe(model.blocks[0].position.x + 40);
    const newWire = out.model.wires[out.model.wires.length - 1];
    expect(out.ids).toContain(newWire.from.block);
    expect(out.ids).toContain(newWire.to.block);
  });

  it("makes a blank model with a quarterly timeline starting next January", () => {
    const m = blankModel();
    expect(m.blocks).toEqual([]);
    expect(m.timeline.start).toMatch(/^\d{4}-01-01$/);
    expect(m.timeline.frequency).toBe("quarter");
  });
});

describe("summary rows", async () => {
  const { addReport, inReport, moveReport, removeReport, renameReport } = await import("./graph");
  it("adds once, renames, reorders and removes", () => {
    let m = addReport(model, PRODUCT, "result", "Product revenue");
    m = addReport(m, PRODUCT, "result", "Again");
    m = addReport(m, TOTAL, "result", "Total revenue");
    expect(m.report?.map((r) => r.label)).toEqual(["Product revenue", "Total revenue"]);
    expect(inReport(m, TOTAL, "result")).toBe(true);
    m = moveReport(m, 1, -1);
    expect(m.report?.[0].label).toBe("Total revenue");
    expect(moveReport(m, 0, -1)).toBe(m);
    m = renameReport(m, 0, "Revenue");
    expect(m.report?.[0].label).toBe("Revenue");
    m = removeReport(m, PRODUCT, "result");
    expect(m.report).toHaveLength(1);
  });
});

describe("feedback, scenarios and subsystems", async () => {
  const g = await import("./graph");

  it("allows a loop only into a Feedback block's x", () => {
    const fb = { ...SPECS["math.add@1"], id: "series.feedback", inputs: [port("x", "number"), port("initial", "scalar<number>", 0)] };
    const specs = { ...SPECS, "series.feedback@1": fb };
    let m = g.addBlock(model, fb, { x: 0, y: 0 }, "fb");
    const ctx = { ...CTX, specs };
    const intoFb = g.connect(m, ctx, { block: TOTAL, port: "result" }, { block: "fb", port: "x" });
    if (!("model" in intoFb)) throw new Error(intoFb.refused);
    m = intoFb.model;
    const back = g.connect(m, ctx, { block: "fb", port: "result" }, { block: PRODUCT, port: "a" });
    expect("model" in back).toBe(true);
    expect(g.wouldCycle(model, TOTAL, PRODUCT, "a")).toBe(true);
  });

  it("sets and clears scenario overrides", () => {
    let m = g.addScenario(model, "High price").model;
    expect(m.scenarios?.[0].id).toBe("high-price");
    m = g.addScenario(m, "High price").model;
    expect(m.scenarios?.[1].id).toBe("high-price-2");
    m = g.setOverride(m, "high-price", PRICE, "settings", "value", 14);
    expect(g.scenarioOverride(m, "high-price", PRICE)?.settings).toEqual({ value: 14 });
    m = g.setOverride(m, "high-price", PRICE, "settings", "value", undefined);
    expect(m.scenarios?.[0].overrides).toEqual([]);
    m = g.renameScenario(m, "high-price", "Premium");
    expect(m.scenarios?.[0].name).toBe("Premium");
    expect(g.deleteScenario(m, "high-price").scenarios).toHaveLength(1);
  });

  it("exposes the end blocks' outputs when nothing outside uses the group", () => {
    const grouped = g.groupIntoComposite(model, [PRODUCT, TOTAL], SPECS);
    expect(grouped.model.composites![0].outputs.map((o) => o.source.block)).toEqual([TOTAL]);
  });

  it("groups blocks into a subsystem and ungroups them back", () => {
    const withReport = g.addReport(model, TOTAL, "result", "Total revenue");
    const grouped = g.groupIntoComposite(withReport, [PRODUCT, TOTAL], SPECS, "Revenue");
    const c = grouped.model.composites![0];
    expect(c.id).toBe("user.revenue");
    expect(c.inputs?.map((i) => i.name)).toEqual(["a", "b"]);
    expect(c.outputs.map((o) => o.name)).toEqual(["Total_revenue"]);
    expect(grouped.model.blocks.map((b) => b.uuid)).toEqual([PRICE, UNITS, grouped.instance]);
    expect(grouped.model.wires.every((w) => w.to.block === grouped.instance)).toBe(true);
    expect(grouped.model.report?.[0]).toMatchObject({ block: grouped.instance, port: "Total_revenue" });
    expect(g.compositeAsSpec(c).inputs?.map((p) => p.name)).toEqual(["a", "b"]);

    const back = g.ungroup(grouped.model, grouped.instance);
    expect(back.model.blocks).toHaveLength(4);
    expect(back.model.wires).toHaveLength(3);
    expect(back.model.composites).toEqual([]);
    const total = back.model.blocks.find((b) => b.label === "Total revenue")!;
    expect(back.model.report?.[0].block).toBe(total.uuid);
    expect(total.inline).toEqual({ b: 150 });
  });
});
