"""Tests for ``backlog.py cmd_add --local`` (V2 local-first path).

Mirrors the GH-first suite (``test_backlog_add_gh_first.py``) but
exercises the no-gh path: ID from ``id_counter``, file written via
MCP ``edpa_item_create`` handler, no ``issue_map.yaml`` update,
no GH call. Subprocess is mocked so we can assert on the
``git add`` / ``git commit`` tail without touching a real repo.
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
import mcp_server  # noqa: E402


# --- workspace fixture -----------------------------------------------------

def _write_workspace(tmp_path: Path, *, with_sync: bool = False,
                     initiatives: list[dict] | None = None,
                     features: list[dict] | None = None) -> Path:
    """Minimal .edpa/ tree. ``with_sync=False`` is the V2 default."""
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories",
              "defects", "events", "risks"):
        (edpa / "backlog" / d).mkdir(parents=True)

    (edpa / "config" / "people.yaml").write_text(
        yaml.safe_dump({"people": [
            {"id": "alice", "name": "Alice", "role": "Dev", "fte": 1.0, "capacity": 80},
        ]})
    )

    edpa_cfg: dict = {"project": {"name": "V2 Local Test"}}
    if with_sync:
        edpa_cfg["sync"] = {
            "github_org": "octocat",
            "github_repo": "demo",
            "github_project_number": 1,
        }
    (edpa / "config" / "edpa.yaml").write_text(yaml.safe_dump(edpa_cfg))

    from _md_frontmatter import save_md
    for item in initiatives or []:
        save_md(edpa / "backlog" / "initiatives" / f"{item['id']}.md",
                item, body="")
    for item in features or []:
        save_md(edpa / "backlog" / "features" / f"{item['id']}.md",
                item, body="")
    return tmp_path


def _args(**overrides) -> argparse.Namespace:
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
    """Stub subprocess.run so ``git add`` / ``git commit`` don't hit disk."""
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    yield calls


@pytest.fixture(autouse=True)
def clear_mcp_cache():
    """MCP server keeps an LRU cache of parsed YAML; flush between tests so
    one test's writes don't leak into another's read."""
    yield
    mcp_server._load_yaml_cache_clear()


# --- happy path ------------------------------------------------------------

def test_local_initiative_no_sync_required(tmp_path, silence_git, capsys):
    """Local mode works without any sync config — the whole point of V2."""
    root = _write_workspace(tmp_path, with_sync=False)
    bl = backlog.load_backlog(root)

    backlog.cmd_add(root, bl, _args(type="Initiative", title="Platform"))

    md_file = root / ".edpa" / "backlog" / "initiatives" / "I-1.md"
    assert md_file.exists()

    from _md_frontmatter import load_md
    data = load_md(md_file)
    assert data["id"] == "I-1"
    assert data["type"] == "Initiative"
    assert data["title"] == "Platform"

    # Counter file was created and bumped.
    counter = yaml.safe_load(
        (root / ".edpa" / "config" / "id_counters.yaml").read_text()
    )
    assert counter["counters"]["Initiative"] == 1

    # Output advertises local mode.
    out = capsys.readouterr().out
    assert "local" in out.lower()
    assert "I-1" in out

    # No issue_map.yaml written.
    assert not (root / ".edpa" / "config" / "issue_map.yaml").exists()


def test_local_story_under_feature(tmp_path, silence_git):
    """Story add resolves parent via MCP handler (Feature must exist)."""
    root = _write_workspace(
        tmp_path,
        initiatives=[{"id": "I-1", "type": "Initiative", "title": "Root",
                      "status": "Funnel"}],
        features=[{"id": "F-1", "type": "Feature", "title": "Auth",
                   "status": "Funnel", "parent": "I-1"}],
    )
    bl = backlog.load_backlog(root)

    backlog.cmd_add(root, bl, _args(
        type="Story", title="Login flow", parent="F-1",
        js=5, bv=8, tc=3, rr_oe=2,
    ))

    from _md_frontmatter import load_md
    data = load_md(root / ".edpa" / "backlog" / "stories" / "S-1.md")
    assert data["parent"] == "F-1"
    assert data["js"] == 5
    assert data["wsjf"] == round((8 + 3 + 2) / 5, 2)


