from fastapi.testclient import TestClient

from neverland.server.app import create_app
from neverland.server.config import ServerConfig

TOKEN = "s3cret-token"


def _client(tmp_path, token):
    config = ServerConfig(data_dir=tmp_path, token=token, poll_interval=0)
    return TestClient(create_app(config))


def test_no_token_leaves_api_open(tmp_path):
    client = _client(tmp_path, token=None)
    assert client.get("/api/vocabulary").status_code == 200


def test_missing_token_is_rejected(tmp_path):
    client = _client(tmp_path, token=TOKEN)
    resp = client.get("/api/vocabulary")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_token_is_rejected(tmp_path):
    client = _client(tmp_path, token=TOKEN)
    resp = client.get("/api/vocabulary", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_valid_token_is_accepted(tmp_path):
    client = _client(tmp_path, token=TOKEN)
    resp = client.get("/api/vocabulary", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
