import pytest
from sqlalchemy import select

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from anipik.api import create_app  # noqa: E402
from anipik.db import session_scope  # noqa: E402
from anipik.models import Episode, Job  # noqa: E402
from anipik.sources import SOURCE_KINDS, Release, SourceKind  # noqa: E402


class FakeSource(SourceKind):
    kind = "fake"
    fields = ("feed",)

    def search(self, params):
        return [Release("[GroupA] Show - 03 [1080P][简体内嵌]", "magnet:?xt=urn:btih:" + "3" * 40),
                Release("[GroupA] Show - 02 [1080P][繁体内嵌]", "magnet:?xt=urn:btih:" + "2" * 40),
                Release("【GroupB】Show [01-12] 合集", "magnet:?xt=urn:btih:" + "1" * 40)]


@pytest.fixture
def client(factory, monkeypatch):
    monkeypatch.setitem(SOURCE_KINDS, "fake", FakeSource)
    with TestClient(create_app(factory)) as c:
        yield c


@pytest.fixture
def source(client):
    r = client.post("/api/sources", json={"name": "src", "kind": "fake", "config": {"feed": "x"}})
    assert r.status_code == 201
    return r.json()


def test_subscription_crud(client, source):
    body = {"name": "Show", "save_dir": "26年10月/Show", "bangumi_id": 1, "cover_url": "https://x/c.jpg",
            "start_episode": 3, "bindings": [{"source_id": source["id"], "keywords": ["GroupA", "Show"],
                                              "include": ["简体"]}]}
    r = client.post("/api/subscriptions", json=body)
    assert r.status_code == 201, r.text
    sub = r.json()
    assert [(e["number"], e["status"]) for e in sub["episodes"]] == [(1, "skipped"), (2, "skipped")]
    assert sub["bindings"][0]["include"] == ["简体"] and sub["destination"].endswith("Show")
    assert client.post("/api/subscriptions", json=body).status_code == 409

    listing = client.get("/api/subscriptions").json()
    assert listing[0]["counts"] == {"skipped": 2} and listing[0]["sources"] == ["src"]

    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"enabled": False, "bindings": [
        {"source_id": source["id"], "keywords": ["Show"], "exclude": ["720"]}]})
    assert r.status_code == 200
    assert r.json()["enabled"] is False and r.json()["bindings"][0]["keywords"] == ["Show"]
    assert client.patch(f"/api/subscriptions/{sub['id']}",
                        json={"bindings": [{"source_id": 999, "keywords": ["x"]}]}).status_code == 422

    r = client.post(f"/api/subscriptions/{sub['id']}/episodes", json={"numbers": [2, 5], "status": "done"})
    assert {e["number"]: e["status"] for e in r.json()["episodes"]} == {1: "skipped", 2: "done", 5: "done"}
    r = client.post(f"/api/subscriptions/{sub['id']}/episodes", json={"numbers": [5], "status": "delete"})
    assert [e["number"] for e in r.json()["episodes"]] == [1, 2]

    assert client.delete(f"/api/sources/{source['id']}").status_code == 409  # still bound
    assert client.delete(f"/api/subscriptions/{sub['id']}").status_code == 204
    assert client.get(f"/api/subscriptions/{sub['id']}").status_code == 404
    assert client.delete(f"/api/sources/{source['id']}").status_code == 204


def test_preview(client, source):
    sub = client.post("/api/subscriptions", json={"name": "Show", "start_episode": 3, "bindings": [
        {"source_id": source["id"], "keywords": ["Show"]}]}).json()
    r = client.post("/api/sources/preview", json={"source_id": source["id"], "keywords": ["Show"],
                                                  "include": ["简体"], "subscription_id": sub["id"]})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [(i["episode"], i["matched"], i["group"], i["status"]) for i in items] == [
        (3, True, "GroupA", None), (2, False, "GroupA", "skipped"), (None, False, "GroupB", None)]
    assert items[2]["batch"] is True
    bad = client.post("/api/sources/preview", json={"source_id": source["id"], "keywords": ["x"], "include": ["("]})
    assert bad.status_code == 422


def test_job_actions(client, factory, source):
    sub = client.post("/api/subscriptions", json={"name": "Show", "bindings": [
        {"source_id": source["id"], "keywords": ["Show"]}]}).json()
    with session_scope(factory) as s:
        episode = Episode(subscription_id=sub["id"], number=4, status="needs_attention", attempts=1)
        s.add(episode)
        s.flush()
        s.add(Job(episode_id=episode.id, downloader="pikpak_client", url="magnet:?", destination="D:/x",
                  phase="needs_attention", state={"phase": "cloud_submitting"}, error="unknown"))
    jobs = client.get("/api/jobs", params={"view": "attention"}).json()
    assert len(jobs) == 1 and jobs[0]["subscription"]["name"] == "Show" and jobs[0]["episode"] == 4
    job_id = jobs[0]["id"]

    r = client.post(f"/api/jobs/{job_id}", json={"action": "retry_from_scratch"})
    assert r.json()["phase"] == "running" and r.json()["backend_phase"] == "new"
    assert client.post(f"/api/jobs/{job_id}", json={"action": "abandon"}).status_code == 409  # running now

    with session_scope(factory) as s:
        s.get(Job, job_id).phase = "failed"
    assert client.post(f"/api/jobs/{job_id}", json={"action": "mark_done"}).json()["phase"] == "done"
    with session_scope(factory) as s:
        assert s.scalar(select(Episode).where(Episode.number == 4)).status == "done"


def test_settings_validation(client):
    assert client.get("/api/settings").json()["max_active_jobs"] == 5
    assert client.patch("/api/settings", json={"max_active_jobs": 2, "library_root": "N:/新番"}).status_code == 200
    assert client.get("/api/settings").json()["library_root"] == "N:/新番"
    assert client.patch("/api/settings", json={"nope": 1}).status_code == 422
    assert client.patch("/api/settings", json={"max_active_jobs": "2"}).status_code == 422
    assert client.patch("/api/settings", json={"downloader": "nope"}).status_code == 422


def test_status_and_scan_request(client):
    status = client.get("/api/status").json()
    assert status["scheduler_in_process"] is False and status["downloader"] == "pikpak_client"
    assert client.post("/api/scan").json() == {"requested": True}
    assert client.get("/api/settings").status_code == 200


def test_server_settings_and_restart(factory):
    import time
    restarts = []
    with TestClient(create_app(factory, server={"host": "127.0.0.1", "port": 8964},
                               on_restart=lambda: restarts.append(1))) as c:
        assert c.get("/api/settings").json()["server.port"] == 8964
        assert c.patch("/api/settings", json={"server.host": "0.0.0.0", "server.port": 9000}).status_code == 200
        assert c.patch("/api/settings", json={"server.host": "everywhere"}).status_code == 422
        assert c.patch("/api/settings", json={"server.port": 70000}).status_code == 422
        server = c.get("/api/status").json()["server"]
        assert server["port"] == 8964 and server["can_restart"] is True  # still the bound address
        assert c.post("/api/app/restart").json() == {"restarting": True}
        time.sleep(0.8)
        assert restarts == [1]
    with TestClient(create_app(factory)) as c:  # console mode: no restart hook
        assert c.post("/api/app/restart").status_code == 409