def test_local_writes_contributors_block(tmp_path, silence_git):
    """``--contributor PERSON:ROLE:CW`` lands in the YAML with ``as:`` field."""
    root = _write_workspace(
        tmp_path,
        initiatives=[{"id": "I-1", "type": "Initiative", "title": "Root",
                      "status": "Funnel"}],
        features=[{"id": "F-1", "type": "Feature", "title": "Auth",
                   "status": "Funnel", "parent": "I-1"}],
    )
    bl = backlog.load_backlog(root)

    backlog.cmd_add(root, bl, _args(
        type="Story", title="Login", parent="F-1", js=5,
        contributor=["alice:owner:1.0", "alice:reviewer:0.3"],
    ))

    from _md_frontmatter import load_md
    data = load_md(root / ".edpa" / "backlog" / "stories" / "S-1.md")
    assert data["contributors"] == [
        {"person": "alice", "as": "owner", "cw": 1.0},
        {"person": "alice", "as": "reviewer", "cw": 0.3},
    ]


def test_local_commits_via_git(tmp_path, silence_git):
    """Tail of cmd_add runs ``git add`` + ``git commit`` with conventional msg."""
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)

    backlog.cmd_add(root, bl, _args(type="Initiative", title="Project Apollo"))

    cmds = [tuple(c) for c in silence_git]
    assert any("add" in c for c in cmds)
    assert any(c[:2] == ("git", "commit") and
               any("feat(I-1): Project Apollo" in x for x in c)
               for c in cmds)


def test_local_id_counter_is_monotonic_across_calls(tmp_path, silence_git):
    """Sequential adds → I-1, I-2, I-3 from the local counter, no gh."""
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    for n in range(1, 4):
        backlog.cmd_add(root, bl, _args(type="Initiative", title=f"P{n}"))

    for n in range(1, 4):
        assert (root / ".edpa" / "backlog" / "initiatives" / f"I-{n}.md").exists()


# --- failure modes ---------------------------------------------------------

def test_local_invalid_type_exits(tmp_path, silence_git, capsys):
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(type="Saga", title="x"))
    assert exc.value.code == 1
    assert "ERROR" in capsys.readouterr().out


def test_local_story_without_parent_exits(tmp_path, silence_git, capsys):
    """Story requires a parent — MCP handler returns ERROR, CLI exits 1."""
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(type="Story", title="orphan"))
    assert exc.value.code == 1
    assert "parent" in capsys.readouterr().out.lower()


def test_local_parent_not_found_exits(tmp_path, silence_git, capsys):
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(
            type="Story", title="x", parent="F-999",
        ))
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().out.lower()


def test_local_bad_contributor_format_exits(tmp_path, silence_git, capsys):
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(
            type="Initiative", title="x", contributor=["malformed"],
        ))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "PERSON:ROLE:CW" in out


def test_local_bad_contributor_cw_exits(tmp_path, silence_git, capsys):
    root = _write_workspace(tmp_path)
    bl = backlog.load_backlog(root)
    with pytest.raises(SystemExit) as exc:
        backlog.cmd_add(root, bl, _args(
            type="Initiative", title="x", contributor=["alice:owner:2.5"],
        ))
    assert exc.value.code == 1
    assert "[0,1]" in capsys.readouterr().out


# --- mode selection ----------------------------------------------------------
#
# V1 dual-mode tests (test_default_path_with_sync_uses_gh_not_local,
# test_fails_without_sync_and_without_local_flag) were removed in V2.0
# (Krok 6): there is no longer a GH-first path, so there's nothing to
# fall back from. See git history at branch v1-github-coupled.
