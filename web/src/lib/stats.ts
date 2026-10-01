/** Nearest-rank percentile; p in (0, 100]. */
export function percentile(values: number[], p: number): number {
  if (values.length === 0) throw new Error("percentile of an empty list");
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.ceil((p / 100) * sorted.length);
  return sorted[Math.min(sorted.length, Math.max(1, rank)) - 1];
}

export interface LatencySample {
  roundTripMs: number;
  evaluateMs: number;
  responseBytes: number;
}

export interface LatencySummary {
  runs: number;
  requestBytes: number;
  responseBytes: number;
  evaluateP50: number;
  roundTripP50: number;
  roundTripP95: number;
  pass: boolean;
}

/** Phase 0 gate on localhost: server evaluate under 50 ms, round trip p50 under 150 ms. */
export const GATE = { evaluateMs: 50, roundTripMs: 150 } as const;

export function summarize(samples: LatencySample[], requestBytes: number): LatencySummary {
  const evaluateP50 = percentile(
    samples.map((s) => s.evaluateMs),
    50,
  );
  const roundTripP50 = percentile(
    samples.map((s) => s.roundTripMs),
    50,
  );
  return {
    runs: samples.length,
    requestBytes,
    responseBytes: samples[samples.length - 1].responseBytes,
    evaluateP50,
    roundTripP50,
    roundTripP95: percentile(
      samples.map((s) => s.roundTripMs),
      95,
    ),
    pass: evaluateP50 < GATE.evaluateMs && roundTripP50 < GATE.roundTripMs,
  };
}
