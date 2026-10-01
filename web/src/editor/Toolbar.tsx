import { useRef, useState } from "react";
import { type ModelSummary, api } from "../api/client";
import type { Model } from "../api/types.gen";
import { saveBlob } from "../lib/download";
import { SelectField } from "./fields";
import { addScenario, blankModel } from "./graph";
import { useEditor } from "./store";

const EXAMPLES = [
  { name: "demo", title: "Demo: price times units plus other income" },
  { name: "saas_company", title: "Reference model: SaaS company (161 blocks, 4 scenarios)" },
  { name: "cash_interest", title: "Interest on the cash balance (a feedback loop)" },
];

function confirmDiscard(): boolean {
  return !useEditor.getState().dirty || window.confirm("Discard unsaved changes to this model?");
}

function download(filename: string, text: string) {
  saveBlob(new Blob([text], { type: "application/json" }), filename);
}

export function fileName(model: Model, ext: string): string {
  return `${model.name.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "model"}.${ext}`;
}

export function Toolbar({ readOnly }: { readOnly: boolean }) {
  const { model, dirty, savedOnServer, computing, evalError, result, past, future, scenario } = useEditor();
  const { loadModel, save, undo, redo, say, applyTop, setScenario } = useEditor.getState();
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [saved, setSaved] = useState<ModelSummary[]>();
  const [listError, setListError] = useState<string>();
  const [backupState, setBackupState] = useState<{ text: string; tone?: "danger" }>();

  async function openDialog() {
    setListError(undefined);
    setBackupState(undefined);
    dialog.current?.showModal();
    try {
      setSaved((await api.models()).data);
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    }
  }

  async function downloadBackup() {
    setBackupState({ text: "Preparing the backup" });
    try {
      const { blob, filename } = await api.backup();
      saveBlob(blob, filename);
      setBackupState({ text: `Downloaded ${filename}.` });
    } catch (e) {
      setBackupState({ text: `Couldn't export the models: ${e instanceof Error ? e.message : String(e)}`, tone: "danger" });
    }
  }

  async function open(load: () => Promise<{ data: Model }>, savedOnServer: boolean) {
    if (!confirmDiscard()) return;
    try {
      loadModel((await load()).data, { savedOnServer });
      dialog.current?.close();
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    }
  }

  async function importFile(file: File) {
    if (!confirmDiscard()) return;
    let data: unknown;
    try {
      data = JSON.parse(await file.text());
    } catch {
      say(`${file.name} isn't valid JSON. Export a model from this app, or check the file.`, "danger");
      return;
    }
    try {
      await api.validate(data);
      loadModel(data as Model);
      say(`Imported ${file.name}. Save it to keep it on the server.`);
    } catch (e) {
      say(`${file.name} isn't a valid model: ${e instanceof Error ? e.message : String(e)}`, "danger");
    }
  }

  const errorCount = result?.errors.length ?? 0;
  const warningCount = result?.warnings?.length ?? 0;
  const scenarios = model?.scenarios ?? [];
  const saveState = dirty ? "Unsaved changes" : savedOnServer ? "Saved" : "Not saved";
  const computeState = evalError ? "Evaluation failed" : computing ? "Computing" : "Up to date";

  return (
    <div className="bm-toolbar">
      <div className="bm-row bm-row--tight">
        <button type="button" className="dt-btn" onClick={openDialog}>
          Open model
        </button>
        {!readOnly && (
          <>
            <button type="button" className="dt-btn" onClick={() => confirmDiscard() && loadModel(blankModel())}>
              New model
            </button>
            <button type="button" className="dt-btn dt-btn--primary" onClick={save} disabled={!model}>
              Save model
            </button>
            <button type="button" className="dt-btn" onClick={() => fileInput.current?.click()}>
              Import JSON
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".json,application/json"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) importFile(file);
              }}
            />
            <button
              type="button"
              className="dt-btn"
              disabled={!model}
              onClick={() => model && download(fileName(model, "json"), JSON.stringify(model, null, 1))}
            >
              Export JSON
            </button>
            <button type="button" className="dt-btn" onClick={undo} disabled={!past.length}>
              Undo
            </button>
            <button type="button" className="dt-btn" onClick={redo} disabled={!future.length}>
              Redo
            </button>
          </>
        )}
      </div>
      <div className="bm-row bm-row--tight bm-row--end">
        <SelectField
          label="Scenario"
          value={scenario ?? ""}
          options={[{ value: "", label: "Base case" }, ...scenarios.map((sc) => ({ value: sc.id, label: sc.name }))]}
          onChange={(v) => setScenario(v || undefined)}
        />
        {!readOnly && (
          <button
            type="button"
            className="dt-btn"
            disabled={!model}
            onClick={() => {
              let id = "";
              applyTop((m) => {
                const out = addScenario(m, `Scenario ${(m.scenarios?.length ?? 0) + 1}`);
                id = out.id;
                return out.model;
              });
              setScenario(id);
              say("Added a scenario. Values you change now apply only to it; rename it in the Model panel.");
            }}
          >
            New scenario
          </button>
        )}
      </div>
      <p className="bm-toolbar__state" aria-live="polite">
        {!readOnly && <span className="dt-tag">{saveState}</span>}{" "}
        <span className={evalError ? "dt-tag dt-tag--danger" : "dt-tag"} data-testid="compute-state">
          {computeState}
        </span>{" "}
        {errorCount > 0 && (
          <span className="dt-tag dt-tag--danger">
            {errorCount} {errorCount === 1 ? "error" : "errors"}
          </span>
        )}{" "}
        {warningCount > 0 && (
          <span className="dt-tag dt-tag--caution">
            {warningCount} {warningCount === 1 ? "warning" : "warnings"}
          </span>
        )}
      </p>
      {evalError && <p className="bm-status bm-status--danger">{evalError}</p>}

      <dialog ref={dialog} className="dt-panel bm-dialog" aria-labelledby="open-title">
        <div className="dt-panel__head">
          <h2 className="dt-panel__title" id="open-title">
            Open model
          </h2>
          <button type="button" className="dt-btn dt-btn--quiet" onClick={() => dialog.current?.close()}>
            Close
          </button>
        </div>
        <div className="dt-panel__body bm-stack">
          <h3 className="bm-subhead">Examples</h3>
          <ul className="bm-list">
            {EXAMPLES.map((ex) => (
              <li key={ex.name} className="bm-list__item">
                <span>{ex.title}</span>
                <button type="button" className="dt-btn" onClick={() => open(() => api.example(ex.name), false)}>
                  Open example
                </button>
              </li>
            ))}
          </ul>
          <h3 className="bm-subhead">Saved models</h3>
          <p className="bm-status">
            Export all models downloads one zip file with every saved model and saved block on this server, as a backup. To
            restore a model, choose Import JSON and pick its file from the zip.
          </p>
          <div>
            <button type="button" className="dt-btn" onClick={downloadBackup}>
              Export all models
            </button>
          </div>
          {backupState && (
            <p className={`bm-status${backupState.tone ? " bm-status--danger" : ""}`} aria-live="polite">
              {backupState.text}
            </p>
          )}
          {listError && <p className="bm-status bm-status--danger">{listError}</p>}
          {saved && saved.length === 0 && <p className="bm-status">No saved models yet. Save a model to see it here.</p>}
          {saved && saved.length > 0 && (
            <ul className="bm-list">
              {saved.map((m) => (
                <li key={m.id} className="bm-list__item">
                  <span>
                    {m.name} <span className="bm-small">{m.blocks} blocks, saved {new Date(m.updated).toLocaleString()}</span>
                  </span>
                  <button type="button" className="dt-btn" onClick={() => open(() => api.model(m.id), true)}>
                    Open model
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </dialog>
    </div>
  );
}
