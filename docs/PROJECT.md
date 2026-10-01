# Block model builder: project definition

## Context

The goal is a browser-based, LabVIEW-style modeling tool built on the financial modeling work: typed function blocks with UUIDs, wired into a system, evaluated, and exported as a summary worksheet. The Drafting Table kit (`CLAUDE.md`, `styles/drafting-table.css`, Atkinson Hyperlegible fonts) sets the UI rules: no component libraries, square corners, no color beyond `--pencil`, title block and stub callouts required, light/dark themes.

Decisions made:
- Engine: Python on the server. The server does validation, evaluation, and export; the browser is a thin client.
- Devices: desktop for editing; phones get a read-only view.
- Wire types: Python-friendly scalars, common financial model types, and first-class period series.
- Block logic v1: built-in library only.
- Acceptance model: a generic SaaS company, quarterly for eight years; see "Reference model" below.

## Design decisions and trade-offs

1. **Server-side evaluation.** Every edit that changes a value goes to the server, debounced (about 300ms), with a visible "Computing" state. Cost: a network round-trip per recompute and no offline editing. Benefit: full CPython ecosystem (numpy, XlsxWriter, pydantic), one place for integrations and a database later, and a light client. Model sizes (tens to low hundreds of blocks, up to about 120 periods) keep each evaluation well under network latency.
2. **Desktop editing, phone viewing.** The editor targets 1280px and up. At phone widths the app shows a read-only view: model list, pan/zoom diagram, and the summary table. No editing controls render on phones.
3. **Server-side model storage from v1.** A phone can only view what the server can serve, so models are saved on the server (JSON files in a data directory behind list/get/save endpoints). A database replaces this later without changing the API. Import and export of model JSON files stays available on desktop. There is no real auth yet. Until there is, a shared deployment must turn on the shared-password gate (HTTP basic auth from `BM_AUTH_USER` and `BM_AUTH_PASSWORD`, behind HTTPS); local development runs without it.
4. **Money as float64.** Same as Excel; fine for modeling. `Decimal` adds cost and complexity for no modeling benefit.
5. **UUID belongs to the instance, not the block type.** A block *spec* (e.g. `finance.npv@1`) is a reusable JSON definition; each placed *instance* has its own UUID, inline input values, settings, and position. Both are JSON.
6. **Circular references** (e.g. interest on cash balance) are allowed only through a Feedback block (Phase 4), whose output in period t is its input in period t-1, like LabVIEW's feedback node.
   - The evaluator solves loops by iterating until the Feedback outputs stop changing, which is exact after at most one pass per period.
   - Blocks that use every period at once (Total, NPV, IRR, Aggregate to year; spec `causal: false`) can't sit inside a loop.
   - Any other cycle is an error that says to insert Feedback, Lag or Accumulate.
7. **Phase 4 choices** (approved 2026-09-28):
   - the `table` type became a Lookup block;
   - the `enum` type was dropped in favour of model-level scenarios;
   - unit mismatches are warnings, not errors;
   - cycles are allowed through Feedback only.

## Type system

Every port has a type. Types drive wire validation in the editor, number formatting in tables and exports, and simple consistency checks in the engine.

| Type | Python value | Use | Display |
|---|---|---|---|
| `float` | `float` | generic number, ratio | `1,234.56` |
| `int` | `int` | whole number | `1,234` |
| `bool` | `bool` | flags, conditions | `TRUE` / `FALSE` |
| `str` | `str` | labels, names | text |
| `date` | `datetime.date` | milestones, timeline dates | `2027-03-31` |
| `currency` | `float` + ISO code (default `USD`) | money | `$1,234,567` |
| `percent` | `float` stored as a fraction (0.15) | rates, yields, margins | `15.0%` |
| `quantity` | `float` + unit label (`kg`, `USD/kg`) | physical and per-unit amounts | `1,234.5 kg` |
| `count` | `int` + unit label (`orders`) | discrete things | `12 orders` |
| `series<T>` | array of T, one per period | any of the scalar types above over the model timeline | row of values |
| `annual<T>` | array of T, one per fiscal year | output of Aggregate to year | row of values |

