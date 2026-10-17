import os

import pytest
from sqlalchemy import select

from anipik.db import session_scope
from anipik.folders import FolderMoveError, move_folder
from anipik.models import Episode, Job


def make(path, files=("ep01.mkv",)):
    path.mkdir(parents=True)
    for name in files:
        (path / name).write_bytes(b"x")
    return path


def test_move_into_new_parent(tmp_path):
    old = make(tmp_path / "Show")
    assert move_folder(old, tmp_path / "26年10月" / "Show S2") == "moved"
    assert not old.exists() and (tmp_path / "26年10月" / "Show S2" / "ep01.mkv").is_file()


def test_missing_and_same(tmp_path):
    assert move_folder(tmp_path / "nope", tmp_path / "x") == "missing"
    make(tmp_path / "Show")
    assert move_folder(tmp_path / "Show", tmp_path / "Show") == "same"


def test_refuses_to_merge_or_nest(tmp_path):
    old = make(tmp_path / "Show")
    make(tmp_path / "Other", files=("keep.mkv",))
    with pytest.raises(FolderMoveError, match="不为空"):
        move_folder(old, tmp_path / "Other")
    with pytest.raises(FolderMoveError, match="里面"):
        move_folder(old, old / "Season 2")
    assert (old / "ep01.mkv").is_file() and (tmp_path / "Other" / "keep.mkv").is_file()


def test_empty_target_is_replaced(tmp_path):
    old = make(tmp_path / "Show")
    (tmp_path / "Empty").mkdir()
    assert move_folder(old, tmp_path / "Empty") == "moved"
    assert (tmp_path / "Empty" / "ep01.mkv").is_file()


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive file system")
def test_case_only_rename(tmp_path):
    make(tmp_path / "show")
    assert move_folder(tmp_path / "show", tmp_path / "Show") == "moved"
    assert [p.name for p in tmp_path.iterdir()] == ["Show"]


# -- through the API ---------------------------------------------------------------
@pytest.fixture
def client(factory, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from anipik.api import create_app

    with TestClient(create_app(factory)) as c:
        c.patch("/api/settings", json={"library_root": str(tmp_path / "lib")})
        yield c


def test_rename_save_dir_moves_folder_and_job_paths(client, factory, tmp_path):
    sub = client.post("/api/subscriptions", json={"name": "Show", "bindings": []}).json()
    old = make(tmp_path / "lib" / "Show")
    with session_scope(factory) as s:
        episode = Episode(subscription_id=sub["id"], number=1, status="done", attempts=1)
        s.add(episode)
        s.flush()
        s.add(Job(episode_id=episode.id, downloader="pikpak_client", url="magnet:?", destination=str(old),
                  phase="done", state={}))

    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"save_dir": "26年10月/Show"})
    assert r.status_code == 200, r.text
    new = tmp_path / "lib" / "26年10月" / "Show"
    assert r.json()["moved"] == {"from": str(old), "to": str(new)}
    assert (new / "ep01.mkv").is_file() and not old.exists()
    with session_scope(factory) as s:
        assert s.scalar(select(Job)).destination == str(new)


def test_rename_refused_while_downloading(client, factory, tmp_path):
    sub = client.post("/api/subscriptions", json={"name": "Show", "bindings": []}).json()
    old = make(tmp_path / "lib" / "Show")
    with session_scope(factory) as s:
        episode = Episode(subscription_id=sub["id"], number=2, status="downloading", attempts=1)
        s.add(episode)
        s.flush()
        s.add(Job(episode_id=episode.id, downloader="pikpak_client", url="magnet:?", destination=str(old),
                  phase="running", state={}))
    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"save_dir": "Elsewhere"})
    assert r.status_code == 409 and old.is_dir()
    assert client.get(f"/api/subscriptions/{sub['id']}").json()["save_dir"] == "Show"  # rolled back


def test_rename_without_moving_or_without_old_folder(client, tmp_path):
    sub = client.post("/api/subscriptions", json={"name": "Show", "bindings": []}).json()
    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"save_dir": "A"})  # no folder yet
    assert r.status_code == 200 and r.json()["moved"] is None
    old = make(tmp_path / "lib" / "A")
    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"save_dir": "B", "move_files": False})
    assert r.json()["moved"] is None and old.is_dir() and r.json()["save_dir"] == "B"
