"""Tests for plugin/edpa/scripts/migrate_v1_to_v2.py.

Build a tmp git repo that mimics a V1 EDPA project (sync config in
edpa.yaml, issue_map.yaml, items with GH-style IDs), run each migration
step, and verify post-conditions match the V2 layout.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import migrate_v1_to_v2 as mig  # noqa: E402
from _md_frontmatter import save_md_item, load_md  # noqa: E402


def _git(args, cwd, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True)


@pytest.fixture
def v1_repo(tmp_path: Path) -> Path:
    """Tmp repo with V1 layout: items, issue_map, sync config in edpa.yaml."""
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "t@x"], cwd=tmp_path)
    _git(["config", "user.name", "T"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)

    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (edpa / "backlog" / d).mkdir(parents=True)

    # V1 config with sync block.
    (edpa / "config" / "edpa.yaml").write_text(yaml.safe_dump({
        "project": {"name": "V1 Project"},
        "sync": {
            "github_org": "octocat",
            "github_repo": "demo",
            "github_project_number": 1,
            "field_ids": {"status": "PVTSSF_x"},
        },
    }))
    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [{"id": "alice", "name": "Alice", "role": "Dev"}],
    }))

    # V1 issue_map.yaml
    (edpa / "config" / "issue_map.yaml").write_text(yaml.safe_dump({
        "github_repo": "octocat/demo",
        "items": {
            "I-1": {"issue_number": 1, "node_id": "N1"},
            "S-5": {"issue_number": 5, "node_id": "N5"},
            "S-12": {"issue_number": 12, "node_id": "N12"},
        },
    }))

    # Items at known IDs (GH-derived numbers, gaps allowed).
    save_md_item(edpa / "backlog" / "initiatives" / "I-1.md",
                 {"id": "I-1", "type": "Initiative", "title": "Root",
                  "status": "Implementing"})
    save_md_item(edpa / "backlog" / "stories" / "S-5.md",
                 {"id": "S-5", "type": "Story", "title": "Login",
                  "status": "Implementing"})
    save_md_item(edpa / "backlog" / "stories" / "S-12.md",
                 {"id": "S-12", "type": "Story", "title": "Signup",
                  "status": "Implementing"})

    # First commit (S-5 starts in Implementing)
    _git(["add", "."], cwd=tmp_path,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-15T10:00:00+00:00"})
    _git(["commit", "-q", "-m", "v1 initial"], cwd=tmp_path,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-15T10:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-01-15T10:00:00+00:00"})

    # Second commit: flip S-5 to Done so closed_at can be backfilled
    save_md_item(edpa / "backlog" / "stories" / "S-5.md",
                 {"id": "S-5", "type": "Story", "title": "Login",
                  "status": "Done"})
    _git(["add", "."], cwd=tmp_path)
    _git(["commit", "-q", "-m", "S-5 done"], cwd=tmp_path,
         env_extra={"GIT_AUTHOR_DATE": "2026-03-01T15:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-03-01T15:00:00+00:00"})

    return tmp_path


# ---------------------------------------------------------------------------
# Individual steps
# ---------------------------------------------------------------------------

def test_seed_counters_uses_max_per_type(v1_repo: Path) -> None:
    info = mig.step_seed_counters(v1_repo)
    assert info["counters"]["Initiative"] == 1
    assert info["counters"]["Story"] == 12   # max of S-5, S-12

    parsed = yaml.safe_load(
        (v1_repo / ".edpa" / "config" / "id_counters.yaml").read_text()
    )
    assert parsed["counters"]["Story"] == 12


def test_backfill_timestamps_fills_missing_fields(v1_repo: Path) -> None:
    info = mig.step_backfill_timestamps(v1_repo)
    assert len(info["files_touched"]) > 0

    s5 = load_md(v1_repo / ".edpa/backlog/stories/S-5.md")
    assert s5["created_at"].startswith("2026-01-15")
    assert s5["updated_at"].startswith("2026-03-01")
    # closed_at should be set (status was Done at second commit)
    assert s5.get("closed_at") is not None


def test_backfill_preserves_existing_timestamps(v1_repo: Path) -> None:
    # Pre-set timestamp
    s12 = load_md(v1_repo / ".edpa/backlog/stories/S-12.md")
    s12["created_at"] = "2026-99-99T00:00:00Z"
    save_md_item(v1_repo / ".edpa/backlog/stories/S-12.md", s12)

    mig.step_backfill_timestamps(v1_repo)

    s12 = load_md(v1_repo / ".edpa/backlog/stories/S-12.md")
    assert s12["created_at"] == "2026-99-99T00:00:00Z"


def test_archive_issue_map_moves_file(v1_repo: Path) -> None:
    info = mig.step_archive_issue_map(v1_repo)
    assert info["action"] == "moved"
    assert not (v1_repo / ".edpa/config/issue_map.yaml").exists()
    assert (v1_repo / ".edpa/archive/issue_map_v1.yaml").exists()


def test_archive_issue_map_idempotent(v1_repo: Path) -> None:
    mig.step_archive_issue_map(v1_repo)
    info = mig.step_archive_issue_map(v1_repo)
    # Already-archived state — should be a no-op (no source file present).
    assert info["action"] == "skipped"


def test_strip_sync_config_removes_block(v1_repo: Path) -> None:
    info = mig.step_strip_sync_config(v1_repo)
    assert info["action"] == "stripped"
    parsed = yaml.safe_load((v1_repo / ".edpa/config/edpa.yaml").read_text())
    assert "sync" not in parsed
    assert "v1_sync_archive" in parsed
    assert parsed["v1_sync_archive"]["github_org"] == "octocat"


def test_strip_sync_config_skips_when_no_sync(v1_repo: Path) -> None:
    mig.step_strip_sync_config(v1_repo)
    info = mig.step_strip_sync_config(v1_repo)
    assert info["action"] == "skipped"


# ---------------------------------------------------------------------------
# End-to-end main()
# ---------------------------------------------------------------------------

def test_e2e_main_creates_one_commit(v1_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(v1_repo)
    monkeypatch.setattr(sys, "argv", ["migrate_v1_to_v2.py", "--skip-pull"])
    rc = mig.main()
    assert rc == 0

    # Counter file written
    assert (v1_repo / ".edpa/config/id_counters.yaml").exists()
    # issue_map archived
    assert (v1_repo / ".edpa/archive/issue_map_v1.yaml").exists()
    # edpa.yaml stripped
    parsed = yaml.safe_load((v1_repo / ".edpa/config/edpa.yaml").read_text())
    assert "sync" not in parsed
    # One migration commit
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=str(v1_repo),
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    assert "migrate from GH-coupled V1 to local-first V2" in log


def test_dry_run_writes_nothing(v1_repo: Path, monkeypatch) -> None:
    counter_before = (v1_repo / ".edpa/config/id_counters.yaml").exists()
    monkeypatch.chdir(v1_repo)
    monkeypatch.setattr(sys, "argv", ["migrate_v1_to_v2.py", "--dry-run", "--skip-pull"])
    rc = mig.main()
    assert rc == 0
    counter_after = (v1_repo / ".edpa/config/id_counters.yaml").exists()
    assert counter_before == counter_after  # neither created nor deleted
