"""FastAPI app wrapping the blockmodel engine.

uv run uvicorn app.main:app --app-dir server --reload --port 8000

Deployment settings (all optional): BM_WEB_DIR serves the built web app at /;
BM_AUTH_USER and BM_AUTH_PASSWORD turn on the shared-password gate (see access.py).
"""

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from blockmodel.compose import ScenarioError
from blockmodel.evaluate import ENGINE, evaluate
from blockmodel.export import ExportError, export
from blockmodel.library import load_library
from blockmodel.model import CompositeSpec, EvaluateResponse, Model
from blockmodel.spec import LibraryResponse
from blockmodel.synthetic import synthetic_model
from blockmodel.types import KIND_GROUPS
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from fastapi import Path as PathParam
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .access import BasicAuthGate, credentials_from_env
from .storage import (
    BlockStore,
    FileStore,
    ModelSummary,
    backup_zip,
    default_block_store,
    default_store,
    writable,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "models" / "examples"

api = APIRouter()

ValuesParam = Annotated[
    str,
    Query(
        description="Which blocks' values to return: all, none, or a comma-separated list of block uuids. "
        "Types and errors are always returned for every block."
    ),
]


def _include(values: str) -> list[str] | None:
    if values == "all":
        return None
    if values == "none":
        return []
    return [v.strip() for v in values.split(",") if v.strip()]


def _json(result: EvaluateResponse) -> Response:
    # The engine builds the response without re-validation; serialize it directly.
    return Response(content=result.model_dump_json(by_alias=True), media_type="application/json")


@api.get("/api/health")
def health(
    store: Annotated[FileStore, Depends(default_store)],
    blocks: Annotated[BlockStore, Depends(default_block_store)],
) -> Response:
    """200 when the server can evaluate and save. 503 when saves would fail, so a host's
    health check fails the deploy instead of passing it and failing on the first save."""
    for folder in (store.root, blocks.root):
        if not writable(folder):
            detail = (
                f"Can't save to {folder}: it isn't writable. Check that the data disk is mounted "
                "and that the server can write to it."
            )
            return JSONResponse({"status": "error", "engine": ENGINE, "detail": detail}, status_code=503)
    return JSONResponse({"status": "ok", "engine": ENGINE})


@api.get("/api/library")
def library() -> LibraryResponse:
    groups = {k: list(v) for k, v in KIND_GROUPS.items()}
    return LibraryResponse(engine=ENGINE, kind_groups=groups, specs=list(load_library()))


ScenarioParam = Annotated[
    str | None, Query(description="A scenario id from the model; omit for the base case.")
]


@api.post("/api/evaluate", response_model=EvaluateResponse)
def evaluate_model(model: Model, values: ValuesParam = "all", scenario: ScenarioParam = None) -> Response:
    try:
        return _json(evaluate(model, include=_include(values), scenario=scenario))
    except ScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.post("/api/validate", response_model=EvaluateResponse)
def validate_model(model: Model) -> Response:
    """Types and errors for every block, without computing values."""
    return _json(evaluate(model, compute=False))


@api.post("/api/export")
def export_model(
    model: Model,
    format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "xlsx",
    scenario: ScenarioParam = None,
) -> Response:
    """The summary worksheet as CSV, or as XLSX with Summary, Assumptions and Blocks sheets."""
    try:
        content, media_type = export(model, format, scenario)
    except (ExportError, ScenarioError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    base = model.name if not scenario else f"{model.name} {scenario}"
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in base).strip("_") or "model"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'},
    )


@api.get("/api/models")
def list_models(store: Annotated[FileStore, Depends(default_store)]) -> list[ModelSummary]:
    return store.list()


@api.get("/api/models/{model_id}")
def get_model(model_id: UUID, store: Annotated[FileStore, Depends(default_store)]) -> Model:
    model = store.get(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"No saved model with id {model_id}.")
    return model


@api.put("/api/models/{model_id}")
def put_model(
    model_id: UUID, model: Model, store: Annotated[FileStore, Depends(default_store)]
) -> ModelSummary:
    if model.id != model_id:
        raise HTTPException(
            status_code=422,
            detail=f"The URL names model {model_id}, but the body is model {model.id}. Use the same id.",
        )
    store.put(model)
    return next(s for s in store.list() if s.id == model_id)


@api.get("/api/blocks")
def list_blocks(store: Annotated[BlockStore, Depends(default_block_store)]) -> list[CompositeSpec]:
    """Saved subsystems, for the palette's My blocks."""
    return store.list()


@api.put("/api/blocks/{block_id}")
def put_block(
    block_id: Annotated[str, PathParam(pattern=r"^user\.[a-z0-9_]+$")],
    spec: CompositeSpec,
    store: Annotated[BlockStore, Depends(default_block_store)],
) -> CompositeSpec:
    if spec.id != block_id:
        raise HTTPException(
            status_code=422,
            detail=f"The URL names block {block_id}, but the body is block {spec.id}. Use the same id.",
        )
    store.put(spec)
    return spec


@api.get("/api/backup")
def backup(
    store: Annotated[FileStore, Depends(default_store)],
    blocks: Annotated[BlockStore, Depends(default_block_store)],
) -> Response:
    """Every saved model and block as one zip, so backups don't depend on the host's disk snapshots."""
    now = datetime.now(UTC).replace(microsecond=0)
    return Response(
        content=backup_zip(store, blocks, ENGINE, now),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="block-model-builder-backup-{now:%Y%m%d-%H%M%S}.zip"'
        },
    )


@api.get("/api/examples/{name}")
def example(name: Annotated[str, PathParam(pattern=r"^[a-z0-9_-]+$")]) -> Model:
    path = EXAMPLES_DIR / f"{name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No example model named {name}.")
    return Model.model_validate_json(path.read_text())


@api.get("/api/dev/synthetic")
def synthetic(
    blocks: Annotated[int, Query(ge=11, le=2000)] = 250,
    periods: Annotated[int, Query(ge=1, le=600)] = 120,
) -> Model:
    return synthetic_model(blocks=blocks, periods=periods)


def create_app(env: Mapping[str, str] = os.environ) -> FastAPI:
    """The API, plus the built web app and the password gate when the environment asks for them."""
    app = FastAPI(title="Block model builder", version="0.1.0")
    app.include_router(api)
    web_dir = env.get("BM_WEB_DIR")
    if web_dir:
        if not (Path(web_dir) / "index.html").is_file():
            raise RuntimeError(f"BM_WEB_DIR={web_dir} has no index.html. Run npm run build in web/ first.")
        # Mounted after the API routes, so /api paths never reach it.
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    # Level 1: 7 ms for 565 KiB -> 278 KiB on the 250 by 120 model; level 9 takes 43 ms for 262 KiB.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=1)
    credentials = credentials_from_env(env)
    if credentials:
        app.add_middleware(BasicAuthGate, credentials=credentials)
    return app


app = create_app()
