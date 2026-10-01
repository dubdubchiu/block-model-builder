import { ReactFlowProvider } from "@xyflow/react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Canvas } from "./canvas/Canvas";
import { APP } from "./config";
import { Inspector } from "./editor/Inspector";
import { Palette } from "./editor/Palette";
import { Summary } from "./editor/Summary";
import { useShortcuts } from "./editor/shortcuts";
import { useEditor, useView } from "./editor/store";
import { Toolbar } from "./editor/Toolbar";
import { Callout, Notice } from "./shell/dt";
import { ThemeToggle } from "./shell/ThemeToggle";
import { TitleBlock } from "./shell/TitleBlock";
import { LatencyPanel } from "./spike/LatencyPanel";

const PHONE_QUERY = "(max-width: 40rem)";

function useIsPhone(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(PHONE_QUERY);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia(PHONE_QUERY).matches,
  );
}

const DEV_PAGE = new URLSearchParams(window.location.search).get("dev");

export function App() {
  const { model, loadError, init, leave } = useEditor();
  const view = useView();
  const isPhone = useIsPhone();
  const [tab, setTab] = useState<"diagram" | "summary">("diagram");
  useShortcuts(!isPhone);

  useEffect(() => {
    init();
  }, [init]);

  const sample = model?.blocks.some((b) => b.settings?.source === "illustrative");

  return (
    <div className="bm-app">
      <header className="bm-header">
        <h1 className="bm-header__title">{APP.name}</h1>
        <ThemeToggle />
      </header>

      <main className="bm-main">
        {DEV_PAGE === "latency" ? (
          <LatencyPanel />
        ) : (
          <ReactFlowProvider>
            {isPhone && <Notice>Editing is desktop only. On a phone you can open models, pan, zoom and read values.</Notice>}
            <Toolbar readOnly={isPhone} />
            {loadError && (
              <div className="bm-stack">
                <Notice tone="danger">{loadError}</Notice>
                <div>
                  <button type="button" className="dt-btn" onClick={init}>
                    Retry loading
                  </button>
                </div>
              </div>
            )}
            <div className="dt-tabs" role="tablist" aria-label="View">
              {(["diagram", "summary"] as const).map((t, i, all) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  id={`tab-${t}`}
                  className="dt-tab"
                  aria-selected={tab === t}
                  aria-controls={`panel-${t}`}
                  tabIndex={tab === t ? 0 : -1}
                  onClick={() => setTab(t)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                      const next = all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
                      setTab(next);
                      document.getElementById(`tab-${next}`)?.focus();
                    }
                  }}
                >
                  {t === "diagram" ? "Diagram" : "Summary"}
                </button>
              ))}
            </div>
            <div id="panel-diagram" role="tabpanel" aria-labelledby="tab-diagram" hidden={tab !== "diagram"}>
              <div className={isPhone ? "bm-workspace bm-workspace--phone" : "bm-workspace"}>
                {!isPhone && <Palette />}
                <section className="bm-center" aria-label="Diagram">
                  {view?.inside && (
                    <nav className="bm-breadcrumb" aria-label="Subsystem path">
                      <button type="button" className="dt-btn" onClick={leave}>
                        Back to model
                      </button>
                      <span>
                        {model?.name} / <strong>{view.inside.title}</strong>
                      </span>
                    </nav>
                  )}
                  <div className="bm-center__head">
                    <h2 className="text-heading">{view?.inside ? `Inside ${view.inside.title}` : (model?.name ?? "Loading model")}</h2>
                    {model && (
                      <span className="bm-meta">
                        {model.timeline.periods} periods, {model.timeline.frequency}ly from {model.timeline.start}
                      </span>
                    )}
                    {sample && <Callout label="Sample data" note="Blocks tagged Sample hold illustrative figures, not real data." side="left" />}
                  </div>
                  {model && <Canvas readOnly={isPhone} />}
                </section>
                <Inspector readOnly={isPhone} />
              </div>
            </div>
            <div id="panel-summary" role="tabpanel" aria-labelledby="tab-summary" hidden={tab !== "summary"}>
              <h2 className="text-heading">{model?.name ?? "Loading model"}</h2>
              <Summary readOnly={isPhone} />
            </div>
          </ReactFlowProvider>
        )}
      </main>

      <footer className="bm-footer">
        <TitleBlock data={sample ? "Sample" : "Live"} />
      </footer>
    </div>
  );
}
