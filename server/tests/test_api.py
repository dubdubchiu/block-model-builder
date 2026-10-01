import gzip
import io
import json
import time
import uuid
import zipfile

import pytest
from app.main import app
from app.storage import BlockStore, FileStore, default_block_store, default_store
from fastapi.testclient import TestClient

TOTAL = "121f5ae3-4f9c-4590-9b58-e332ae7e52b0"
PRICE = "502cd728-7c8c-43e6-bd27-fa99e7f6ae87"


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[default_store] = lambda: FileStore(tmp_path / "models")
    app.dependency_overrides[default_block_store] = lambda: BlockStore(tmp_path / "blocks")
    yield TestClient(app)
    app.dependency_overrides.clear()


def demo(client) -> dict:
    return client.get("/api/examples/demo").json()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["engine"].startswith("blockmodel")


def test_library(client):
    body = client.get("/api/library").json()
    assert len(body["specs"]) == 31
    assert "count" in body["kind_groups"]["integer"]
    lag = next(s for s in body["specs"] if s["id"] == "series.lag")
    assert [p["name"] for p in lag["inputs"]] == ["x", "n"]


def test_evaluate_demo(client):
    body = client.post("/api/evaluate", json=demo(client)).json()
    assert body["errors"] == []
    total = body["outputs"][TOTAL]["result"]
    assert total["type"] == "series<currency>" and total["value"][0] == 650.0
    assert body["timeline"]["period_labels"][0] == "2027Q1"


def test_values_filter(client):
    model = demo(client)
    none = client.post("/api/evaluate", params={"values": "none"}, json=model).json()
    assert none["outputs"][TOTAL]["result"]["value"] is None
    assert none["outputs"][TOTAL]["result"]["type"] == "series<currency>"
    some = client.post("/api/evaluate", params={"values": TOTAL}, json=model).json()
    assert some["outputs"][TOTAL]["result"]["value"] is not None
    assert some["outputs"][PRICE]["value"]["value"] is None


def test_validate_returns_types_without_values(client):
    body = client.post("/api/validate", json=demo(client)).json()
    assert body["errors"] == []
    assert body["outputs"][TOTAL]["result"] == {"type": "series<currency>", "unit": "USD", "value": None}


def test_invalid_model_is_rejected(client):
    assert client.post("/api/evaluate", json={"schemaVersion": 1}).status_code == 422


def test_examples(client):
    assert client.get("/api/examples/..%2Fsecrets").status_code in (404, 422)
    assert client.get("/api/examples/missing").status_code == 404
    reference = client.get("/api/examples/saas_company").json()
    body = client.post("/api/evaluate", json=reference).json()
    assert body["errors"] == [] and len(body["outputs"]) == len(reference["blocks"])


def test_model_storage_round_trip(client):
    assert client.get("/api/models").json() == []
    model = demo(client)
    saved = client.put(f"/api/models/{model['id']}", json=model)
    assert saved.status_code == 200
    assert saved.json()["name"] == model["name"] and saved.json()["blocks"] == 4
    listed = client.get("/api/models").json()
    assert [m["id"] for m in listed] == [model["id"]]
    assert client.get(f"/api/models/{model['id']}").json() == model
    assert client.get(f"/api/models/{uuid.uuid4()}").status_code == 404


def test_model_id_must_match(client):
    model = demo(client)
    response = client.put(f"/api/models/{uuid.uuid4()}", json=model)
    assert response.status_code == 422
    assert "Use the same id" in response.json()["detail"]


def test_synthetic_round_trip_and_gzip(client):
    model = client.get("/api/dev/synthetic", params={"blocks": 250, "periods": 120}).json()
    assert len(model["blocks"]) == 250
    client.post("/api/evaluate", json=model)  # warm up
    t0 = time.perf_counter()
    response = client.post("/api/evaluate", json=model, headers={"Accept-Encoding": "gzip"})
    elapsed = (time.perf_counter() - t0) * 1000
    body = response.json()
    assert body["errors"] == []
    assert response.headers["content-encoding"] == "gzip"
    raw = len(response.content)
    compressed = len(gzip.compress(response.content))
    print(
        f"\nTestClient round trip, 250 by 120: {elapsed:.1f} ms total, {body['timing']['evaluate_ms']:.2f} ms evaluate, "
        f"{raw / 1024:.0f} KiB JSON, about {compressed / 1024:.0f} KiB gzipped"
    )


