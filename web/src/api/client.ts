import type { CompositeSpec as Composite, EvaluateResponse, LibraryResponse, Model } from "./types.gen";

export interface ModelSummary {
  id: string;
  name: string;
  blocks: number;
  updated: string;
}

export const SERVER_HINT = "Start it from the repo root with: uv run uvicorn app.main:app --app-dir server --port 8000";

export class ApiError extends Error {}

export interface Timed<T> {
  data: T;
  /** Wall time from sending the request to having the parsed body. */
  ms: number;
  responseBytes: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<Timed<T>> {
  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(`Couldn't reach the server. ${SERVER_HINT}`);
  }
  const text = await response.text();
  if (response.status === 502 || response.status === 504) {
    throw new ApiError(`The server isn't running. ${SERVER_HINT}`);
  }
  if (!response.ok) {
    let detail = text;
    try {
      detail = JSON.stringify(JSON.parse(text).detail);
    } catch {
      // Keep the raw text.
    }
    throw new ApiError(`The server returned ${response.status} for ${path}: ${detail}`);
  }
  const data = JSON.parse(text) as T;
  return { data, ms: performance.now() - started, responseBytes: new TextEncoder().encode(text).length };
}

/** A file from the server: the blob and the server's suggested file name. */
async function fetchFile(path: string, fallbackName: string, init?: RequestInit): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(`Couldn't reach the server. ${SERVER_HINT}`);
  }
  if (!response.ok) {
    let detail = await response.text();
    try {
      detail = JSON.parse(detail).detail;
    } catch {
      // Keep the raw text.
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  return { blob: await response.blob(), filename };
}

export const api = {
  library: () => request<LibraryResponse>("/api/library"),
  example: (name: string) => request<Model>(`/api/examples/${encodeURIComponent(name)}`),
  synthetic: (blocks: number, periods: number) =>
    request<Model>(`/api/dev/synthetic?blocks=${blocks}&periods=${periods}`),
  /** Pass a pre-serialized body to keep serialization out of repeated timings. */
  evaluate: (model: Model | string, values: string[] | "all" | "none" = "all", scenario?: string) =>
    request<EvaluateResponse>(
      `/api/evaluate?values=${Array.isArray(values) ? values.join(",") || "none" : values}${scenario ? `&scenario=${encodeURIComponent(scenario)}` : ""}`,
      {
      method: "POST",
      headers: { "Content-Type": "application/json" },
        body: typeof model === "string" ? model : JSON.stringify(model),
      },
    ),
  validate: (model: unknown) =>
    request<EvaluateResponse>("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(model),
    }),
  /** The summary as a file: returns the blob and the server's suggested file name. */
  exportFile: (model: Model, format: "csv" | "xlsx", scenario?: string) =>
    fetchFile(`/api/export?format=${format}${scenario ? `&scenario=${encodeURIComponent(scenario)}` : ""}`, `model.${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(model),
    }),
  /** Every saved model and block as one zip file. */
  backup: () => fetchFile("/api/backup", "block-model-builder-backup.zip"),
  models: () => request<ModelSummary[]>("/api/models"),
  blocks: () => request<Composite[]>("/api/blocks"),
  saveBlock: (spec: Composite) =>
    request<Composite>(`/api/blocks/${encodeURIComponent(spec.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    }),
  model: (id: string) => request<Model>(`/api/models/${encodeURIComponent(id)}`),
  saveModel: (model: Model) =>
    request<ModelSummary>(`/api/models/${encodeURIComponent(model.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(model),
    }),
};
