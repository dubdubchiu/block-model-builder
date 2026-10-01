/**
 * Client-side port checks, mirroring `Pattern.check` in engine/blockmodel/types.py.
 * Only the checks the editor needs at drag time: shape (single value vs per period) and kind.
 * The server stays the authority; it re-checks every wire on evaluation.
 */

export type KindGroups = Record<string, string[]>;

export interface ParsedType {
  shape: "scalar" | "series" | "annual";
  kind: string;
}

const SHAPES = new Set(["scalar", "series", "annual"]);

export function parseType(text: string): ParsedType {
  const m = /^(\w+)<(\w+)>$/.exec(text.trim());
  if (m && SHAPES.has(m[1])) return { shape: m[1] as ParsedType["shape"], kind: m[2] };
  return { shape: "scalar", kind: text.trim() };
}

interface Pattern {
  scalarOnly: boolean;
  kinds: string[] | null; // null: an output pattern word we can't check against (e.g. "number" on an unevaluated block)
}

function parsePattern(text: string, groups: KindGroups): Pattern {
  const m = /^(\w+)<(\w+)>$/.exec(text.trim());
  const inner = m ? m[2] : text.trim();
  const scalarOnly = m?.[1] === "scalar";
  if (inner in groups) return { scalarOnly, kinds: groups[inner] };
  return { scalarOnly, kinds: [inner] };
}

/**
 * Can a wire carrying `sourceType` go into a port with `pattern`? Returns null when it can,
 * or a sentence saying why not. `sourceType` may itself be a pattern (before the first evaluation);
 * then only definite mismatches are refused.
 */
export function refuseReason(port: string, pattern: string, sourceType: string, groups: KindGroups): string | null {
  const accepts = parsePattern(pattern, groups);
  const source = parseType(sourceType);
  if (accepts.scalarOnly && source.shape !== "scalar") {
    return `Input ${port} takes a single value, but this output has per-period values.`;
  }
  const sourceKinds = source.kind in groups ? groups[source.kind] : [source.kind];
  if (accepts.kinds && !sourceKinds.some((k) => accepts.kinds!.includes(k))) {
    if (sourceKinds.every((k) => k === "bool")) {
      return `Input ${port} needs a number, but this output is TRUE/FALSE. Use an If block instead.`;
    }
    const kindWord = pattern.includes("integer") ? "a whole number (int or count)" : pattern;
    return `Input ${port} expects ${kindWord}, but this output is ${sourceType}.`;
  }
  return null;
}
