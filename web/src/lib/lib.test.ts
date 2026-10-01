import { describe, expect, it } from "vitest";
import { formatBytes, formatMs, previewOutput } from "./format";
import { GATE, percentile, summarize } from "./stats";
import { applyTheme } from "./theme";

describe("previewOutput", () => {
  it("formats scalars and booleans", () => {
    expect(previewOutput(12.5)).toBe("12.5");
    expect(previewOutput(1234567.891)).toBe("1,234,567.89");
    expect(previewOutput(true)).toBe("TRUE");
  });

  it("shows the head of a series and its length", () => {
    expect(previewOutput([650, 650, 650, 650])).toBe("650, 650, 650, … (4 periods)");
    expect(previewOutput([1, 2])).toBe("1, 2 (2 periods)");
  });
});

describe("formatting sizes and times", () => {
  it("picks units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(532 * 1024)).toBe("532 KiB");
    expect(formatMs(3.456)).toBe("3.46 ms");
    expect(formatMs(42.34)).toBe("42.3 ms");
  });
});

describe("percentile", () => {
  it("uses nearest rank", () => {
    const values = [5, 1, 4, 2, 3];
    expect(percentile(values, 50)).toBe(3);
    expect(percentile(values, 95)).toBe(5);
    expect(percentile(values, 1)).toBe(1);
  });

  it("rejects an empty list", () => {
    expect(() => percentile([], 50)).toThrow();
  });
});

describe("summarize", () => {
  const sample = (roundTripMs: number, evaluateMs: number) => ({ roundTripMs, evaluateMs, responseBytes: 100 });

  it("passes under the gate and fails over it", () => {
    expect(summarize([sample(20, 4), sample(30, 5)], 10).pass).toBe(true);
    expect(summarize([sample(GATE.roundTripMs + 1, 4)], 10).pass).toBe(false);
    expect(summarize([sample(20, GATE.evaluateMs + 1)], 10).pass).toBe(false);
  });
});

describe("applyTheme", () => {
  function fakeRoot() {
    const attrs = new Map<string, string>();
    return {
      attrs,
      setAttribute: (k: string, v: string) => void attrs.set(k, v),
      removeAttribute: (k: string) => void attrs.delete(k),
    };
  }

  it("sets data-theme for light and dark and clears it for system", () => {
    const root = fakeRoot();
    applyTheme("dark", root);
    expect(root.attrs.get("data-theme")).toBe("dark");
    applyTheme("light", root);
    expect(root.attrs.get("data-theme")).toBe("light");
    applyTheme("system", root);
    expect(root.attrs.has("data-theme")).toBe(false);
  });
});

describe("formatForSummary", () => {
  it("follows Excel-style formats and kind defaults", async () => {
    const { formatForSummary } = await import("./format");
    expect(formatForSummary(-12345678.5, "currency", "USD", "$#,##0")).toBe("-$12,345,679");
    expect(formatForSummary(0.143882568, "percent", null, "0.0%")).toBe("14.4%");
    expect(formatForSummary(146.832, "quantity", "kg", "#,##0.0")).toBe("146.8");
    expect(formatForSummary(0.4408, "percent", null)).toBe("44.1%");
    expect(formatForSummary(1234.5, "currency", "EUR")).toBe("1,235");
    expect(formatForSummary(true, "bool", null)).toBe("TRUE");
  });
});
