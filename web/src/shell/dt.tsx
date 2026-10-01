/** Thin wrappers over Drafting Table classes. Structure only; all styling comes from the stylesheet. */
import type { ReactNode } from "react";

export function Callout({ label, note, side = "right" }: { label: string; note?: string; side?: "left" | "right" }) {
  const classes = ["dt-callout", side === "left" && "dt-callout--left", note && "dt-callout--noted"]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes}>
      <span>
        <span className="dt-callout__label">{label}</span>
        {note && <span className="dt-callout__note">{note}</span>}
      </span>
      <span className="dt-callout__leader" aria-hidden="true" />
    </span>
  );
}

export function Placeholder({ label, note }: { label: string; note: string }) {
  return (
    <div className="dt-placeholder">
      <span className="dt-placeholder__label">{label}</span>
      <span className="dt-placeholder__note">{note}</span>
    </div>
  );
}

export function Panel({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section className="dt-panel">
      <div className="dt-panel__head">
        <h2 className="dt-panel__title">{title}</h2>
        {meta && <span className="dt-panel__meta">{meta}</span>}
      </div>
      <div className="dt-panel__body">{children}</div>
    </section>
  );
}

export function Notice({ children, tone }: { children: ReactNode; tone?: "danger" | "caution" }) {
  return (
    <div className={tone ? `dt-notice dt-notice--${tone}` : "dt-notice"} role={tone === "danger" ? "alert" : undefined}>
      <p className="dt-notice__text">{children}</p>
    </div>
  );
}
