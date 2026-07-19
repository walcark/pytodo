import subprocess
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from neverland.core import service, store
from neverland.core.routine import Freq, Recurrence, Routine
from neverland.core.vocabulary import RepoConfig
from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def test_create_routine_validates_and_describes(client):
    resp = client.post(
        "/api/routines",
        json={"title": "Run", "freq": "weekly", "weekdays": ["mon", "wed", "sat"]},
    )
    assert resp.status_code == 201
    assert resp.json()["rule"] == "weekly: Mon, Wed, Sat"

    # a weekly routine with no weekdays is rejected
    bad = client.post("/api/routines", json={"title": "X", "freq": "weekly"})
    assert bad.status_code == 400
    # unknown freq too
    assert (
        client.post("/api/routines", json={"title": "X", "freq": "no"}).status_code
        == 400
    )


def test_daily_routine_materializes_and_appears_in_today(client, tmp_path):
    # every-day routine is due immediately -> creation materializes it
    client.post(
        "/api/routines", json={"title": "Water plants", "freq": "days", "interval": 1}
    )
    today = client.get("/api/today").json()
    assert [e["title"] for e in today["entries"]] == ["Water plants"]

    # the spawned occurrence is a next todo carrying the routine id
    nexts = client.get("/api/todos", params={"view": "next"}).json()
    assert len(nexts) == 1 and nexts[0]["routine"] is not None


def test_completion_advances_and_avoids_immediate_respawn(client, tmp_path):
    client.post("/api/routines", json={"title": "Water", "freq": "days", "interval": 3})
    occ = client.get("/api/todos", params={"view": "next"}).json()[0]

    client.post(f"/api/todos/{occ['id']}/complete")
    # next_due moved 3 days out, so re-materializing today spawns nothing
    assert service.materialize_routines(tmp_path, RepoConfig(sync_auto=False)) == []
    routine = store.list_routines(tmp_path)[0]
    assert routine.next_due == date.today() + timedelta(days=3)


def test_materialize_is_idempotent_while_occurrence_open(client, tmp_path):
    client.post("/api/routines", json={"title": "Run", "freq": "days", "interval": 1})
    # occurrence already open; a second materialize must not duplicate it
    service.materialize_routines(tmp_path, RepoConfig(sync_auto=False))
    nexts = client.get("/api/todos", params={"view": "next"}).json()
    assert len(nexts) == 1


def test_lead_makes_it_appear_early(tmp_path):
    # a yearly routine due in 3 days, with a 5-day lead, is already due today
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    due = date.today() + timedelta(days=3)
    routine = Routine(
        id="",
        title="Buy gift",
        recurrence=Recurrence(freq=Freq.YEARLY, month=due.month, day=due.day),
        lead=5,
        next_due=due,
    )
    store.create_routine(tmp_path, routine=routine)
    spawned = service.materialize_routines(tmp_path, RepoConfig(sync_auto=False))
    assert [t.title for t in spawned] == ["Buy gift"]


def test_delete_routine(client):
    rid = client.post(
        "/api/routines", json={"title": "Bank", "freq": "monthly", "monthday": 1}
    ).json()["id"]
    assert client.delete(f"/api/routines/{rid}").status_code == 204
    assert client.get("/api/routines").json() == []
    assert client.delete(f"/api/routines/{rid}").status_code == 404