Lookup tables are a block (`lookup.table`), not a wire type; scenario selection is model-level (see Scenarios), so there is no `enum` type.

Rules in v1. The numeric kinds are `int`, `float`, `count`, `quantity`, `percent`, and `currency`.
- **Broadcast:** a scalar wired into a series input is broadcast across all periods. A block's result is per period if any input is; all-scalar inputs give a scalar. `series<T>` and `annual<T>` cannot be mixed in one block.
- **Add, Subtract, Min, Max:** the same kind in gives the same kind out. `currency` needs `currency` with the same ISO code on both sides; mixing currency with any other kind is an error that says to use a currency Constant. Other mixed kinds give `float`.
- **Multiply:**
  - `currency` times any non-currency kind gives `currency`; `currency` times `currency` is an error.
  - `percent` times `percent` gives `percent`.
  - Any kind X times `percent` gives X, except `count` times `percent`, which gives `quantity`.
  - `count` times `quantity` gives `quantity`; `count` times `count` gives `count`.
  - Everything else gives `float`.
- **Divide:** `currency` over `currency` gives `float`. `currency` over a non-currency kind gives `currency` with a derived unit label (`USD/kg`, `USD/order`), which covers cost per kg and cost per order. Everything else gives `float`. Per-unit prices are typed `currency` with a label such as `USD/kg`, so `kg` times `USD/kg` stays money.
- **Inline literals** (unwired input ports):
  - in Add, Subtract, Min, Max, Compare, If branches, Safe divide's fallback and Accumulate's opening, a literal adopts the kind of the other operand, as in Excel (`revenue + 150` stays currency);
  - in Multiply and Divide, a literal is a plain factor and the result keeps the wired side's type (`2 * price` stays currency; a literal numerator, `1 / x`, gives float);
  - elsewhere a literal is a float, or an int on a whole-number port.
