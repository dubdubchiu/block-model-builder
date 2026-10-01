# Block model builder

A browser-based, LabVIEW-style graphical modeling tool: typed function blocks wired into a system, evaluated, and exported as a summary worksheet. Full definition, architecture, and phases: `docs/PROJECT.md`. Keep that file current when scope or decisions change.

## Project rules

- The server does the heavy lifting: validation, evaluation, and export run in the Python engine (`engine/`, package `blockmodel`) behind the FastAPI app in `server/`. The browser is a thin client.
- Desktop is the editing target. Phone widths get a read-only view with no editing controls.
- Port types and coercion rules are defined in `docs/PROJECT.md` (Type system). The engine's pydantic models are the source of truth for `schemas/` and the TypeScript types.
- Block specs and model files are JSON and must validate against `schemas/`. A block spec references a registered `impl` key; it never contains code.
- Block type identity is `id@version`; each placed instance carries its own UUID.
- Cycles are allowed only through a Feedback block (`series.feedback`); reject any other cycle with an error that says how to fix it. Blocks with `causal: false` can't sit inside a loop.
- Illustrative inputs are marked as sample data in the UI; real figures carry their source.

## Development

- Python: `uv sync`, then `uv run pytest` and `uv run ruff format --check . && uv run ruff check .` from the repo root.
- Server: `uv run uvicorn app.main:app --app-dir server --port 8000`.
- Web (in `web/`): `npm run dev`, `npm run typecheck`, `npm test`, and `npm run e2e` (builds, starts both servers, runs Playwright, writes screenshots to `web/e2e-screens/`).
- After changing `engine/blockmodel/model.py` or `spec.py`: `uv run python -m blockmodel.schema`, then `npm run gen:types` in `web/`. Never edit `schemas/` or `types.gen.ts` by hand.
- Block specs are JSON files in `engine/blockmodel/library/specs/`; each names an `impl` registered in `engine/blockmodel/library/*.py`. Add or change both together; the loader fails on a spec without an impl or an impl without a spec.
- Block semantics must match the reference model's numpy evaluator (`models/reference/saas_company/generator/dsl.py`), which `engine/tests/test_blocks.py` uses as the oracle. After changing the library, type rules or importer, regenerate `models/examples/saas_company.json` (command in README).
- Deploy image: `docker build --build-arg BUILD_HASH=$(git rev-parse --short HEAD) -t block-model-builder .` (see README "Deploy"). A shared deployment must set `BM_AUTH_USER` and `BM_AUTH_PASSWORD`. Set `E2E_BASE_URL`, plus `E2E_USER` and `E2E_PASSWORD`, to run Playwright against a running server.
- Branches: work on `dev` or a session branch. `staging` (Render staging) changes only by merge, and `main` (Render production) only by fast-forward from `staging`. Never push to `staging` or `main` except for a promotion the user asked for. Render deploys both on every commit (`render.yaml`).
- `@playwright/test` is pinned to 1.56.1 to match the Chromium build preinstalled in the cloud container. Don't run `playwright install`.

## UI: Drafting Table design system

Every UI in this repo uses the Drafting Table design system. It replaces your default look. When a rule here conflicts with a habit, follow the rule.

- Source of truth: https://claude.ai/artifact/32tf4hbYaEZMTpZpZ6scwF (read its README before UI work if you can reach it)
- Working copy: `styles/drafting-table.css` and `styles/fonts/`. Import the stylesheet once at the app root. Do not edit it per feature; propose token changes instead.

### What this repo is

These apps are prototypes. A production team will rebuild them. Optimize for clarity and easy hand-off, not polish.

- Keep dependencies minimal. No UI component libraries (shadcn/ui, MUI, Chakra, Radix Themes, DaisyUI). Headless behavior libraries are fine if styled with `dt-` classes.
- If the app uses React or another framework, wrap the `dt-` classes in thin local components. Do not restyle them.
- If Tailwind is present, use it for layout only (flex, grid, gap, width). Colors, type, borders and radii come from the design system variables, never Tailwind's palette.

### Required on every app

- A `dt-titleblock` at the foot of the main view: Name, Rev, Date, Status `Prototype`, Owner, Data (`Stub`, `Sample` or `Live`), Build (short commit hash).
- A `dt-callout` on anything fake or unfinished: "Stub data", "Not wired", "Hard-coded".
- A `dt-placeholder` for any feature not built yet, instead of fake content or a dead button.
- Light theme by default, dark theme following the OS, and a manual toggle that sets `data-theme` on `<html>`.

### Styling rules

- Use tokens through CSS variables (`var(--ink)`, `var(--space-4)`). Never write raw hex, rgb, or pixel values that a token covers.
- Square corners everywhere (`--radius-none`). Circles only for radio buttons and callout leader dots.
- No box-shadow, no gradients, no blur or glass. The only pattern is hatching.
- Structure with lines: 1px `--stroke-hair` for dividers and control borders, 2px `--stroke-object` for the active panel and emphasis.
- Fill only the focal element. At most one `dt-btn--primary` per view.
- `--pencil` is the only accent: links (always underlined), focus ring, selection. Never a button fill or background.
- Status always has a word. Success is ink plus a word, never green.
- Never a colored left-edge accent on cards, rows or alerts.

### Type and content

- Body text 16px, nothing below 14px. Prose max width `--measure` (70ch). Left-aligned, never justified.
- Fonts: Atkinson Hyperlegible Next (`--font-sans`) for text, Atkinson Hyperlegible Mono (`--font-mono`) only for numbers, IDs, timestamps, code, and annotation labels. Never Inter, Roboto, Geist, or a bare system stack as the primary face.
- Uppercase only inside `dt-tag`, `dt-callout`, `dt-placeholder` and `dt-titleblock` labels. No uppercase eyebrow labels above headings.
- Sentence case everywhere else. Buttons are a verb and its object ("Export CSV"). No arrows appended to labels. No emoji. No middle-dot separators.
- Errors say what happened and how to fix it. Empty states name the absence and the action that fills it.
- Every control has a visible text label. Icons are optional helpers beside labels, single-weight line glyphs, never icon-only buttons.

### Accessibility floor

- Text contrast 4.5:1, control edges and focus ring 3:1, in both themes. The tokens already meet this; do not substitute colors.
- Visible keyboard focus on every interactive element (the stylesheet provides it; do not remove outlines).
- Motion only in response to an action, 120ms or less, and none under `prefers-reduced-motion`.

### Before you finish a UI change

Check it in both themes, at 375px and 1280px wide, with keyboard only. Confirm the title block is present and that stub data is marked.
