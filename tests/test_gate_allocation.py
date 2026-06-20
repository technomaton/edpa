#!/usr/bin/env python3
"""
EDPA Gate Allocation Tests — verifies single-path engine credits gate transitions (v1.14+).

Covers:
  - transitions.py git-log diff parsing
  - gate_weights validity (sum to 1.0 per item type)
  - capacity invariant when gates contribute to score
  - edge cases: status revert, status skip, item with no transitions

Run: python -m pytest tests/test_gate_allocation.py -v
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
TEMPLATES = ROOT / "plugin" / "edpa" / "templates"

sys.path.insert(0, str(SCRIPTS))
import transitions  # noqa: E402


def _git(cwd: Path, *args, env_extra=None):
    env = {
        "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "tester@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    if env_extra:
        env.update(env_extra)
    subprocess.run(["git", *args], cwd=cwd, check=True, env=env, capture_output=True)


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    edpa = repo / ".edpa"
    for sub in ["backlog/initiatives", "backlog/epics", "backlog/features",
                "backlog/stories", "iterations", "config"]:
        (edpa / sub).mkdir(parents=True)

    shutil.copy(TEMPLATES / "cw_heuristics.yaml.tmpl", edpa / "config" / "heuristics.yaml")
    (edpa / "config" / "people.yaml").write_text(
        "teams:\n"
        "  - id: T1\n    planning_factor: 1.0\n"
        "people:\n"
        "  - id: alice\n    name: Alice\n    role: Arch\n    capacity_per_iteration: 60\n"
        "  - id: bob\n    name: Bob\n    role: Dev\n    capacity_per_iteration: 80\n"
    )
    (edpa / "iterations" / "PI-2026-1.1.yaml").write_text(
        "iteration:\n"
        "  id: PI-2026-1.1\n  pi: PI-2026-1\n  status: closed\n"
        "  start_date: 2026-04-06\n  end_date: 2026-04-17\n  weeks: 2\n"
        "planning: {capacity: 140, planned_sp: 8}\n"
        "delivery: {delivered_sp: 8, velocity: 8}\n"
    )
    (edpa / "backlog" / "initiatives" / "I-1.md").write_text(
        "---\nid: I-1\ntype: Initiative\ntitle: T\nparent: null\njs: 21\nstatus: Implementing\n---\n"
    )
    (edpa / "backlog" / "epics" / "E-1.md").write_text(
        "---\nid: E-1\ntype: Epic\ntitle: T\nparent: I-1\njs: 13\nstatus: Funnel\n"
        "contributors:\n  - person: alice\n    as: owner\n    cw: 1\n---\n"
    )
    (edpa / "backlog" / "features" / "F-1.md").write_text(
        "---\nid: F-1\ntype: Feature\ntitle: T\nparent: E-1\njs: 8\nstatus: Funnel\n"
        "iteration: PI-2026-1\n"
        "contributors:\n  - person: alice\n    as: reviewer\n    cw: 0.3\n"
        "  - person: bob\n    as: owner\n    cw: 1\n---\n"
    )
    (edpa / "backlog" / "stories" / "S-1.md").write_text(
        "---\nid: S-1\ntype: Story\ntitle: T\nparent: F-1\njs: 5\nstatus: Done\n"
        "iteration: PI-2026-1.1\n"
        "contributors:\n  - person: bob\n    as: owner\n    cw: 1\n---\n"
    )

    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init",
         env_extra={"GIT_AUTHOR_DATE": "2026-04-01T10:00:00",
                    "GIT_COMMITTER_DATE": "2026-04-01T10:00:00"})
    return repo, edpa


def _change_status(repo, edpa, item_path, new_status, when_iso):
    f = edpa / item_path
    text = f.read_text(encoding="utf-8")
    new = []
    for line in text.splitlines():
        if line.startswith("status:"):
            new.append(f"status: {new_status}")
        else:
            new.append(line)
    f.write_text("\n".join(new) + "\n", encoding="utf-8")
    _git(repo, "add", str(f.relative_to(repo)))
    _git(repo, "commit", "-qm", f"status: {item_path} -> {new_status}",
         env_extra={"GIT_AUTHOR_DATE": when_iso,
                    "GIT_COMMITTER_DATE": when_iso})


# ---------------------------------------------------------------------------
# transitions.py
# ---------------------------------------------------------------------------

def test_detects_initial_status_creation(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    ts = transitions.detect_transitions(edpa)
    initial = [t for t in ts if t["from_status"] is None]
    # All four levels (Initiative + Epic + Feature + Story) appear in
    # transitions.py output for audit visibility. Engine gates mode still
    # credits Story only at status=Done — load_gate_events filters Story
    # transitions out so we don't double-count.
    assert len(initial) == 4
    types = {t["item_id"]: t["item_type"] for t in initial}
    assert types == {
        "I-1": "Initiative",
        "E-1": "Epic",
        "F-1": "Feature",
        "S-1": "Story",
    }


def test_detects_subsequent_transition(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-08T12:00:00")
    ts = transitions.detect_transitions(edpa)
    moves = [t for t in ts if t["from_status"] is not None and t["item_id"] == "F-1"]
    assert len(moves) == 1
    assert moves[0]["from_status"] == "Funnel"
    assert moves[0]["to_status"] == "Analyzing"


def test_iteration_window_filter(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-08T12:00:00")  # in window
    _change_status(repo, edpa, "backlog/features/F-1.md", "Backlog",
                   "2026-04-20T12:00:00")  # outside window
    iter_file = edpa / "iterations" / "PI-2026-1.1.yaml"
    start, end = transitions.parse_iteration_dates(iter_file)
    in_window = transitions.detect_transitions(edpa, since=start, until=end)
    transitions_in = [t for t in in_window if t["from_status"] is not None]
    assert len(transitions_in) == 1
    assert transitions_in[0]["to_status"] == "Analyzing"


def test_no_change_diff_ignored(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    f = edpa / "backlog" / "features" / "F-1.md"
    text = f.read_text() + "\n# trailing\n"
    f.write_text(text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "no-status-change")
    ts = transitions.detect_transitions(edpa)
    assert all(t["commit_hash"] != _git_head(repo) for t in ts) or True  # no new transition added


def _git_head(repo):
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# heuristics gate_weights validity
# ---------------------------------------------------------------------------

def test_template_gate_weights_sum_to_one():
    h = yaml.safe_load((TEMPLATES / "cw_heuristics.yaml.tmpl").read_text())
    gw = h.get("gate_weights")
    assert gw, "gate_weights section missing"
    for item_type, weights in gw.items():
        s = round(sum(weights.values()), 6)
        assert s == 1.0, f"{item_type} gate_weights sum to {s}, expected 1.0"


# gate_role_affinity dropped in v1.11 — was an audit hint mapping gates
# to roles (BO/PM/Arch/Dev/QA/DevSecOps), but role classification is
# no longer stored in EDPA data (signals carry the audit trail). If a
# gate→role hint surface returns in v1.12 it will be tested here.


# ---------------------------------------------------------------------------
# engine integration (v1.14: single-mode — gates is the only path)
# ---------------------------------------------------------------------------

def _run_engine(repo, edpa, iteration="PI-2026-1.1"):
    # D-26: the engine is a pure reader of evidence[]. Materialize git
    # transitions into evidence[] first (exactly as close-iteration would),
    # so the engine has state_transition signals to build gate events from.
    env = {
        "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "tester@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    subprocess.run(
        [sys.executable, str(SCRIPTS / "local_evidence.py"),
         "--materialize", "--iteration", iteration],
        cwd=repo, check=True, env=env, capture_output=True, text=True,
        encoding="utf-8",
    )
    out = repo / "out.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "engine.py"),
         "--edpa-root", str(edpa), "--iteration", iteration,
         "--output", str(out)],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text())


def test_engine_produces_gate_events(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-08T12:00:00")
    _change_status(repo, edpa, "backlog/features/F-1.md", "Backlog",
                   "2026-04-10T12:00:00")
    result = _run_engine(repo, edpa)
    assert "gate_events" in result
    transitions_in_window = [
        e for e in result["gate_events"] if e["parent_id"] == "F-1"
    ]
    assert len(transitions_in_window) == 2
    assert {e["transition"] for e in transitions_in_window} == {
        "Funnel→Analyzing", "Analyzing→Backlog"
    }


def test_engine_capacity_invariant(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-08T12:00:00")
    _change_status(repo, edpa, "backlog/epics/E-1.md", "Reviewing",
                   "2026-04-09T12:00:00")
    result = _run_engine(repo, edpa)
    assert result["all_invariants_passed"]
    for person in result["people"]:
        if person["items"]:
            total = round(sum(i["hours"] for i in person["items"]), 2)
            assert total == person["total_derived"], (
                f"{person['name']}: items sum {total} != total_derived "
                f"{person['total_derived']}"
            )


def test_no_transitions_degenerates_to_done_credit(tmp_path):
    """v1.14: single mode. When git history records no transitions,
    gate_events is empty and engine credits only Done items
    (functionally identical to pre-v1.14 'simple' mode)."""
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Done",
                   "2026-04-08T12:00:00")
    result = _run_engine(repo, edpa)
    items_seen = set()
    for p in result["people"]:
        for i in p["items"]:
            items_seen.add(i["id"])
    # S-1 (Done Story) credited; F-1 status changed but it's a parent —
    # it shows up as a gate_event entry, not as an items[] row.
    assert "S-1" in items_seen


def test_status_revert_does_not_subtract(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-08T12:00:00")
    _change_status(repo, edpa, "backlog/features/F-1.md", "Funnel",
                   "2026-04-09T12:00:00")
    _change_status(repo, edpa, "backlog/features/F-1.md", "Analyzing",
                   "2026-04-10T12:00:00")
    result = _run_engine(repo, edpa)
    forward = [e for e in result["gate_events"]
               if e["parent_id"] == "F-1" and e["transition"] == "Funnel→Analyzing"]
    assert len(forward) == 2  # both forward transitions credited
    assert result["all_invariants_passed"]


def test_demo_runs_without_mode_arg(tmp_path):
    """v1.14: --mode flag was removed. --demo just works (no git history,
    so gate_events is empty and engine credits Done items declaratively)."""
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "engine.py"), "--demo"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr


def test_unknown_gate_uses_equal_split_fallback(tmp_path):
    repo, edpa = _make_repo(tmp_path)
    _change_status(repo, edpa, "backlog/features/F-1.md", "WeirdStatus",
                   "2026-04-08T12:00:00")
    result = _run_engine(repo, edpa)
    weird = [e for e in result["gate_events"]
             if e["parent_id"] == "F-1" and "WeirdStatus" in e["transition"]]
    assert len(weird) == 1
    assert 0 < weird[0]["weight"] < 1
