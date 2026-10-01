# Block model builder

A browser-based, LabVIEW-style graphical modeling tool: typed function blocks wired into a system, evaluated on the server, and exported as a summary worksheet. The definition, architecture and phases are in [`docs/PROJECT.md`](docs/PROJECT.md).

Status: all four phases done (editor, summary and export, scenarios, subsystems, feedback loops).
- The engine has the 31-block library and the type rules. It reproduces the SaaS company reference model to within 2.8e-14 of its workbook, which LibreOffice recalculates independently.
- The browser editor builds, wires, edits, saves and reopens models. The Summary tab shows report rows and exports CSV and XLSX.

## Layout

| Path | What it is |
|---|---|
| `engine/` | Python package `blockmodel`: data model, type rules, block library, evaluator, builder, importers |
| `server/` | FastAPI app wrapping the engine |
| `schemas/` | JSON Schema generated from the pydantic models |
| `web/` | Vite + React + TypeScript client, React Flow canvas |
| `styles/` | Drafting Table design system, unmodified |
| `models/examples/` | `demo.json` (loads in the app), `saas_company.json` (generated from the reference model) and `cash_interest.json` (a feedback loop) |
| `models/reference/saas_company/` | The reference model (a generic SaaS company), its workbook, and its `expected.json` acceptance fixture |

## Development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node 22+.

```
uv sync                                                    # Python deps into .venv
uv run uvicorn app.main:app --app-dir server --port 8000   # API on :8000
cd web && npm install && npm run dev                       # app on :5173, proxies /api to :8000
```

## Checks

```
uv run ruff format --check . && uv run ruff check .
uv run pytest                     # engine and API tests, including schema freshness
cd web
npm run typecheck && npm test     # TypeScript and Vitest
npm run e2e                       # builds, starts both servers, runs Playwright smoke tests
```

The e2e run writes screenshots (light and dark at 1280px and 375px, and the reference model with a block selected) and the latency table to `web/e2e-screens/`. Models saved during e2e runs go to `web/e2e-data/`. The latency check page is at `/?dev=latency`.

## Using the editor

- Add blocks from the palette: drag onto the canvas, or activate "Add <block>" to place it in the middle of the view.
- Wire by dragging from an output handle (right) to an input handle (left), or select a block and choose "Wire <input> from" in the inspector.
- Unwired inputs take a value typed in the inspector; 25% is read as 0.25.
- Shortcuts: Delete, Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y, Ctrl+C, Ctrl+V, Ctrl+S.
- "Open model" lists the examples and saved models; "Find block" jumps to a block by label.
- "Export all models", in the Open model dialog, downloads one zip with every saved model and saved block, as a backup.
- In the inspector, "Add to summary" puts an output on the Summary tab, where Export CSV and Export XLSX download the worksheet.
- Scenarios: "New scenario" in the toolbar, then change values; they apply only to that scenario. The Summary compares scenarios.
- Subsystems: select blocks, "Group into subsystem"; double-click to edit inside. "Save to My blocks" reuses it in other models.
- Loops: wire the value to carry into a Feedback block's x; it passes the previous period's value (see the cash interest example).

## Building models in Python

```python
from datetime import date
from blockmodel import ModelBuilder, Timeline, evaluate

b = ModelBuilder("Revenue", Timeline(start=date(2027, 1, 1), frequency="quarter", periods=8))
price = b.constant(12.5, kind="currency", unit="USD/unit", label="Price")
units = b.series([40, 44, 48, 52, 56, 60, 64, 68], kind="count", unit="unit", label="Units")
revenue = b.add("math.multiply", a=price, b=units, label="Revenue")
model = b.build()
print(evaluate(model).outputs[str(revenue.block)]["result"])  # series<currency> USD
open("revenue.json", "w").write(model.model_dump_json(by_alias=True, indent=1))
```

Block ids and ports are listed in `engine/blockmodel/library/specs/`.

## Regenerating the reference example

After changing the library, the type rules or the importer:

```
uv run python -m blockmodel.importers.rows models/reference/saas_company/generator/spec.py models/examples/saas_company.json \
  --scenarios churn_rate_q,arpa_monthly
uv run python -m blockmodel.examples     # code-built examples such as cash_interest.json
```

`pytest` fails if the committed file is stale.

## Changing the data model

The pydantic models in `engine/blockmodel/model.py` are the source of truth. After changing them:

```
uv run python -m blockmodel.schema     # regenerates schemas/api.schema.json
cd web && npm run gen:types            # regenerates src/api/types.gen.ts
```

`pytest` fails if the schema file is stale.

## Deploy

One Docker image serves the web app and the API on one port. Saved models and blocks live on a disk mounted at `/data`.

