"""Tests for S-241 reconcile.py — git evidence vs backlog status reconciliation.

Covers:
  - collect_evidence: CC-scope + bare subject IDs, body mentions DON'T count,
    auto-prefixed commits (chore(evidence):, Merge) never count
  - build_report suggestion rules: stale evidence → Done (with closed_at from
    the evidence commit), fresh evidence + pre-Implementing → Implementing,
    release-tag containment → Done even when fresh, Feature never → Done,
    Done+evidence → clean, Done without evidence → phantom, Risk ignored
  - apply_suggestions: writes status (+closed_at once), second run is a no-op
  - --check exit semantics via build_report drift flag
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from _md_frontmatter import load_md  # noqa: E402
from reconcile import (  # noqa: E402
    apply_suggestions,
    build_report,
    collect_evidence,
)

OLD = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
    "%Y-%m-%dT%H:%M:%S+00:00")


def git(repo: Path, *args: str, date: str | None = None) -> None:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "HOME": str(repo), "PATH": __import__("os").environ["PATH"]}
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=env)


def write_item(edpa: Path, sub: str, iid: str, itype: str, status: str,
               closed_at: str | None = None) -> Path:
    d = edpa / "backlog" / sub
    d.mkdir(parents=True, exist_ok=True)
    extra = f"\nclosed_at: '{closed_at}'" if closed_at else ""
    (d / f"{iid}.md").write_text(
        f"---\nid: {iid}\ntype: {itype}\ntitle: {iid} title\n"
        f"status: {status}\njs: 3{extra}\n---\n\nbody\n",
        encoding="utf-8")
    return d / f"{iid}.md"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    edpa = tmp_path / ".edpa"
    # Items
    write_item(edpa, "stories", "S-1", "Story", "Funnel")        # old commit → Done
    write_item(edpa, "stories", "S-2", "Story", "Funnel")        # fresh commit → Implementing
    write_item(edpa, "stories", "S-3", "Story", "Done",
               closed_at="2026-01-01T00:00:00Z")                  # evidenced → clean
    write_item(edpa, "stories", "S-4", "Story", "Done")          # no evidence → phantom
    write_item(edpa, "stories", "S-5", "Story", "Funnel")        # only auto-prefix → untouched
    write_item(edpa, "stories", "S-6", "Story", "Funnel")        # only body mention → untouched
    write_item(edpa, "stories", "S-7", "Story", "Funnel")        # fresh but tagged → Done
    write_item(edpa, "defects", "D-1", "Defect", "Backlog")      # old commit → Done
    write_item(edpa, "features", "F-1", "Feature", "Funnel")     # old commit → Implementing only
    write_item(edpa, "risks", "R-1", "Risk", "Funnel")           # ignored type
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "seed backlog", date=OLD)
    # Evidence commits
    (tmp_path / "a.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "feat(S-1): implement thing", date=OLD)
    (tmp_path / "c.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "feat(S-3): shipped earlier", date=OLD)
    (tmp_path / "d.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "chore(evidence): S-5 from abc123", date=OLD)
    (tmp_path / "e.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "no-ticket: unrelated\n\ntalks about S-6 in the body only", date=OLD)
    (tmp_path / "f.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "feat(S-7): fresh but released")
    git(tmp_path, "tag", "v9.9.9")
    # S-2's evidence lands AFTER the tag: fresh + unreleased → Implementing.
    # (A tag contains all ancestor commits, so any pre-tag evidence counts as
    # released — that containment IS the intended Done signal.)
    (tmp_path / "b.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "fix(S-2): fresh fix")
    (tmp_path / "g.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "fix(D-1): old defect fix", date=OLD)
    (tmp_path / "h.txt").write_text("1")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-q", "-m",
        "feat(F-1): feature-level work", date=OLD)
    return tmp_path


def by_id(rows: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in rows}


def test_collect_evidence_subject_scope_only(repo: Path):
    ev = collect_evidence(repo, "main")
    assert "S-1" in ev and "S-2" in ev and "D-1" in ev
    assert "S-5" not in ev, "chore(evidence) auto-prefix must not count"
    assert "S-6" not in ev, "body-only mention must not count"


def test_build_report_suggestions(repo: Path):
    rep = build_report(repo, repo / ".edpa", "main")
    stuck = by_id(rep["stuck"])

    assert stuck["S-1"]["suggested"] == "Done"
    assert stuck["S-1"]["closed_at"] is not None
    assert stuck["S-2"]["suggested"] == "Implementing"
    assert stuck["S-2"]["closed_at"] is None
    assert stuck["S-7"]["suggested"] == "Done"
    assert stuck["S-7"]["reason"] == "evidence in release tag"
    assert stuck["D-1"]["suggested"] == "Done"
    assert stuck["F-1"]["suggested"] == "Implementing", \
        "Feature must never be auto-suggested Done"
    assert "S-3" not in stuck and "S-5" not in stuck and "S-6" not in stuck
    assert "R-1" not in stuck, "Risk is not delivery-tracked"

    phantoms = by_id(rep["phantoms"])
    assert "S-4" in phantoms
    assert "S-3" not in phantoms
    assert rep["drift"] is True


def test_closed_at_matches_evidence_commit(repo: Path):
    rep = build_report(repo, repo / ".edpa", "main")
    s1 = by_id(rep["stuck"])["S-1"]
    got = datetime.strptime(s1["closed_at"], "%Y-%m-%dT%H:%M:%SZ")
    want = datetime.strptime(OLD, "%Y-%m-%dT%H:%M:%S+00:00")
    assert abs((got - want).total_seconds()) < 2


def test_apply_then_idempotent(repo: Path):
    edpa = repo / ".edpa"
    rep = build_report(repo, edpa, "main")
    n = apply_suggestions(rep)
    assert n == len(rep["stuck"]) >= 4

    s1 = load_md(edpa / "backlog" / "stories" / "S-1.md")
    assert s1["status"] == "Done"
    assert s1["closed_at"]
    s2 = load_md(edpa / "backlog" / "stories" / "S-2.md")
    assert s2["status"] == "Implementing"
    assert not s2.get("closed_at")
    f1 = load_md(edpa / "backlog" / "features" / "F-1.md")
    assert f1["status"] == "Implementing"

    rep2 = build_report(repo, edpa, "main")
    ids2 = set(by_id(rep2["stuck"]))
    # S-1/S-7/D-1 are Done now; S-2/F-1 Implementing with fresh-or-old evidence:
    # S-2 fresh+Implementing → clean; F-1 old evidence but hint-only type already
    # at Implementing → clean. Nothing left.
    assert not ids2, f"second run must be clean, got {ids2}"
    assert rep2["drift"] is False


def test_existing_closed_at_not_overwritten(repo: Path):
    edpa = repo / ".edpa"
    # force S-3 into stuck by rewriting status (keep closed_at)
    p = edpa / "backlog" / "stories" / "S-3.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "status: Done", "status: Funnel"), encoding="utf-8")
    rep = build_report(repo, edpa, "main")
    assert by_id(rep["stuck"])["S-3"]["suggested"] == "Done"
    apply_suggestions(rep)
    after = load_md(p)
    assert after["status"] == "Done"
    assert after["closed_at"] == "2026-01-01T00:00:00Z", \
        "pre-existing closed_at must be preserved"
