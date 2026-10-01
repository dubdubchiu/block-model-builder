/** Form fields that commit on Enter or blur, so typing doesn't flood undo history or the server. */
import { type ReactNode, useEffect, useId, useState } from "react";

interface CommitFieldProps {
  label: string;
  value: string;
  onCommit: (text: string) => string | undefined | void; // returns an error sentence to keep the draft
  help?: ReactNode;
  placeholder?: string;
  type?: "text" | "month";
  multiline?: boolean;
  mono?: boolean;
}

export function CommitField({ label, value, onCommit, help, placeholder, type = "text", multiline, mono }: CommitFieldProps) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string>();
  useEffect(() => {
    setDraft(value);
    setError(undefined);
  }, [value]);

  function commit() {
    if (draft === value) return;
    const problem = onCommit(draft);
    setError(problem || undefined);
  }

  const common = {
    id,
    className: mono ? "dt-input bm-mono" : "dt-input",
    value: draft,
    placeholder,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : help ? `${id}-help` : undefined,
    onChange: (e: { target: { value: string } }) => setDraft(e.target.value),
    onBlur: commit,
  };
  return (
    <div className={error ? "dt-field dt-field--error" : "dt-field"}>
      <label className="dt-field__label" htmlFor={id}>
        {label}
      </label>
      {multiline ? (
        <textarea {...common} rows={3} />
      ) : (
        <input
          {...common}
          type={type}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setDraft(value);
          }}
        />
      )}
      {help && !error && (
        <span className="dt-field__help" id={`${id}-help`}>
          {help}
        </span>
      )}
      {error && (
        <span className="dt-field__error" id={`${id}-error`}>
          {error}
        </span>
      )}
    </div>
  );
}

interface SelectFieldProps {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  help?: ReactNode;
}

export function SelectField({ label, value, options, onChange, help }: SelectFieldProps) {
  const id = useId();
  return (
    <div className="dt-field">
      <label className="dt-field__label" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="dt-input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {help && <span className="dt-field__help">{help}</span>}
    </div>
  );
}

/** Parses a number typed by a person: allows commas as thousands separators and a trailing %. */
export function parseNumber(text: string): number | undefined {
  const t = text.trim().replace(/,/g, "");
  if (!t) return undefined;
  const percent = t.endsWith("%");
  const n = Number(percent ? t.slice(0, -1) : t);
  if (!Number.isFinite(n)) return undefined;
  return percent ? n / 100 : n;
}