def test_export_endpoint(client):
    reference = client.get("/api/examples/saas_company").json()
    xlsx = client.post("/api/export", params={"format": "xlsx"}, json=reference)
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="Reference_model__saas_company.xlsx"' in xlsx.headers["content-disposition"]
    assert xlsx.content[:2] == b"PK"  # a zip container
    csv = client.post("/api/export", params={"format": "csv"}, json=reference)
    assert csv.text.splitlines()[0].startswith("Reference model")
    empty = client.post("/api/export", params={"format": "csv"}, json=demo(client))
    assert empty.status_code == 422 and "Add to summary" in empty.json()["detail"]
    assert client.post("/api/export", params={"format": "pdf"}, json=reference).status_code == 422


def test_scenarios_over_the_api(client):
    model = client.get("/api/examples/cash_interest").json()
    base = client.post("/api/evaluate", json=model).json()
    high = client.post("/api/evaluate", params={"scenario": "high-rate"}, json=model).json()
    assert high["scenario"] == "high-rate"
    cash = next(b["uuid"] for b in model["blocks"] if b["label"] == "Cash at end of quarter")
    assert high["outputs"][cash]["result"]["value"][-1] > base["outputs"][cash]["result"]["value"][-1]
    missing = client.post("/api/evaluate", params={"scenario": "nope"}, json=model)
    assert missing.status_code == 422 and "high-rate" in missing.json()["detail"]
    csv = client.post("/api/export", params={"format": "csv", "scenario": "high-rate"}, json=model)
    assert "(scenario: Interest at 3% per quarter)" in csv.text.splitlines()[0]


def test_saved_blocks(client):
    spec = {
        "id": "user.double",
        "title": "Double",
        "inputs": [
            {"name": "x", "targets": [{"block": "9a1b6f7e-0000-4000-8000-000000000003", "port": "a"}]}
        ],
        "outputs": [
            {"name": "y", "source": {"block": "9a1b6f7e-0000-4000-8000-000000000003", "port": "result"}}
        ],
        "blocks": [
            {
                "uuid": "9a1b6f7e-0000-4000-8000-000000000003",
                "spec": "math.multiply@1",
                "inline": {"b": 2},
                "position": {"x": 0, "y": 0},
            }
        ],
        "wires": [],
    }
    assert client.get("/api/blocks").json() == []
    assert client.put("/api/blocks/user.double", json=spec).status_code == 200
    assert [b["id"] for b in client.get("/api/blocks").json()] == ["user.double"]
    assert client.put("/api/blocks/user.other", json=spec).status_code == 422


def test_synthetic_model_exports(client):
    model = client.get("/api/dev/synthetic", params={"blocks": 250, "periods": 120}).json()
    response = client.post("/api/export", params={"format": "xlsx"}, json=model)
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def backup(client) -> tuple[zipfile.ZipFile, dict]:
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="block-model-builder-backup-'
    )
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return archive, json.loads(archive.read("manifest.json"))


def test_backup_with_nothing_saved(client):
    archive, manifest = backup(client)
    assert archive.namelist() == ["manifest.json"]
    assert manifest["models"] == 0 and manifest["blocks"] == 0
    assert "Import JSON" in manifest["restore"]


def test_backup_holds_every_saved_model_and_block_byte_for_byte(client, tmp_path):
    model = demo(client)
    assert client.put(f"/api/models/{model['id']}", json=model).status_code == 200
    other = {**model, "id": str(uuid.uuid4()), "name": "Second"}
    assert client.put(f"/api/models/{other['id']}", json=other).status_code == 200
    spec = {"id": "user.empty", "title": "Empty", "outputs": [], "blocks": [], "wires": []}
    assert client.put("/api/blocks/user.empty", json=spec).status_code == 200
    # A file that no longer validates is still backed up: a backup copies, it doesn't judge.
    (tmp_path / "models" / "broken.json").write_text("{not json")

    archive, manifest = backup(client)
    names = sorted(archive.namelist())
    assert names == sorted(
        [
            "manifest.json",
            "models/broken.json",
            f"models/{model['id']}.json",
            f"models/{other['id']}.json",
            "blocks/user.empty.json",
        ]
    )
    assert manifest["models"] == 3 and manifest["blocks"] == 1
    for name in (n for n in names if n != "manifest.json"):
        folder = "models" if name.startswith("models/") else "blocks"
        assert archive.read(name) == (tmp_path / folder / name.split("/")[1]).read_bytes()
