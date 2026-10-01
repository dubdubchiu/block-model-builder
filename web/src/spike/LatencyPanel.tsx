import { useState } from "react";
import { api } from "../api/client";
import { formatBytes, formatMs } from "../lib/format";
import { GATE, type LatencySample, type LatencySummary, summarize } from "../lib/stats";
import { Notice, Panel } from "../shell/dt";

const BLOCKS = 250;
const PERIODS = 120;
const RUNS = 20;

export function LatencyPanel() {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [summary, setSummary] = useState<LatencySummary>();
  const [error, setError] = useState<string>();

  async function run() {
    setRunning(true);
    setError(undefined);
    setSummary(undefined);
    try {
      setProgress("Fetching the synthetic model");
      const model = (await api.synthetic(BLOCKS, PERIODS)).data;
      const body = JSON.stringify(model);
      await api.evaluate(body); // warm up
      const samples: LatencySample[] = [];
      for (let i = 1; i <= RUNS; i++) {
        setProgress(`Run ${i} of ${RUNS}`);
        const r = await api.evaluate(body);
        if (r.data.errors.length) throw new Error(`Evaluation returned errors: ${r.data.errors[0].message}`);
        samples.push({ roundTripMs: r.ms, evaluateMs: r.data.timing.evaluate_ms, responseBytes: r.responseBytes });
      }
      setSummary(summarize(samples, new TextEncoder().encode(body).length));
      setProgress("Done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setProgress("");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Panel title="Latency check" meta={`${BLOCKS} blocks by ${PERIODS} periods, ${RUNS} runs`}>
      <div className="bm-stack">
        <p className="dt-prose">
          Posts a synthetic model to the server and times each evaluation from this browser. On localhost this
          excludes network time. Gate: server evaluate under {GATE.evaluateMs} ms and round trip p50 under{" "}
          {GATE.roundTripMs} ms.
        </p>
        <div className="bm-row">
          <button type="button" className="dt-btn dt-btn--primary" onClick={run} disabled={running}>
            Run latency check
          </button>
          <span className="bm-status" aria-live="polite">
            {progress}
          </span>
        </div>
        {error && <Notice tone="danger">{error}</Notice>}
        {summary && (
          <table className="dt-table bm-latency" data-testid="latency-table">
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col" className="dt-num">
                  Value
                </th>
              </tr>
            </thead>
            <tbody>
              <Row metric="Request size" value={formatBytes(summary.requestBytes)} />
              <Row metric="Response size" value={formatBytes(summary.responseBytes)} />
              <Row metric="Server evaluate, p50" value={formatMs(summary.evaluateP50)} testId="evaluate-p50" />
              <Row metric="Round trip, p50" value={formatMs(summary.roundTripP50)} testId="round-trip-p50" />
              <Row metric="Round trip, p95" value={formatMs(summary.roundTripP95)} testId="round-trip-p95" />
              <tr>
                <td>Gate</td>
                <td className="dt-num">
                  <span className={summary.pass ? "dt-tag dt-tag--done" : "dt-tag dt-tag--danger"} data-testid="gate">
                    {summary.pass ? "Pass" : "Fail"}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  );
}

function Row({ metric, value, testId }: { metric: string; value: string; testId?: string }) {
  return (
    <tr>
      <td>{metric}</td>
      <td className="dt-num" data-testid={testId}>
        {value}
      </td>
    </tr>
  );
}
