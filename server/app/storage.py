"""Model storage: one JSON file per model under a data directory.

A database replaces this later behind the same three functions.
"""

import io
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from blockmodel.model import CompositeSpec, Model
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]


def writable(folder: Path) -> bool:
    """Whether saves to `folder` would work: it, or the nearest folder above it that exists, is writable."""
    path = folder
    while not path.exists() and path != path.parent:
        path = path.parent
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


class ModelSummary(BaseModel):
    id: UUID
    name: str
    blocks: int
    updated: datetime


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, model_id: UUID) -> Path:
        return self.root / f"{model_id}.json"

    def list(self) -> list[ModelSummary]:
        if not self.root.is_dir():
            return []
        summaries = []
        for path in self.root.glob("*.json"):
            model = Model.model_validate_json(path.read_text())
            updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            summaries.append(
                ModelSummary(id=model.id, name=model.name, blocks=len(model.blocks), updated=updated)
            )
        return sorted(summaries, key=lambda s: s.updated, reverse=True)

    def get(self, model_id: UUID) -> Model | None:
        path = self._path(model_id)
        return Model.model_validate_json(path.read_text()) if path.is_file() else None

    def put(self, model: Model) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        text = model.model_dump_json(by_alias=True, indent=1)
        # Write to a temp file and rename, so a crash never leaves a half-written model.
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(text + "\n")
        os.replace(tmp, self._path(model.id))


def default_store() -> FileStore:
    return FileStore(Path(os.environ.get("BM_DATA_DIR", REPO_ROOT / "data" / "models")))


class BlockStore:
    """Saved subsystems (composite blocks), one JSON file per id, for reuse across models."""

    def __init__(self, root: Path):
        self.root = root

    def list(self) -> list[CompositeSpec]:
        if not self.root.is_dir():
            return []
        return sorted(
            (CompositeSpec.model_validate_json(p.read_text()) for p in self.root.glob("*.json")),
            key=lambda c: c.title.lower(),
        )

    def put(self, spec: CompositeSpec) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(spec.model_dump_json(by_alias=True, indent=1) + "\n")
        os.replace(tmp, self.root / f"{spec.id}.json")


def default_block_store() -> BlockStore:
    return BlockStore(Path(os.environ.get("BM_BLOCKS_DIR", REPO_ROOT / "data" / "blocks")))


RESTORE_NOTE = (
    "To restore one model, open the app, choose Import JSON, pick a file from models/, then Save model. "
    "To restore everything, copy models/*.json into the server's model folder (BM_DATA_DIR) and "
    "blocks/*.json into its block folder (BM_BLOCKS_DIR)."
)


def backup_zip(models: FileStore, blocks: BlockStore, engine: str, now: datetime) -> bytes:
    """Every saved model and block, copied byte for byte (not re-validated, so even a file that no
    longer loads is kept), plus a manifest that says what's inside and how to restore it."""
    buffer = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, root in (("models", models.root), ("blocks", blocks.root)):
            paths = sorted(root.glob("*.json")) if root.is_dir() else []
            for path in paths:
                zf.writestr(f"{folder}/{path.name}", path.read_bytes())
            counts[folder] = len(paths)
        manifest = {"created": now.isoformat(), "engine": engine, **counts, "restore": RESTORE_NOTE}
        zf.writestr("manifest.json", json.dumps(manifest, indent=1) + "\n")
    return buffer.getvalue()
