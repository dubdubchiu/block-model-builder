const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return numberFormat.format(value);
}

type Scalar = number | boolean | string;

export function formatValue(value: Scalar): string {
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return typeof value === "string" ? value : formatNumber(value);
}

/** A short preview of an output: a scalar, or the first values of a series and its length. */
export function previewOutput(output: Scalar | Scalar[]): string {
  if (!Array.isArray(output)) return formatValue(output);
  const values = output;
  const head = values.slice(0, 3).map(formatValue).join(", ");
  const more = values.length > 3 ? ", …" : "";
  return `${head}${more} (${values.length} periods)`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

export function formatMs(ms: number): string {
  return `${ms.toFixed(ms < 10 ? 2 : 1)} ms`;
}

/**
 * Formats a number for the summary: an Excel-style format when the report line has one
 * ("$#,##0", "0.0%", "#,##0.0"), otherwise a default by kind.
 */
export function formatForSummary(value: number | boolean | string, kind: string, unit: string | null | undefined, format?: string | null): string {
  if (typeof value !== "number") return formatValue(value);
  const spec = format ?? defaultFormat(kind, unit);
  const decimals = /\.(0+)/.exec(spec)?.[1].length ?? 0;
  const percent = spec.includes("%");
  const dollars = spec.startsWith("$");
  const n = percent ? value * 100 : value;
  const text = new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(n));
  const sign = n < 0 ? "-" : "";
  return `${sign}${dollars ? "$" : ""}${text}${percent ? "%" : ""}`;
}

function defaultFormat(kind: string, unit: string | null | undefined): string {
  switch (kind) {
    case "currency":
      return (unit ?? "USD").startsWith("USD") ? "$#,##0" : "#,##0";
    case "percent":
      return "0.0%";
    case "count":
    case "int":
      return "#,##0";
    case "quantity":
      return "#,##0.0";
    default:
      return "#,##0.00";
  }
}