```
docker build --build-arg BUILD_HASH=$(git rev-parse --short HEAD) -t block-model-builder .
docker run -p 8000:8000 -v bm-data:/data \
  -e BM_AUTH_USER=team -e BM_AUTH_PASSWORD='choose-a-long-password' \
  block-model-builder
```

Settings, all environment variables:

- `BM_AUTH_USER` and `BM_AUTH_PASSWORD`: a shared-password gate (HTTP basic auth) on every route except `/api/health`. Set both, or neither for no gate. With only one set, the server refuses to start and names the missing one.
- `PORT`: the port to listen on (default 8000). Many hosts set it for you.
- `BM_WEB_DIR`, `BM_DATA_DIR`, `BM_BLOCKS_DIR`: set by the image; change them only if you move things.
- Build hash in the footer: `BUILD_HASH` if given, otherwise the host's commit (`RENDER_GIT_COMMIT` or `RAILWAY_GIT_COMMIT_SHA`, when the host passes it as a build arg), otherwise "unknown".

How the image behaves on a host:

- Hosted disks (Render, Railway) mount root-owned. The entrypoint (`docker-entrypoint.sh`) starts as root, creates the data folders, gives them to the `app` user (uid 10001), then runs the server as that user. The server never runs as root.
- `/api/health` returns 503 when the data folders aren't writable, so a missing or read-only disk fails the host's health check instead of passing it and failing on the first save. Point the host's health check at `/api/health`.
- The Dockerfile has no `VOLUME` line, because Railway rejects Dockerfiles that have one. Mount the disk with `-v` locally, or with the host's disk settings.

To check the image against a root-owned disk before deploying:

```
docker run --rm -p 8000:8000 --tmpfs /data:mode=0755,uid=0 block-model-builder
```

`/api/health` should return 200 and saving a model should work.

Before sharing a deployment:

- Put HTTPS in front of it. Basic auth sends the password with every request, so it must not travel over plain HTTP. Most hosts terminate TLS for you.
- Run one instance only. Storage is JSON files on the volume, so two instances would not see each other's saves.
- Use a persistent volume. Without one, saved models are lost when the container is replaced.
- The gate is a stopgap. Everyone shares one login, there's no per-user history, and anyone with the password can overwrite any model. Real auth is in "Later" in `docs/PROJECT.md`.

To run the browser tests against a running deployment (in `web/`):

```
E2E_BASE_URL=http://127.0.0.1:8000 E2E_USER=team E2E_PASSWORD=... npx playwright test
```

These tests save models to the deployment's storage, so point them at a test instance.

### Render

`render.yaml` is a Render Blueprint with two services:

| Service | Branch | Plan | Disk |
|---|---|---|---|
| `block-model-builder` (production) | `main` | Starter (512 MB) | 1 GB at `/data` |
| `block-model-builder-staging` | `staging` | Free | None |

- Each service deploys on every commit to its branch. `dev` and session branches are never deployed.
- When you create the Blueprint, Render prompts for `BM_AUTH_USER` and generates `BM_AUTH_PASSWORD`. Read the password on each service's Environment page.
- Staging has no disk, because Render doesn't allow one on the free plan. Saves on staging are lost on each deploy, and when the free instance spins down after idling.
- The footer's build hash comes from `RENDER_GIT_COMMIT`, which Render passes to the Docker build. Confirmed on the first deploy: both footers showed the deployed commit.

Backups:

- Render takes daily snapshots of production's disk.
- For a copy you hold yourself, choose Open model, then "Export all models" (`GET /api/backup`). You get a zip with `models/`, `blocks/` and a `manifest.json` that lists the counts and how to restore.
- The files are copied byte for byte, so even a file that no longer loads is kept.
- To restore one model, choose Import JSON, pick its file from the zip, then Save model. To restore everything, copy the files into the server's `BM_DATA_DIR` and `BM_BLOCKS_DIR`.

Live:

- Production: https://block-model-builder.onrender.com
- Staging: https://block-model-builder-staging.onrender.com

The Blueprint reads `render.yaml` from `main`, with Auto Sync. A change to `render.yaml`, even one for the staging service, takes effect only once it reaches `main`.

Promoting a change:

```
git checkout staging && git merge dev && git push origin staging   # deploys staging
# check staging, then:
git push origin staging:main                                       # deploys production; fast-forward only
```

`git push origin staging:main` is refused unless it's a fast-forward, so production always runs a commit staging ran first. Each production deploy probably has a short outage, because Render can't do zero-downtime deploys for a service with a disk. That's unverified; watch the first redeploy.

Behind a proxy that re-signs TLS, pass its CA bundle to the build as a secret: `--secret id=ca,src=/path/to/ca-bundle.crt`. Only the download steps use it, and it isn't kept in the image.
