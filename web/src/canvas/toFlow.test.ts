import { describe, expect, it } from "vitest";
import demo from "../../../models/examples/demo.json";
import type { BlockSpec, EvaluateResponse, Model } from "../api/types.gen";
import { edgeClass, toFlow } from "./toFlow";

const port = (name: string, type: string) => ({ name, type });
const spec = (id: string, title: string, inputs: string[], output: [string, string]): BlockSpec => ({
  id,
  version: 1,
  title,
  category: "Test",
  doc: "",
  impl: id,
  inputs: inputs.map((name) => port(name, "number")),
  outputs: [port(...output)],
});
const specs: Record<string, BlockSpec> = {
  "source.constant@1": spec("source.constant", "Constant", [], ["value", "any"]),
  "source.series@1": spec("source.series", "Series input", [], ["value", "series<any>"]),
  "math.multiply@1": spec("math.multiply", "Multiply", ["a", "b"], ["result", "number"]),
  "math.add@1": spec("math.add", "Add", ["a", "b"], ["result", "number"]),
};

describe("edgeClass", () => {
  it("weights series wires and dashes bool wires", () => {
    expect(edgeClass("float")).toBe("bm-edge");
    expect(edgeClass("series<currency>")).toBe("bm-edge bm-edge--series");
    expect(edgeClass("annual<count>")).toBe("bm-edge bm-edge--series");
    expect(edgeClass("series<bool>")).toBe("bm-edge bm-edge--series bm-edge--bool");
    expect(edgeClass(undefined)).toBe("bm-edge");
  });
});

describe("toFlow", () => {
  const model = demo as Model;

  it("maps blocks to nodes and wires to edges weighted by the spec pattern before evaluation", () => {
    const { nodes, edges } = toFlow(model, specs);
    expect(nodes).toHaveLength(4);
    expect(edges).toHaveLength(3);
    const priceToMultiply = edges.find((e) => e.targetHandle === "a" && e.sourceHandle === "value");
    expect(priceToMultiply?.className).toBe("bm-edge");
    const unitsToMultiply = edges.find((e) => e.targetHandle === "b" && e.sourceHandle === "value");
    expect(unitsToMultiply?.className).toBe("bm-edge bm-edge--series");
    const add = nodes.find((n) => n.data.label === "Total revenue");
    expect(add?.data.wiredInputs).toEqual(["a"]);
    expect(add?.data.inline).toEqual({ b: 150 });
  });

  it("attaches outputs and block errors from the result", () => {
    const addId = model.blocks[3].uuid;
    const result: EvaluateResponse = {
      engine: "blockmodel 0.1.0",
      timeline: { period_labels: ["2027Q1"], years: [2027] },
      outputs: { [model.blocks[0].uuid]: { value: { type: "currency", unit: "USD/unit", value: 12.5 } } },
      errors: [{ block: addId, message: "Input a is broken." }],
      timing: { evaluate_ms: 1 },
    };
    const { nodes } = toFlow(model, specs, result);
    expect(nodes[0].data.results?.value.value).toBe(12.5);
    expect(nodes.find((n) => n.id === addId)?.data.error).toBe("Input a is broken.");
  });

  it("weights edges by the inferred type after evaluation", () => {
    const multiply = model.blocks[2].uuid;
    const result: EvaluateResponse = {
      engine: "blockmodel 0.1.0",
      timeline: { period_labels: [], years: [] },
      outputs: { [multiply]: { result: { type: "series<currency>", unit: "USD", value: null } } },
      errors: [],
      timing: { evaluate_ms: 1 },
    };
    const multiplyToAdd = toFlow(model, specs, result).edges.find((e) => e.source === multiply);
    expect(multiplyToAdd?.className).toBe("bm-edge bm-edge--series");
  });

  it("flags an unknown block type", () => {
    const broken = { ...model, blocks: [{ ...model.blocks[0], spec: "core.missing@1" }] };
    const { nodes } = toFlow(broken, specs);
    expect(nodes[0].data.error).toContain("Unknown block type");
  });
});
