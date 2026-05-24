"""Tests for `backlog.py cmd_add` — the strict GH-first interactive path.

These tests own the behaviours users *see*: fail-fast without sync config,
title format mirror, sub-issue link on parent, exit codes, file-on-disk
state. Subprocess is mocked at the factory level so we exercise the
whole `cmd_add` orchestration without hitting github.com.

Run: python -m pytest tests/test_backlog_add_gh_first.py -v
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import backlog  # noqa: E402
import _gh_issue_factory as fac  # noqa: E402


# --- workspace fixture -----------------------------------------------------

def _write_workspace(tmp_path: Path, *, with_sync: bool = True,
                     issue_map: dict | None = None,
                     initiatives: list[dict] | None = None) -> Path:
    """Build a minimal .edpa/ tree. `with_sync=False` omits the sync
    block so we can exercise the fail-fast branch."""
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects", "events"):
        (edpa / "backlog" / d).mkdir(parents=True)

    (edpa / "config" / "people.yaml").write_text("people: []\n")

    edpa_cfg: dict = {"project": {"name": "Test"}}
    if with_sync:
        edpa_cfg["sync"] = {
            "github_org": "octocat",
            "github_repo": "demo",
            "github_project_number": 1,
        }
    (edpa / "config" / "edpa.yaml").write_text(yaml.safe_dump(edpa_cfg))

    if issue_map is not None:
        (edpa / "config" / "issue_map.yaml").write_text(
            yaml.safe_dump(issue_map))

    # Optional seed Initiatives so parent lookups in cmd_add can find them.
    from _md_frontmatter import save_md
    for item in (initiatives or []):
        save_md(edpa / "backlog" / "initiatives" / f"{item['id']}.md",
                item, body="")
    return tmp_path


def _args(**overrides) -> argparse.Namespace:
    """argparse.Namespace mirroring `backlog.py add ...`. Anything not
    overridden defaults to None / sensible values so cmd_add doesn't trip
    on `getattr(args, x, None)` checks."""
    base = {
        "type": "Initiative",
        "parent": None,
        "title": "Untitled",
        "js": None,
        "bv": None,
        "tc": None,
        "rr_oe": None,
        "assignee": None,
        "status": "Funnel",
        "iteration": None,
        "contributor": [],
    }
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def silence_git(monkeypatch):
    """cmd_add invokes `git add` / `git commit` at the tail. We don't
    want pytest output polluted by real git calls — replace with no-op.
    Returns a list of captured argv so tests can assert on it."""
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


# --- fail-fast: no sync config --------------------------------------------

def test_fails_fast_without_sync_config(tmp_path, capsys):
    """The whole point of removing --local: bail with exit code 1 and a
    user-actionable message. No GH call, no file written.

    Uses Initiative (no parent required) so the test focuses on the
    sync gate rather than parent-existence validation."""
    root = _write_workspace(tmp_path, with_sync=False)
    bl = backlog.load_backlog(root)

    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(type="Initiative",
                                        title="needs sync"))
    assert exc.value.code == 1

    out = capsys.readouterr().out
    assert "sync is not configured" in out
    assert "edpa:setup" in out
    # Nothing on disk
    assert list((root / ".edpa" / "backlog" / "initiatives").glob("*.md")) == []


# --- happy path: Initiative (no parent) ------------------------------------

def test_initiative_create_writes_md_and_updates_issue_map(
        tmp_path, monkeypatch, silence_git):
    """The minimal flow: one Initiative, factory returns I-1, .md
    written under initiatives/, issue_map.yaml gets a fresh entry with
    node_id, no sub-issue link attempted (no parent)."""
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)

    def fake_factory(org, repo, **kw):
        assert kw["item_type"] == "Initiative"
        assert kw["raw_title"] == "Platform"
        assert kw["parent_node_id"] is None
        return {
            "issue_number": 1,
            "node_id": "NODE_I1",
            "project_item_id": "PVTI_I1",
            "url": "https://github.com/octocat/demo/issues/1",
            "edpa_id": "I-1",
            "warnings": [],
        }

    monkeypatch.setattr(fac, "create_gh_issue", fake_factory)
    monkeypatch.setattr(backlog, "_load_org_issue_type_ids", lambda org: {})

    backlog.cmd_add(root, bl, _args(type="Initiative", title="Platform"))

    md_file = root / ".edpa" / "backlog" / "initiatives" / "I-1.md"
    assert md_file.exists()

    from _md_frontmatter import load_md
    data = load_md(md_file)
    assert data["id"] == "I-1"
    assert data["type"] == "Initiative"
    assert data["title"] == "Platform"

    issue_map = yaml.safe_load(
        (root / ".edpa" / "config" / "issue_map.yaml").read_text())
    assert issue_map["items"]["I-1"] == {
        "issue_number": 1,
        "project_item_id": "PVTI_I1",
        "node_id": "NODE_I1",
    }


# --- happy path: child resolves parent node_id from issue_map -------------

def test_story_passes_parent_node_id_from_issue_map(
        tmp_path, monkeypatch, silence_git):
    """When a parent already exists in issue_map.yaml with a node_id,
    cmd_add must forward it to the factory so the sub-issue link
    happens in one pass (the PR1 bug fix)."""
    root = _write_workspace(
        tmp_path,
        issue_map={
            "github_repo": "octocat/demo",
            "github_project_number": 1,
            "items": {
                "F-3": {"issue_number": 3, "project_item_id": "PVTI_F3",
                        "node_id": "NODE_F3"},
            },
        },
        initiatives=[
            {"id": "I-1", "type": "Initiative", "title": "Root",
             "status": "Funnel", "parent": None},
        ],
    )
    # Add an F-3 file too so cmd_add's find_item parent lookup succeeds
    from _md_frontmatter import save_md
    save_md(root / ".edpa" / "backlog" / "features" / "F-3.md",
            {"id": "F-3", "type": "Feature", "title": "Auth",
             "status": "Funnel", "parent": "I-1"},
            body="")
    bl = backlog.load_backlog(root)

    captured = {}

    def fake_factory(org, repo, **kw):
        captured.update(kw)
        return {
            "issue_number": 42,
            "node_id": "NODE_S42",
            "project_item_id": "PVTI_S42",
            "url": "https://github.com/octocat/demo/issues/42",
            "edpa_id": "S-42",
            "warnings": [],
        }

    monkeypatch.setattr(fac, "create_gh_issue", fake_factory)
    monkeypatch.setattr(backlog, "_load_org_issue_type_ids", lambda org: {})

    backlog.cmd_add(root, bl, _args(type="Story", parent="F-3",
                                    title="OMOP parser"))

    assert captured["parent_node_id"] == "NODE_F3"
    assert (root / ".edpa" / "backlog" / "stories" / "S-42.md").exists()


# --- missing node_id in issue_map → warning, but item still written -------

def test_parent_without_node_id_warns_but_continues(
        tmp_path, monkeypatch, silence_git, capsys):
    """Older repos may have issue_map entries from before PR1 (no
    node_id). cmd_add must NOT crash — it warns and lets sync push
    backfill later."""
    root = _write_workspace(
        tmp_path,
        issue_map={
            "items": {
                "F-3": {"issue_number": 3, "project_item_id": "PVTI_F3"},
                # no node_id field at all
            },
        },
        initiatives=[
            {"id": "I-1", "type": "Initiative", "title": "Root",
             "status": "Funnel", "parent": None},
        ],
    )
    from _md_frontmatter import save_md
    save_md(root / ".edpa" / "backlog" / "features" / "F-3.md",
            {"id": "F-3", "type": "Feature", "title": "Auth",
             "status": "Funnel", "parent": "I-1"}, body="")
    bl = backlog.load_backlog(root)

    # Also stub the node-id graphql backfill to "" so the lookup fails
    # — exercises the "cannot link" warning branch.
    monkeypatch.setattr(fac, "_resolve_node_id", lambda *a, **kw: "")

    monkeypatch.setattr(fac, "create_gh_issue", lambda *a, **kw: {
        "issue_number": 99,
        "node_id": "NODE_99",
        "project_item_id": "P99",
        "url": "u",
        "edpa_id": "S-99",
        "warnings": [],
    })
    monkeypatch.setattr(backlog, "_load_org_issue_type_ids", lambda org: {})

    backlog.cmd_add(root, bl, _args(type="Story", parent="F-3", title="t"))

    out = capsys.readouterr().out
    assert "cannot link" in out
    assert (root / ".edpa" / "backlog" / "stories" / "S-99.md").exists()


# --- GH hard failure: no local file written --------------------------------

def test_gh_failure_aborts_without_local_state(
        tmp_path, monkeypatch, silence_git, capsys):
    """The PR1 promise: 'no local item was written so there is no drift
    to clean up'. Verify by asserting the stories directory stays empty
    after a factory exception."""
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)

    def boom(org, repo, **kw):
        raise RuntimeError("repo not found")

    monkeypatch.setattr(fac, "create_gh_issue", boom)
    monkeypatch.setattr(backlog, "_load_org_issue_type_ids", lambda org: {})

    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(type="Initiative", title="x"))
    assert exc.value.code == 1

    out = capsys.readouterr().out
    assert "repo not found" in out
    assert list((root / ".edpa" / "backlog" / "initiatives").glob("*.md")) == []
    # issue_map.yaml must NOT be written either — would leak a partial
    # entry the user has no way to reconcile.
    assert not (root / ".edpa" / "config" / "issue_map.yaml").exists()


# --- ID derivation: cmd_add trusts factory edpa_id -------------------------

def test_uses_factory_returned_edpa_id_not_local_scan(
        tmp_path, monkeypatch, silence_git):
    """A passing test for the PR1 invariant: the local file path comes
    from factory['edpa_id'], NOT from any local sequential scan. If GH
    issue is #87 then the local file is I-87.md regardless of how many
    Initiative .md files already exist."""
    root = _write_workspace(tmp_path)
    # Seed one stray Initiative so a sequential scan would suggest I-2.
    from _md_frontmatter import save_md
    save_md(root / ".edpa" / "backlog" / "initiatives" / "I-1.md",
            {"id": "I-1", "type": "Initiative", "title": "Existing",
             "status": "Funnel", "parent": None}, body="")
    bl = backlog.load_backlog(root)

    monkeypatch.setattr(fac, "create_gh_issue", lambda *a, **kw: {
        "issue_number": 87,
        "node_id": "N87",
        "project_item_id": "P87",
        "url": "u",
        "edpa_id": "I-87",
        "warnings": [],
    })
    monkeypatch.setattr(backlog, "_load_org_issue_type_ids", lambda org: {})

    backlog.cmd_add(root, bl, _args(type="Initiative", title="From GH"))

    assert (root / ".edpa" / "backlog" / "initiatives" / "I-87.md").exists()
    # Not I-2 — sequential scan must NOT be used.
    assert not (root / ".edpa" / "backlog" / "initiatives" / "I-2.md").exists()
