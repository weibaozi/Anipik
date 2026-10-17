import os
import time

from anipik import webbuild


def make_web(tmp_path):
    web = tmp_path / "web"
    (web / "src").mkdir(parents=True)
    (web / "src" / "App.vue").write_text("<template/>")
    (web / "package.json").write_text("{}")
    (web / "package-lock.json").write_text("{}")
    return web


def touch(path, offset):
    t = time.time() + offset
    os.utime(path, (t, t))


def build_dist(web, offset=0):
    (web / "dist").mkdir(exist_ok=True)
    (web / "dist" / "index.html").write_text("<html/>")
    touch(web / "dist" / "index.html", offset)


def test_stale_until_built_and_again_after_a_pull(tmp_path):
    web = make_web(tmp_path)
    assert webbuild.is_stale(web)  # never built
    build_dist(web, offset=10)
    assert not webbuild.is_stale(web)
    touch(web / "src" / "App.vue", offset=20)  # git pull rewrote a source file
    assert webbuild.is_stale(web)


def test_ensure_built_runs_install_only_when_needed(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    calls = []

    def fake_npm(args, cwd):
        calls.append(args[0] if args[0] == "install" else " ".join(args))
        if args == ["install", "--no-fund", "--no-audit"]:
            (cwd / "node_modules").mkdir(exist_ok=True)
            (cwd / "node_modules" / ".package-lock.json").write_text("{}")
            touch(cwd / "node_modules" / ".package-lock.json", 5)
        else:
            build_dist(cwd, offset=10)

    monkeypatch.setattr(webbuild, "_npm", fake_npm)
    assert webbuild.ensure_built(web) == "built" and calls == ["install", "run build"]
    assert webbuild.ensure_built(web) == "fresh" and len(calls) == 2
    touch(web / "src" / "App.vue", 20)
    assert webbuild.ensure_built(web) == "built" and calls[-1] == "run build" and calls.count("install") == 1


def test_missing_node_keeps_serving_old_build(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    build_dist(web, offset=-100)  # older than the sources
    monkeypatch.setattr(webbuild.shutil, "which", lambda name: None)
    assert webbuild.ensure_built(web) == "stale"
    assert (web / "dist" / "index.html").exists()
