#!/usr/bin/env python3
"""D-26 end-to-end: the engine report derives ONLY from materialized
evidence[]/contributors[], never from a live git scan.

Proves the core invariant "report == snapshot": every person/cw in
edpa_results.json is present in the item's contributors[] on disk — the
"yaml_edit credits a committer who isn't in evidence[]" divergence that
motivated D-26 can no longer happen.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    pytest.skip("PyYAML not installed", allow_module_level=True)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from _md_frontmatter import load_md, save_md_item  # noqa: E402

_BASE_ENV = {
    "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com",
    "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@example.com",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def _git(cwd, *args, env_extra=None):
    env = dict(_BASE_ENV)
    if env_extra:
        env.update(env_extra)
    subprocess.run(["git", *args], cwd=cwd, check=True, env=env,
                   capture_output=True, text=True, encoding="utf-8")


def _run(cwd, *args):
    r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r


def _setup(tmp_path):
    repo = tmp_path / "repo"
    edpa = repo / ".edpa"
    for sub in ("backlog/stories", "iterations", "config"):
        (edpa / sub).mkdir(parents=True)
    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({"people": [
        {"id": "alice", "name": "Alice", "role": "Dev",
         "email": "alice@example.com", "capacity_per_iteration": 40},
        {"id": "bob", "name": "Bob", "role": "Dev",
         "email": "bob@example.com", "capacity_per_iteration": 40},
    ]}))
    (edpa / "iterations" / "PI-2026-1.1.yaml").write_text(yaml.safe_dump({
        "iteration": {"id": "PI-2026-1.1", "pi": "PI-2026-1", "status": "closed",
                      "start_date": "2026-04-06", "end_date": "2026-04-17"}}))
    # S-1 Done, pre-seeded with alice's prior commit_author evidence.
    save_md_item(edpa / "backlog" / "stories" / "S-1.md", {
        "id": "S-1", "type": "Story", "title": "Login", "status": "Done",
        "js": 5, "iteration": "PI-2026-1.1",
        "evidence": [{"type": "commit_author", "person": "alice",
                      "weight": 2.78, "ref": "commit/seedaaa",
                      "at": "2026-04-08T09:00:00+00:00"}],
    })
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init",
         env_extra={"GIT_AUTHOR_DATE": "2026-04-06T08:00:00",
                    "GIT_COMMITTER_DATE": "2026-04-06T08:00:00"})
    return repo, edpa


def test_report_equals_materialized_snapshot(tmp_path):
    repo, edpa = _setup(tmp_path)
    p = edpa / "backlog" / "stories" / "S-1.md"

    # Bob (NOT the assignee/committer-of-record) edits S-1's YAML — the
    # "Martin Turyna" shape: a yaml_edit by the person who touched the file.
    data = load_md(p)
    data["bv"] = 3
    save_md_item(p, data)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "S-1: groom", env_extra={
        "GIT_AUTHOR_NAME": "Bob", "GIT_AUTHOR_EMAIL": "bob@example.com",
        "GIT_COMMITTER_NAME": "Bob", "GIT_COMMITTER_EMAIL": "bob@example.com",
        "GIT_AUTHOR_DATE": "2026-04-10T10:00:00",
        "GIT_COMMITTER_DATE": "2026-04-10T10:00:00"})

    # Pipeline: materialize (yaml_edit -> evidence[]) -> recompute
    # contributors[] -> run the engine.
    _run(repo, str(SCRIPTS / "local_evidence.py"),
         "--materialize", "--iteration", "PI-2026-1.1")
    _run(repo, str(SCRIPTS / "detect_contributors.py"), "--all-items")
    out = repo / "out.json"
    _run(repo, str(SCRIPTS / "engine.py"), "--edpa-root", str(edpa),
         "--iteration", "PI-2026-1.1", "--output", str(out))
    result = json.loads(out.read_text())

    s1 = load_md(p)
    ev_types = {s["type"] for s in s1["evidence"]}
    assert "yaml_edit" in ev_types          # bob's edit was materialized
    assert {s["person"] for s in s1["evidence"]} == {"alice", "bob"}

    # THE INVARIANT: every (person, cw) in the report for S-1 matches the
    # materialized contributors[] on disk — no phantom person, no divergence.
    file_cw = {c["person"]: round(c["cw"], 4) for c in s1["contributors"]}
    report_cw = {}
    for person in result["people"]:
        for it in person["items"]:
            if it["id"] == "S-1":
                report_cw[person["id"]] = round(it["cw"], 4)
    assert set(report_cw) == set(file_cw), (
        f"report persons {set(report_cw)} != snapshot {set(file_cw)}")
    for pid, cw in file_cw.items():
        assert report_cw[pid] == pytest.approx(cw, abs=0.01)
    assert result["all_invariants_passed"]
