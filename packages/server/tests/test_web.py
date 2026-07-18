from fastapi.testclient import TestClient

from neverland.server.app import create_app
from neverland.server.config import ServerConfig


def _client(tmp_path, static_dir):
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config, static_dir=static_dir))


def _built_static(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>neverland</title>")
    return static


def test_serves_index_when_built(tmp_path):
    client = _client(tmp_path, _built_static(tmp_path))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "neverland" in resp.text


def test_hint_when_not_built(tmp_path):
    client = _client(tmp_path, tmp_path / "missing")
    resp = client.get("/")
    assert resp.status_code == 503
    assert "build-web" in resp.json()["detail"]


def test_api_wins_over_the_spa_mount(tmp_path):
    # The catch-all static mount at "/" must not shadow the API.
    client = _client(tmp_path, _built_static(tmp_path))
    assert client.get("/api/vocabulary").status_code == 200