- **Retype** (`display_kind`, `display_unit` in a block's settings): changes the output's type for display and for downstream rules.
  - Allowed between non-currency number kinds; `count` needs whole-number values.
  - A unit relabel is allowed on any kind.
  - Nothing converts into or out of `currency`.
  - This is how `gross_profit / revenue_total` becomes a percent, and how a ceiling's `int` becomes a `count` of seats.
- **Rounding and windows:** Ceiling and Round keep the kind and make values integral (`float` becomes `int`). Lag, Accumulate, Running max and Total keep the kind. NPV keeps the kind of its cash flow; IRR gives `percent`; Discount factor and Power give `float`.
- **Comparisons** give `bool`. A `bool` in arithmetic is an error that says to use If (e.g. `if(flag, x, 0)`, not `x * flag`).
- **Units** combine like dimensions:
  - `USD/kg` times `kg` gives `USD`; `USD` over `order` gives `USD/order`; `seats` times `USD/order` gives `USD*seats/order`.
  - Names match without a plural s (`orders` cancels `order`).
  - Mismatched units in Add, Subtract, Min, Max, Compare and If are warnings ("Check units"), not errors, so models with loose labels still evaluate. The reference model has 10.
  - Currency-code mismatches stay errors.

**Port patterns** in block specs say what an input accepts:
- `number` (any numeric kind, scalar or per period);
- `scalar<number>`, or `scalar<integer>` (int or count);
- `bool`, `any`, or a concrete type.

Output patterns document the result's shape; the engine returns each output's inferred type after evaluation. `/api/library` returns the kind groups (`number`, `integer`) so the editor can check wires without copying the rules.

## Architecture

```
CLAUDE.md                 project rules + Drafting Table rules (from kit)
styles/                   kit stylesheet and fonts, unmodified
engine/                   Python package `blockmodel` (3.12+; numpy, pydantic v2; XlsxWriter in Phase 3)
  blockmodel/types.py       types, port patterns, and the rules above
  blockmodel/model.py       Model, BlockInstance, Wire, and the evaluate response (pydantic)
  blockmodel/spec.py        BlockSpec (pydantic)
  blockmodel/timeline.py    period dates, labels, fiscal years
  blockmodel/evaluate.py    wire checks, cycle detection, per-block inference and compute, errors
  blockmodel/library/       specs/<id>.json (29 files) + registered implementations by category
  blockmodel/builder.py     programmatic models: ModelBuilder, deterministic ids, layered layout
  blockmodel/importers/     formula parser; row importer for the reference model format
  blockmodel/export.py      summary table, CSV, XLSX (Phase 3)
  tests/                    pytest; oracle.py loads the reference model's numpy evaluator
server/                   FastAPI app wrapping the engine
  app/main.py               GET /api/library; POST /api/evaluate?values=all|none|<uuids>, /api/validate;
                            GET /api/models, GET/PUT /api/models/{id}; POST /api/export (Phase 3); GET /api/backup
  app/storage.py            JSON files under data/models/ or BM_DATA_DIR (database later, same interface)
  tests/                    API tests with the FastAPI test client
schemas/                  JSON Schema generated from the pydantic models; TS types generated from it
web/                      Vite + React + TypeScript, thin client
  src/canvas/               @xyflow/react (headless behavior), custom node styled with dt- classes
  src/palette/, src/inspector/, src/report/, src/viewer/ (phone read-only view)
  src/api/                  typed client for the server API
models/examples/          demo.json; saas_company.json (generated by the row importer)
docs/PROJECT.md           this definition, kept current
```

The pydantic models are the single source of truth: they generate `schemas/`, which generates the TypeScript types. The client fetches block specs and the type compatibility table from `/api/library`, so wiring checks in the editor match the engine without duplicating rules by hand.

Dependencies:
- Web: React, `@xyflow/react` (base.css only, all visuals from dt- tokens), `zustand`.
- Server: FastAPI, uvicorn, plus the engine's. Responses are gzipped at level 1.
- Dev: Vitest, Playwright, pytest, ruff; scipy and openpyxl only so tests can run the reference model's numpy evaluator as an oracle.

## Data model (JSON)

**Block spec** (one file per type, `engine/blockmodel/library/specs/<id>.json`): `id`, `version`, `title`, `category`, `doc`, `inputs[] {name, type (pattern), required, inline, doc}`, `settings[] {name, type, default, options, doc}`, `outputs[] {name, type}`, `impl` (registered function key, never code). An optional input with no inline value is skipped when unwired (Sum's `in1..in8`).

Every scalar parameter is an input port, LabVIEW style. Unwired, it takes an inline value set in the inspector (the spec's `inline` is the default); wired, it takes the wire. So Lag's `n` can come from a driver, and formula literals fold into the block instead of needing their own Constant blocks. `settings` holds the few values that are never wired:
- Constant: `value`, `kind`, `unit`.
- Series input: `values`, `kind`, `unit`.
- Both: `source` (a URL with access date, or `illustrative`) and `notes`.
- Compare: `op`.
- Any single-output block: `display_kind` and `display_unit` (retype).

**Model file**: `schemaVersion`, `id` (UUID), `name`, `timeline {start, frequency: month|quarter|year, periods, fiscal_year_end}`, `blocks[] {uuid, spec: "id@version", label, inline {port: value}, settings, position}`, `wires[] {uuid, from {block, port}, to {block, port}}`, `report[] {block, port, label, format}`.

**Timeline:**
- `start` must be the first day of a month; periods step by 1, 3 or 12 months.
- A period's fiscal year is the year in which its fiscal year ends (`fiscal_year_end`, default `12-31`).
- Period labels look like `2027-01`, `2027Q1` or `2027`.

**Evaluate response:**
- `outputs[block][port] = {type, unit, value}`;
- `timeline {period_labels, years}`;
- `errors[] {block, message}`, where block is null for model-level errors such as a cycle;
- `timing`.

`values` is null for blocks that weren't requested (`?values=`) and everywhere in `/api/validate`.

## Editor behavior (desktop)

- Palette by category; drag onto canvas. Ports show name and type in mono annotation style.
- Wiring is refused when types are incompatible or a wire would form a loop. The reason appears in a status line under the canvas, which is announced to screen readers.
- Wire styling follows LabVIEW's convention, without color: scalar 1px, series 2px, bool dashed. Selection uses `--pencil`.
- Inspector:
  - label and UUID (copyable);
  - for each input, a "Wire from" select (the keyboard path to wiring) or an inline value;
  - settings from the spec; retype; outputs with a per-period values table; the block's error.
  - With nothing selected, it shows the model name and timeline.
- Find block: type a label to select a block and center it (needed at the reference model's 161 blocks).
- Debounced recompute on the server (300 ms), with stale responses dropped; errors shown as a `dt-tag--danger` on the block with a sentence saying what to fix. If the server is unreachable, the editor says so and keeps local edits. Models of 80 or more blocks request values only for on-screen, selected and report blocks (`?values=`).
- Undo/redo (snapshot stack), multi-select, delete, copy/paste, keyboard shortcuts, keyboard-reachable inspector.
- Save and open models on the server; import and export model JSON files; import block spec JSON (validated; must reference a registered `impl`).
- Summary tab: `dt-table`s of report rows (per period, per fiscal year, single values) with a sticky label column, formatted by the row's Excel-style format or by kind.
  - "Add to summary" and "Remove from summary" on each output in the inspector; rename, Move up, Move down and Remove row under "Edit summary rows".
  - Export CSV and Export XLSX are generated on the server (`engine/blockmodel/export.py`, `POST /api/export?format=csv|xlsx`). The XLSX has three sheets:
    - Summary, with the row formats and frozen headers;
    - Assumptions: every Constant and Series input with kind, unit, source and notes;
    - Blocks: uuid, label, block, output, type, unit, error.
  - Values only in v1. An empty summary gives an error that says how to add rows.
- Title block (Data reads Sample when any input is illustrative), theme toggle, `dt-placeholder` for unbuilt features. Constant and Series input blocks carry a Sample or Sourced tag from their `source` setting.
- The Phase 0 latency check lives at `/?dev=latency`; the e2e suite runs it against the gate.

## Phone view (read-only)

Model list, pan/zoom diagram without editing handles, block details on tap, and the summary table with horizontal scroll inside the table only. Checked at 375px.

**Programmatic path**: the engine is a normal Python package, so `pip install -e engine` lets you build, evaluate, and save models from scripts or notebooks, then open them in the editor. `blockmodel.ModelBuilder` adds blocks by id with handles or literals as inputs. `blockmodel.importers.rows.FormulaBuilder` turns formulas such as `safe_divide(cost, orders, 0)` into blocks. This covers "importing blocks or something more programmatic" in v1.

## Built-in library (31 blocks)

- Sources:
  - `source.constant`, `source.series`;
  - `source.timeline`, with outputs `t`, `period_start`, `period_end`, `year`, `fiscal_year` and `periods`;
  - `source.growth`, `source.step`, `source.flag`, `source.spread`.
- Math: `math.add`, `subtract`, `multiply`, `divide`, `safe_divide` (a, b, fallback), `power`, `min`, `max`, `ceiling`, `round` (x, digits), `sum` (up to 8 inputs).
- Series: `series.accumulate` (x, opening), `lag` (x, n; n wirable), `running_max`, `total`, `annual` (Aggregate to year).
- Finance: `finance.discount_factor`, `npv` (rate, cash_flow), `irr` (cash_flow, optional guess), `depreciation_sl` (capex, life).
- Logic: `logic.compare` (`op` setting: `> >= < <= == !=`), `logic.if` (condition, then, else).
- Phase 4:
  - `series.feedback` (x, initial; kind and unit settings when initial is typed in);
  - `lookup.table` (x; settings keys, values, mode `step` or `linear`, kind, unit; clamped at the ends).

### Semantics

These match the reference model's workbook and its numpy evaluator (`models/reference/saas_company/generator/dsl.py`), which serves as the oracle for per-block tests.

- **Periods** are numbered `t = 1..N`. Growth is `start * (1 + rate)^(t - 1)`. Step is `value` when `t >= from_period`, else 0. Period flag is `start <= t <= end`. Spread is `amount / n` for `start <= t < start + n`, else 0.
- **Rates are per period.** NPV, Discount factor and IRR take and return per-period (here quarterly) rates. Annual conversion is explicit: `pow(1 + annual, 0.25) - 1`.
- **NPV** discounts period t by `(1 + rate)^t` with t from 1, like Excel's NPV (valued at the start of period 1). numpy-financial's `npv` discounts the first value at t = 0 and differs by a factor of `(1 + rate)`. Discount factor is `1 / (1 + rate)^t`.
- **IRR** uses a bracketing solver: it scans (-0.99, 10] for sign changes, on a grid dense between -20% and 100%, and refines by bisection, with no Newton step. The optional `guess` only picks which root to return when there are several, taking the one nearest the guess. With no sign change, IRR returns an error that says the cash flow needs both signs. Spreadsheet Newton from 0.1 diverges on the reference model's profile; this solver doesn't.
- **Divide** is strict: a zero denominator in any period is a block error that names the period and points to Safe divide. Safe divide returns `fallback` where the denominator is 0. If evaluates both branches, so `if(b > 0, a / b, 0)` is not a substitute.
- **Lag** fills the first n periods with 0.
- **Accumulate** is `opening + running sum`. **Running max** is the running maximum.
- **Straight-line depreciation** spreads each period's capex evenly over `life` periods, starting in the period it is spent (vintages). This equals `(cumulative(capex) - lag(cumulative(capex), life)) / life`.
- **Round** rounds half away from zero, like Excel (Python and numpy round half to even).
- **Ceiling** snaps values within 1e-9 relative of an integer to that integer before rounding up, so float noise in a quotient that should be exact doesn't add one.
- **Aggregate to year** sums each fiscal year's periods into `annual<T>`.
- **Any non-finite result** (for example Power of a negative base) is a block error that names the first bad period.

## Scenarios and subsystems (Phase 4)

**Scenarios:**
- Data: `Model.scenarios[] {id, name, overrides[] {block, inline, settings}}`.
- Overrides apply to top-level blocks only. `evaluate` and `export` take `?scenario=`; an unknown id is a 422 that lists the model's scenarios.
- Editor:
  - a Scenario select and New scenario in the toolbar;
  - while a scenario is active, value edits (Constant value, Series values, Lookup keys and values, inline inputs) go to that scenario and are marked Overridden, with "Use base value" to clear them;
  - wiring and labels always edit the base model;
  - the Summary can compare with another scenario (single values and the last period, with the difference).
- The reference import adds Low and High scenarios for quarterly churn and monthly ARPA. Base NPV is $51.2M; high churn takes it to $13.0M and low ARPA to $1.5M.

**Subsystems** (composite blocks, like a LabVIEW subVI):
- Data: `Model.composites[] {id user.<name>, version, title, inputs[] {name, type, targets[]}, outputs[] {name, source}, blocks, wires}`. An instance's spec is `user.<name>@1`.
- The engine flattens instances before evaluating, deriving inner ids from the instance id so each instance evaluates independently.
  - Inner results come back under `instance/inner` keys.
  - Errors inside name the inner block and carry a `path`.
  - A subsystem that contains itself is an error.
- Editor:
  - "Group into subsystem" on a selection. Each outside source becomes an input; each output used outside or on the summary becomes an output; if none are, the group's end blocks are exposed.
  - "Open subsystem" (or double-click) edits inside, with a "Back to model" breadcrumb; values shown are the opened instance's.
  - "Ungroup", "Export subsystem JSON", "Save to My blocks" (`/api/blocks`), and "Import block JSON".
  - Saved subsystems appear under My blocks in the palette and are copied into a model when used, so model files stay self-contained.
  - To change a subsystem's ports, ungroup and group again.

## Reference model: SaaS company

A generic subscription software company; every figure is illustrative. It lives in `models/reference/saas_company/` (see its README).
- Quarterly, 32 periods from 2027-01-01.
- 39 drivers (6 of them per-period series) and 80 calculation rows, plus 4 annual rollups.
- Customers: new customers are the tighter of what marketing spend buys and what the sales team can close. Churn applies to the customers at the start of each quarter. The customer count uses a closed form, `retention * cumulative(new / retention, opening)`, instead of a loop, because the spec format has no feedback rows.
- Revenue from average customers times a monthly ARPA that rises with price; cost of revenue from hosting, support and payment fees; opex by function, with one spread-out project; capex and straight-line depreciation; tax with losses carried forward; receivables, deferred revenue and payables; cash with two equity raises.
- Unit economics: fully loaded CAC, LTV to CAC, CAC payback, burn multiple, rule of 40, runway.
- Valuation: Gordon-growth terminal value, NPV (checked against discount factors) and IRR.

**Headline values:** NPV $51.2M at an 18% annual discount rate; IRR 53.4% annual; ARR grows from $10.2M to $86.6M; EBITDA turns positive in quarter 14; 4,272 customers won in total.

**Acceptance rule:** tests read `expected.json`, a snapshot of the workbook's cached values after LibreOffice recalculates its live formulas, never the workbook itself. A value passes when `|got - want| <= max(1e-6, 1e-6 * |want|)`; bool flags match exactly. The 11 `required` rows gate the test. The 21 `checkpoint` rows, and the other calculation rows in the snapshot, are reported row by row to locate the first divergence.

**Import:**
- `blockmodel.importers.rows` converts `generator/spec.py` into `models/examples/saas_company.json`: 161 blocks and 207 wires, with no errors or unit warnings.
- It checks every row's declared type against the engine's inference.
- `engine/tests/test_reference.py` is the acceptance test.

Changing the model means regenerating the workbook and `expected.json` together, as the folder README describes.

## Phases

- **Phase 0, scaffold and spike.** Repo layout, kit styles, Vite app with title block and theme toggle, FastAPI server with a stub `/api/evaluate`, typed client, one custom React Flow node styled with dt- classes. *Check:* evaluate round-trip latency on a synthetic 250-block, 120-period model.
- **Phase 1, engine and API (no UI).** Types, spec loader, model, validation, evaluator, library, schema generation, programmatic builder, server endpoints and file storage. Pytest per block, an end-to-end model, and API tests. Moved in from Phase 3: the row importer and the reference acceptance test.
- **Phase 2, editor.** Canvas, palette, typed wiring, inspector, undo/redo, server save/open, JSON import/export, live recompute and error display.
- **Phase 3, summary, export, phone view.** Summary table and report editing, CSV/XLSX export, phone read-only view with the model list and summary. (The reference model's layout and the Sample marking landed in Phase 2.)
- **Phase 4, modeling depth.** Subsystems, the Feedback block for circularity, unit algebra with warnings, the Lookup block, scenarios. (`table` became the Lookup block and `enum` was dropped, as approved.)
- **Later.** Database storage of blocks and models, integrations and sync with other systems, auth and multi-user, sandboxed user Python blocks, formula-based XLSX export.

## Status

- 2026-09-27: project defined; design kit vendored under `styles/`. Revised for server-side evaluation, desktop editing with phone view, and financial types.
- 2026-09-27: first reference model received from Chat and snapshotted to `expected.json`. Its findings are resolved above: a bracketing IRR, wirable parameter ports, Power, Running max and Safe divide, the type rules for per-unit prices, `annual<T>`, and the Excel semantics for NPV, Round and Ceiling.
- 2026-09-27: Phase 0 done. It covers:
  - a uv workspace (`engine/`, `server/`) and pydantic models that generate `schemas/api.schema.json` and `web/src/api/types.gen.ts`;
  - a stub evaluator (Constant, Add, Multiply) with cycle and per-block errors;
  - FastAPI endpoints (health, library, evaluate, examples, dev/synthetic);
  - a Vite, React and React Flow client with a custom block node, theme toggle, title block and a phone read-only view;
  - pytest, Vitest and Playwright smoke tests.
- Phase 0 latency (250 blocks by 120 periods, localhost, 20 runs from the browser): server evaluate p50 3.7 ms; round trip p50 31 ms and p95 36 ms; request 121 KiB, response 532 KiB. Gate passed (under 50 ms and 150 ms).
  - Evaluation is not the bottleneck; JSON size is. The response carries every output for every period, and on a real network 532 KiB costs roughly 200 ms at 20 Mbit/s.
  - Phase 1 therefore adds gzip on responses and an option to return only the requested ports (visible blocks and report rows).
- 2026-09-28: Phase 1 done.
  - Engine: type system and rules, 29-block library as JSON specs plus registered implementations, evaluator with per-block errors, builder, formula parser and row importer.
  - Server: evaluate with a `values` filter, validate, library with kind groups, model storage (list, get, put), gzip.
  - Client: shows inferred types and units; the demo model uses the real library.
- Phase 1 tests: 115 pytest, 12 Vitest, 7 Playwright.
  - Every block matches the reference model's numpy evaluator on random and edge-case inputs.
  - The imported reference model matches all 89 rows of `expected.json`, worst relative difference 1.8e-13 (the workbook's 15-digit rounding). It evaluates in about 8 ms.
- Phase 1 latency (250 by 120, localhost, from the browser): server evaluate p50 9 ms, round trip p50 45 ms. Gate passed.
  - Type inference roughly doubled evaluation time from Phase 0.
  - Gzip at level 1 costs 7 ms and halves the response (565 KiB to about 278 KiB); level 9 took 43 ms for 262 KiB.
  - Float values are close to incompressible, so the `values` filter is the bigger lever once the editor requests only visible blocks.
- Found and fixed while building: an inline literal in Multiply adopted its peer's kind, which would have made `2 * price` a currency-times-currency error. Literals are now plain factors in Multiply and Divide.
- 2026-09-28: Phase 2 done. The editor has:
  - a palette (filter, drag onto the canvas, or activate "Add <block>");
  - wiring by dragging handles or with the inspector's "Wire from" select; refused wires give a reason;
  - the inspector for inputs, settings, retype and values;
  - undo and redo (100 steps), copy and paste, delete, shortcuts;
  - open, new, save, import JSON and export JSON;
  - Find block.
  - Editing logic is pure functions in `web/src/editor/graph.ts`.
- Phase 2 layout: the builder's layered layout now puts each source one column left of its first consumer, orders columns by neighbours, and stacks blocks by estimated height.
  - The reference model went from one 57-block column (11,000 px) to 40 columns at most 23 blocks tall.
  - Large models open on their first columns at a readable zoom, not fitted to a speck.
- Phase 2 tests: 115 pytest, 24 Vitest, 11 Playwright. The editor flows cover drag from palette, handle wiring, inline edits recomputed by the server, undo and redo, a refused wire, save and reopen, export, keyboard-only wiring and delete, and the reference model opening with no errors.
- 2026-09-28: Phase 3 done.
  - Summary tab and row editing; CSV and XLSX export with the three sheets; the phone view opens models and reads the diagram and summary with no editing controls.
  - The importer now takes report labels from drivers too ("Equity raised", not `equity_raises`).
- Phase 3 tests: 120 pytest, 26 Vitest, 15 Playwright.
  - The XLSX test reopens the file with openpyxl and checks every report value and number format against evaluate.
  - e2e: the reference model's summary shows its NPV and IRR, both exports download, summary rows are added, renamed, reordered and removed, and at 375px the table scrolls inside its container.
- 2026-09-28: Phase 4 done.
  - Engine: Feedback loops, Lookup, scenarios, subsystems, unit algebra with warnings.
  - Examples: `cash_interest.json` (interest on the cash balance through a Feedback block; matches a hand-written period loop exactly).
  - Editor: scenarios with overrides and comparison; group, open, edit inside, ungroup, export and save subsystems; warnings on blocks and in the toolbar.
- Phase 4 tests: 140 pytest, 30 Vitest, 19 Playwright. The reference acceptance test is unchanged and passing.
- All planned phases are done. Next candidates are in "Later".
- 2026-09-28: deployable image.
  - The `Dockerfile` builds the web app and serves it from FastAPI on one port, with `/data` as the storage volume. The image is about 300 MB, most of it numpy.
  - A shared-password gate protects every route except the health check.
  - Verified locally: the image built here, and all 19 Playwright tests passed against the running container with the gate on. The latency gate passed too (round trip p95 56 ms), and saved models survived a restart.
  - Not hosted anywhere yet. See "Deploy" in the README.
- 2026-09-29: hosting fixes, from Chat's review of Render and Railway.
  - Hosted disks mount root-owned, so the image's non-root user couldn't save: health said 200, the model list was empty, and the first save failed with a 500. Reproduced with a root-owned tmpfs.
  - Fixes:
    - an entrypoint takes ownership of the data folders, then runs the server as the app user;
    - `/api/health` returns 503 when saves would fail;
    - no `VOLUME` line, which Railway rejects;
    - the build hash falls back to the host's commit.
  - Verified on a root-owned disk:
    - saves work, and the server runs as uid 10001;
    - all 19 Playwright tests pass with the gate on, and models survive a restart;
    - a container started as non-root on that disk reports 503.
- 2026-09-30: hosting on Render, from one Blueprint (`render.yaml`).
  - Production: `main`, Starter plan (512 MB), 1 GB disk at `/data`, one instance.
  - Staging: `staging`, free plan, no disk.
  - Branch plan:
    - work happens on `dev` and session branches, which are never deployed;
    - `staging` changes by merge;
    - `main` changes only by fast-forward from `staging`, so production builds the exact commit staging ran.
  - Memory, measured locally in Docker:
    - about 49 MB idle;
    - 179 MB peak evaluating a 2,000-block by 600-period synthetic model;
    - 63 MB on an XLSX export.
    - Starter's 512 MB is enough. Several very large requests at once can exceed 256 MB.
- 2026-10-01: deployed on Render.
  - Production: https://block-model-builder.onrender.com. Staging: https://block-model-builder-staging.onrender.com.
  - Checks on the live services:
    - `/api/health` returns 200 over HTTPS, and plain HTTP redirects to HTTPS;
    - the password gate works on both;
    - both footers show the deployed commit, so Render passes `RENDER_GIT_COMMIT` to the Docker build;
    - a saved model survived a restart and a full redeploy on production;
    - production memory runs at 50 to 75 MB of 512 MB;
    - logs are clean.
  - Open items:
    - Default branch: done. It's `main`, and the old session branch is deleted.
    - Branch rules: they live only in `CLAUDE.md`. GitHub enforces branch protection on private repos only with a paid plan.
    - Backups: Render's daily disk snapshots, not yet verified. "Export all models" now gives a backup you hold yourself (see below).
    - Synthetic models returned 422 on export, because they had no summary rows. Fixed (see below).
    - Shared login: no per-user identity, revocation or edit history. Real auth stays in "Later".
    - Region: not yet checked in each service's Settings against `render.yaml`.
- 2026-10-01: backups and synthetic exports.
  - **"Export all models":** a button in the Open model dialog, backed by `GET /api/backup`.
    - It downloads one zip of every saved model and block, plus a `manifest.json` with counts and restore steps.
    - Files are copied byte for byte, not re-validated, so even a file that no longer loads is kept.
  - **Synthetic models have summary rows:** one per end block in the last layer, up to 10. They export to CSV and XLSX like real models.
  - **Found while testing, not fixed:** one unreadable file in the models folder makes `GET /api/models` return 500. The saved-models list then fails to load, though the backup still includes that file. The fix is to skip unreadable files in the list and name them.
- 2026-10-01: the repo is generic.
  - The reference model is now a generic SaaS company (`models/reference/saas_company/`, example `saas_company.json`), replacing the first, industry-specific one.
  - Its workbook was recalculated in LibreOffice and matches the numpy evaluator with 0 failures (worst relative difference 2.8e-14); the engine matches `expected.json` to the same 2.8e-14.
  - Unit examples in tests and docs use generic names (`orders`, `seats`).
  - Git history was squashed to a single commit, so no earlier version of the repo is retained.

## Verification (per phase, once building)

- Engine and server: `pytest`, including API tests.
- Schemas: every block spec and example model validates against `schemas/`; a test fails if the generated schemas are out of date.
- Web: Vitest for store and API client; Playwright script that drags two blocks, wires them, edits an inline value, checks the recomputed value from the server, and exports CSV.
- Design: both themes, 1280px editor, 375px phone view, keyboard-only pass, title block present, sample data marked.
- Reference model: the imported model matches `expected.json` under the acceptance rule above (`engine/tests/test_reference.py`, since Phase 1).
