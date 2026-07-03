"""D-52 — coarse per-project backlog write lock (``.edpa/.backlog.lock``).

``_md_frontmatter.save_md`` is atomic (tempfile + os.replace), so a crash
can't leave a torn item file — but atomic REPLACE alone doesn't stop two
writers interleaving load → mutate → save and silently dropping one side's
changes (the MCP server's write tools vs the post-commit evidence emitter
is a real single-machine pairing). ``id_counter.backlog_write_lock`` is
the shared mutex both sides take around their read-modify-write cycles.

Covers:
  - the context manager itself (acquire, release, re-acquire, timeout →
    BacklogLockTimeout with a clear message);
  - local_evidence._apply_to_item running under the lock (raises on a
    wedged lock; ad-hoc non-canonical paths stay lock-free);
  - the post-commit hook degrading with a stderr note, exit 0, no
    traceback;
  - mcp_server write handlers returning a clean ERROR result on timeout;
  - a threaded lost-update smoke test through _apply_to_item.

Run: python3 -m pytest tests/test_write_lock.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "edpa" / "scripts"))

import id_counter  # noqa: E402
import local_evidence as le  # noqa: E402
from _md_frontmatter import load_md, save_md_item  # noqa: E402
from id_counter import BacklogLockTimeout, FileLock, backlog_write_lock  # noqa: E402


# ─── Fixtures / helpers ──────────────────────────────────────────────────────


def _hold_lock(edpa_root: Path) -> FileLock:
    """Acquire the backlog lock out-of-band (same impl id_counter uses)."""
    edpa_root.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(edpa_root / ".backlog.lock"), timeout=1)
    lock.acquire()
    return lock


def _write_item(edpa_root: Path, rel_dir: str, item: dict) -> Path:
    d = edpa_root / "backlog" / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{item['id']}.md"
    save_md_item(p, item)
    return p


# ─── backlog_write_lock context manager ──────────────────────────────────────


def test_lock_acquires_creates_lockfile_and_releases(tmp_path):
    edpa = tmp_path / ".edpa"
    with backlog_write_lock(edpa):
        assert (edpa / ".backlog.lock").exists()
    # released — an immediate re-acquire with a tiny timeout must succeed
    with backlog_write_lock(edpa, timeout=0.1):
        pass


def test_lock_timeout_raises_clear_error(tmp_path):
    edpa = tmp_path / ".edpa"
    holder = _hold_lock(edpa)
    try:
        with pytest.raises(BacklogLockTimeout) as exc_info:
            with backlog_write_lock(edpa, timeout=0.15):
                pytest.fail("must not enter the critical section")
        msg = str(exc_info.value)
        assert "backlog write lock" in msg
        assert ".backlog.lock" in msg
    finally:
        holder.release()


def test_lock_timeout_is_a_timeout_error(tmp_path):
    """Callers may catch the stdlib TimeoutError family."""
    assert issubclass(BacklogLockTimeout, TimeoutError)


def test_lock_default_timeout_read_at_call_time(tmp_path, monkeypatch):
    """timeout=None resolves BACKLOG_LOCK_TIMEOUT_SEC lazily so tests (and
    operators) can shrink it without re-importing every consumer."""
    monkeypatch.setattr(id_counter, "BACKLOG_LOCK_TIMEOUT_SEC", 0.1)
    edpa = tmp_path / ".edpa"
    holder = _hold_lock(edpa)
    try:
        with pytest.raises(BacklogLockTimeout):
            with backlog_write_lock(edpa):
                pass
    finally:
        holder.release()


def test_lock_released_when_body_raises(tmp_path):
    edpa = tmp_path / ".edpa"
    with pytest.raises(RuntimeError):
        with backlog_write_lock(edpa):
            raise RuntimeError("boom")
    with backlog_write_lock(edpa, timeout=0.1):
        pass  # not wedged by the failed body


# ─── local_evidence._apply_to_item under the lock ────────────────────────────


def test_lock_root_resolved_from_canonical_item_path(tmp_path):
    edpa = tmp_path / "proj" / ".edpa"
    p = edpa / "backlog" / "stories" / "S-1.md"
    assert le._lock_root_for_item(p) == edpa.resolve()


def test_lock_root_none_for_ad_hoc_path(tmp_path):
    assert le._lock_root_for_item(tmp_path / "S-1.md") is None


def test_apply_to_item_locks_canonical_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(id_counter, "BACKLOG_LOCK_TIMEOUT_SEC", 0.15)
    edpa = tmp_path / ".edpa"
    item_path = _write_item(edpa, "stories",
                            {"id": "S-1", "type": "Story", "title": "t",
                             "status": "Implementing"})
    holder = _hold_lock(edpa)
    try:
        with pytest.raises(BacklogLockTimeout):
            le._apply_to_item(item_path, [{"type": "commit_author",
                                           "person": "alice", "weight": 4,
                                           "ref": "commit/abc1234"}])
    finally:
        holder.release()
    # nothing was written while the lock was held
    assert "evidence" not in (load_md(item_path) or {})
    # and the same call succeeds once the lock is free
    assert le._apply_to_item(item_path, [{"type": "commit_author",
                                          "person": "alice", "weight": 4,
                                          "ref": "commit/abc1234"}])
    assert (load_md(item_path) or {}).get("evidence")


def test_apply_to_item_ad_hoc_path_writes_unlocked(tmp_path):
    """Non-canonical layouts (unit-test scratch files) keep pre-lock
    behaviour: no lock dir is invented next to arbitrary paths."""
    p = tmp_path / "S-9.md"
    save_md_item(p, {"id": "S-9", "type": "Story", "title": "t"})
    assert le._apply_to_item(p, [{"type": "commit_author", "person": "a",
                                  "weight": 1, "ref": "commit/fff0000"}])
    assert not (tmp_path / ".backlog.lock").exists()


def test_concurrent_apply_to_item_no_lost_update(tmp_path):
    """Two threads merging different refs into the same item must both
    land — the lock serializes the load→mutate→save cycles."""
    edpa = tmp_path / ".edpa"
    item_path = _write_item(edpa, "stories",
                            {"id": "S-1", "type": "Story", "title": "t",
                             "status": "Implementing"})
    n_each = 8
    errors: list[BaseException] = []

    def writer(person: str) -> None:
        try:
            for i in range(n_each):
                le._apply_to_item(item_path, [{
                    "type": "commit_author", "person": person, "weight": 4,
                    "ref": f"commit/{person}-{i}",
                }])
        except BaseException as exc:  # noqa: BLE001 — surface in main thread
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(p,))
               for p in ("alice", "bob")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    refs = {s["ref"] for s in (load_md(item_path) or {}).get("evidence", [])}
    expected = {f"commit/{p}-{i}" for p in ("alice", "bob")
                for i in range(n_each)}
    assert refs == expected, f"lost update: missing {expected - refs}"


# ─── post-commit hook degrades cleanly ───────────────────────────────────────


def _git(args, cwd, env_extra=None):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "alice@example.dev"], cwd=tmp_path)
    _git(["config", "user.name", "Alice Senior"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [{"id": "alice", "name": "Alice Senior",
                    "email": "alice@example.dev"}],
    }), encoding="utf-8")
    _write_item(edpa, "stories", {"id": "S-1", "type": "Story",
                                  "title": "Login", "status": "Implementing"})
    _git(["add", "."], cwd=tmp_path)
    _git(["commit", "-q", "-m", "init"], cwd=tmp_path)
    return tmp_path


def test_hook_mode_skips_with_note_on_wedged_lock(repo, monkeypatch, capsys):
    """Hook mode must never wedge or traceback: the user's commit already
    succeeded. On lock timeout it prints a clear note pointing at
    --materialize and exits 0."""
    monkeypatch.setattr(id_counter, "BACKLOG_LOCK_TIMEOUT_SEC", 0.15)
    (repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "src.py"], cwd=repo)
    _git(["commit", "-q", "-m", "feat(S-1): work"], cwd=repo)

    holder = _hold_lock(repo / ".edpa")
    monkeypatch.chdir(repo)
    try:
        rc = le.main([])
    finally:
        holder.release()
    assert rc == 0
    err = capsys.readouterr().err
    assert "backlog write lock" in err
    assert "--materialize" in err
    # nothing landed on the item while the lock was wedged
    item = load_md(repo / ".edpa" / "backlog" / "stories" / "S-1.md") or {}
    assert not any("commit_author" == s.get("type")
                   for s in item.get("evidence") or [])


# ─── MCP write handlers return a clean ERROR on timeout ─────────────────────


@pytest.fixture
def mcp_server():
    import importlib
    return importlib.import_module("mcp_server")


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    edpa = tmp_path / ".edpa"
    _write_item(edpa, "stories", {"id": "S-1", "type": "Story",
                                  "title": "Login", "status": "Implementing",
                                  "js": 3, "bv": 0, "tc": 0, "rr_oe": 0})
    return edpa


def test_item_update_returns_error_on_wedged_lock(mcp_server, edpa_root,
                                                  monkeypatch):
    monkeypatch.setattr(id_counter, "BACKLOG_LOCK_TIMEOUT_SEC", 0.15)
    holder = _hold_lock(edpa_root)
    try:
        result = mcp_server._handle_item_update(
            edpa_root, {"item_id": "S-1", "fields": {"js": 5}})
    finally:
        holder.release()
    assert result[0].text.startswith("ERROR")
    assert "backlog write lock" in result[0].text
    # the item was left untouched
    item = load_md(edpa_root / "backlog" / "stories" / "S-1.md") or {}
    assert item.get("js") == 3


def test_item_create_returns_error_on_wedged_lock(mcp_server, tmp_path,
                                                  monkeypatch):
    monkeypatch.setattr(id_counter, "BACKLOG_LOCK_TIMEOUT_SEC", 0.15)
    edpa = tmp_path / ".edpa"
    (edpa / "backlog" / "defects").mkdir(parents=True)
    holder = _hold_lock(edpa)
    try:
        result = mcp_server._handle_item_create(
            edpa, {"type": "Defect", "title": "boom"})
    finally:
        holder.release()
    assert result[0].text.startswith("ERROR")
    assert "backlog write lock" in result[0].text
    assert not list((edpa / "backlog" / "defects").glob("*.md"))


def test_item_update_succeeds_when_lock_free(mcp_server, edpa_root):
    result = mcp_server._handle_item_update(
        edpa_root, {"item_id": "S-1", "fields": {"js": 5}})
    assert not result[0].text.startswith("ERROR")
    item = load_md(edpa_root / "backlog" / "stories" / "S-1.md") or {}
    assert item.get("js") == 5
    # lock is not left dangling — an immediate explicit acquire succeeds
    with backlog_write_lock(edpa_root, timeout=0.1):
        pass
