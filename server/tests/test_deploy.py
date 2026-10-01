"""Deployment settings: the built web app served at /, and the shared-password gate."""

import pytest
from app.access import GateConfigError
from app.main import create_app
from app.storage import BlockStore, FileStore, default_block_store, default_store
from fastapi.testclient import TestClient

AUTH = {"BM_AUTH_USER": "team", "BM_AUTH_PASSWORD": "s3cret:with-colon"}


@pytest.fixture
def web_dir(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Block model builder</title>")
    return tmp_path


def test_serves_the_web_app_beside_the_api(web_dir):
    client = TestClient(create_app({"BM_WEB_DIR": str(web_dir)}))
    page = client.get("/")
    assert page.status_code == 200 and "Block model builder" in page.text
    assert client.get("/?dev=latency").status_code == 200
    assert client.get("/api/library").json()["specs"]
    missing = client.get("/api/nope")
    assert missing.status_code == 404 and missing.json() == {"detail": "Not Found"}


def test_no_web_app_unless_asked():
    assert TestClient(create_app({})).get("/").status_code == 404


def test_a_web_dir_without_a_build_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="npm run build"):
        create_app({"BM_WEB_DIR": str(tmp_path)})


def test_gate_requires_the_shared_credentials(web_dir):
    client = TestClient(create_app({**AUTH, "BM_WEB_DIR": str(web_dir)}))
    for path in ("/", "/api/library", "/api/models"):
        denied = client.get(path)
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"].startswith('Basic realm="Block model builder"')
    assert client.get("/", auth=("team", "wrong")).status_code == 401
    assert client.get("/", auth=("other", AUTH["BM_AUTH_PASSWORD"])).status_code == 401
    assert client.get("/", headers={"Authorization": "Basic not-base64!"}).status_code == 401
    assert client.get("/", headers={"Authorization": "Bearer x"}).status_code == 401
    assert client.get("/", auth=("team", AUTH["BM_AUTH_PASSWORD"])).status_code == 200
    assert client.get("/api/library", auth=("team", AUTH["BM_AUTH_PASSWORD"])).status_code == 200


def test_health_stays_open_behind_the_gate():
    assert TestClient(create_app(AUTH)).get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "only, missing", [("BM_AUTH_USER", "BM_AUTH_PASSWORD"), ("BM_AUTH_PASSWORD", "BM_AUTH_USER")]
)
def test_a_half_configured_gate_refuses_to_start(only, missing):
    with pytest.raises(GateConfigError, match=f"^{missing} is not set"):
        create_app({only: AUTH[only]})


def test_no_gate_when_unset():
    assert TestClient(create_app({})).get("/api/library").status_code == 200


def test_health_fails_when_saves_would_fail(tmp_path):
    """A disk the server can't write to fails the health check, instead of the first save."""
    app = create_app({})
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("")  # a file where the data folder's parent should be; fails even as root
    app.dependency_overrides[default_store] = lambda: FileStore(blocker / "models")
    app.dependency_overrides[default_block_store] = lambda: BlockStore(tmp_path / "blocks")
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"].startswith(f"Can't save to {blocker / 'models'}")
    # Folders that don't exist yet are fine when the server can create them.
    app.dependency_overrides[default_store] = lambda: FileStore(tmp_path / "new" / "models")
    assert TestClient(app).get("/api/health").status_code == 200
