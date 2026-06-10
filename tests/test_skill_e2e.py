#!/usr/bin/env python3
"""
EDPA Skill-driven E2E — Layer 3 of ``docs/E2E-SKILLS-TEST-PLAN.md`` Příloha D.

Drives EDPA skills/commands through ``claude -p`` (headless Claude Code) inside a
throwaway git sandbox and asserts on **side effects** — filesystem state + the
git audit trail — NOT on the assistant's prose. LLM nondeterminism makes
transcript matching flaky ("Project name?" one week, "What's the project name?"
the next); outcomes ("the ``.md`` exists and a ``feat(S-N):`` commit landed") are
stable across runs.

The plugin under test is the **working tree** (``--plugin-dir <repo>/plugin``),
not whatever stale version is installed in ``~/.claude/plugins`` — so a regression
in the repo is caught before release, independent of the developer's installed
copy.

Opt-in only. These spawn real Claude Code (API cost + minutes of wall time), so
they auto-skip unless BOTH:

  * env ``EDPA_SKILL_E2E=1``
  * ``claude`` on PATH

That keeps the default ``pytest -m "not e2e"`` and the ``test.yml`` CI workflow
green and cost-free (no API key needed in CI — the env gate skips collection).

Run::

    EDPA_SKILL_E2E=1 pytest tests/test_skill_e2e.py -v
    EDPA_SKILL_E2E=1 EDPA_SKILL_E2E_KEEP=1 pytest tests/test_skill_e2e.py -v -s   # keep + show sandbox path

Marker: ``skill_e2e`` (registered in ``pytest.ini``) → ``pytest -m skill_e2e``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a dev dependency
    pytest.skip("PyYAML not installed", allow_module_level=True)

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin"
CLAUDE = shutil.which("claude")

pytestmark = pytest.mark.skill_e2e

# ── opt-in gate (skips at collection time → CI / default runs never spawn claude)
if not os.environ.get("EDPA_SKILL_E2E"):
    pytest.skip(
        "skill-E2E is opt-in — set EDPA_SKILL_E2E=1 to run (spawns real `claude -p`)",
        allow_module_level=True,
    )
if CLAUDE is None:
    pytest.skip("`claude` CLI not on PATH", allow_module_level=True)

# Wall-clock ceiling for a single `claude -p` skill invocation. close-iteration
# is the slowest (engine + reports + several model turns); bump via env if needed.
CLAUDE_TIMEOUT = int(os.environ.get("EDPA_SKILL_E2E_TIMEOUT", "360"))
KEEP = bool(os.environ.get("EDPA_SKILL_E2E_KEEP"))


# ── helpers ──────────────────────────────────────────────────────────────────
def claude_run(prompt: str, cwd: Path, *, timeout: int = CLAUDE_TIMEOUT
               ) -> subprocess.CompletedProcess:
    """Drive the working-tree EDPA plugin headlessly in ``cwd``.

    Outcome-based: callers assert on disk/git effects in ``cwd``, not on stdout.
    ``EDPA_LOG_FILE`` is set so MCP tool dispatch (``call_tool name=…``) can be
    grepped if a test wants to prove a skill used MCP over ``Bash + grep``.
    """
    env = dict(os.environ)
    env.setdefault("EDPA_LOG_FILE", str(cwd / "_mcp.log"))
    return subprocess.run(
        [
            CLAUDE, "-p", prompt,
            "--plugin-dir", str(PLUGIN),
            "--permission-mode", "bypassPermissions",
            "--output-format", "text",
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout.strip()


def _ids_in(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.md")}


def _backlog_add(proj: Path, type_dir: Path, *args: str) -> str:
    """Create one item via the vendored ``backlog.py add`` (deterministic, free,
    auto-commits ``feat(ID):``). Returns the newly allocated ID by diffing the
    directory — never parses the ANSI-coloured stdout."""
    before = _ids_in(type_dir)
    r = subprocess.run(
        [sys.executable, str(proj / ".edpa/engine/scripts/backlog.py"), "add", *args],
        cwd=str(proj), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"backlog.py add {args} failed:\n{r.stderr}"
    new = _ids_in(type_dir) - before
    assert len(new) == 1, f"expected exactly one new item under {type_dir.name}, got {new}"
    return new.pop()


def _tail(text: str, n: int = 800) -> str:
    return text[-n:] if text else "<empty>"


# ── fixture: one sandboxed, /edpa:setup-initialized project for the module ────
@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    proj = tmp_path_factory.mktemp("skill-e2e")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.email", "e2e@test.local"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.name", "Skill E2E"], cwd=proj, check=True)
    (proj / "README.md").write_text("# skill-e2e sandbox\n")
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-qm", "chore: init sandbox"], cwd=proj, check=True)

    if KEEP:
        print(f"\n[skill-e2e] sandbox: {proj}")

    # The one expensive shared step: bootstrap via the real setup skill.
    r = claude_run("/edpa:setup", cwd=proj)
    if r.returncode != 0 or not (proj / ".edpa/engine/scripts").is_dir():
        pytest.fail(
            f"/edpa:setup did not initialize the project (rc={r.returncode}).\n"
            f"stdout tail:\n{_tail(r.stdout)}\nstderr tail:\n{_tail(r.stderr, 400)}"
        )
    yield proj
    if not KEEP:
        shutil.rmtree(proj, ignore_errors=True)


# ── flow 1: /edpa:setup — engine vendored + configs seeded ───────────────────
def test_setup_vendors_engine_and_seeds_configs(project: Path):
    edpa = project / ".edpa"
    assert (edpa / "engine/VERSION").is_file(), "engine VERSION not vendored"

    n_scripts = len(list((edpa / "engine/scripts").glob("*.py")))
    assert n_scripts >= 40, f"expected the engine vendored, only {n_scripts} scripts present"

    for cfg in ("edpa.yaml", "people.yaml", "cw_heuristics.yaml", "id_counters.yaml"):
        assert (edpa / "config" / cfg).is_file(), f"setup did not seed .edpa/config/{cfg}"

    # VERSION must match the working-tree plugin — proves --plugin-dir loaded the
    # repo under test, not the (older) installed cache.
    plugin_ver = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())["version"]
    assert (edpa / "engine/VERSION").read_text().strip() == plugin_ver, (
        "vendored engine VERSION != working-tree plugin version — "
        "--plugin-dir is not loading the repo under test"
    )


# ── flow 2: /edpa:add — allocates ID from id_counters.yaml + auto-commits ─────
def test_add_story_allocates_id_and_autocommits(project: Path):
    bl = project / ".edpa/backlog"
    # Deterministic parent chain via the vendored script (the skill-under-test is
    # only the Story add). Initiative → Epic → Feature.
    init_id = _backlog_add(project, bl / "initiatives", "--type", "Initiative",
                           "--title", "Add-flow root")
    epic_id = _backlog_add(project, bl / "epics", "--type", "Epic",
                           "--title", "Add-flow epic", "--parent", init_id)
    feat_id = _backlog_add(project, bl / "features", "--type", "Feature",
                           "--title", "Add-flow feature", "--parent", epic_id, "--js", "5")

    stories = bl / "stories"
    before = _ids_in(stories)
    r = claude_run(
        f'/edpa:add Story "Skill-driven story" --parent {feat_id} --js 5', cwd=project
    )
    assert r.returncode == 0, f"/edpa:add failed (rc={r.returncode}):\n{_tail(r.stdout)}"

    created = _ids_in(stories) - before
    assert len(created) == 1, (
        f"expected exactly one new Story file, got {created}.\n"
        f"stdout tail:\n{_tail(r.stdout)}"
    )
    story_id = created.pop()
    # The skill must allocate from id_counters, never invent an ID.
    assert re.fullmatch(r"S-\d+", story_id), f"invalid Story ID shape: {story_id!r}"

    # The add path auto-commits `feat(<ID>): <title>` — it must be HEAD.
    head_subject = _git(project, "log", "-1", "--format=%s")
    assert head_subject.startswith(f"feat({story_id}):"), (
        f"HEAD is not the Story auto-commit: {head_subject!r}"
    )

    # And the written file's frontmatter id must match its filename + the parent.
    fm = yaml.safe_load((stories / f"{story_id}.md").read_text().split("---")[1])
    assert fm["id"] == story_id and fm["parent"] == feat_id


# ── flow 3: /edpa:close-iteration — engine runs, invariant holds, reports land ─
def _plant_closeable_iteration(proj: Path, owner: str,
                               iter_id: str = "PI-2099-9.9", pi: str = "PI-2099-9") -> str:
    """Plant a minimal closeable backlog (high IDs to avoid colliding with the
    add-flow's counter-allocated items) + an active iteration. Mirrors the proven
    seed in test_e2e_install.py so the engine's `Σ hours == capacity` holds."""
    bl = proj / ".edpa/backlog"
    (bl / "initiatives/I-900.md").write_text(
        "---\nid: I-900\ntype: Initiative\ntitle: Close-flow root\nparent: null\n---\n")
    (bl / "epics/E-900.md").write_text(
        "---\nid: E-900\ntype: Epic\ntitle: Close-flow epic\nparent: I-900\n---\n")
    (bl / "features/F-900.md").write_text(
        "---\nid: F-900\ntype: Feature\ntitle: Close-flow feature\nparent: E-900\njs: 5\n---\n")
    (bl / "stories/S-900.md").write_text(
        "---\nid: S-900\ntype: Story\ntitle: Close-flow story\nparent: F-900\njs: 5\n"
        f"status: Done\niteration: {iter_id}\n"
        f"contributors:\n  - person: {owner}\n    as: owner\n    cw: 1\n---\n"
    )
    (proj / ".edpa/iterations" / f"{iter_id}.yaml").write_text(
        "iteration:\n"
        f"  id: {iter_id}\n"
        f"  pi: {pi}\n"
        "  status: active\n"
        "  start_date: 2099-01-05\n"
        "  end_date: 2099-01-16\n"
        "  weeks: 2\n"
        "planning:\n"
        "  capacity: 40\n"
        "  planned_sp: 5\n"
        "delivery:\n"
        "  delivered_sp: 5\n"
        "  velocity: 5\n"
    )
    return iter_id


def test_close_iteration_runs_engine_and_reports(project: Path):
    # Attribute to whoever setup seeded as the first person (template: example-arch).
    people = yaml.safe_load((project / ".edpa/config/people.yaml").read_text())
    owner = people["people"][0]["id"]

    iter_id = _plant_closeable_iteration(project, owner)
    # Commit the plant so the skill's own auto-commits see a clean tree. The
    # synthetic high IDs + a ticket-less subject would trip the ID-safety and
    # ticket-attached hooks the sandbox installs — those guard real backlog work,
    # not test fixtures, so --no-verify is the right escape here.
    subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
    subprocess.run(["git", "commit", "--no-verify", "-qm", "no-ticket: plant closeable iteration"],
                   cwd=str(project), check=True)

    r = claude_run(f"/edpa:close-iteration {iter_id} --skip-prep", cwd=project)
    assert r.returncode == 0, f"close-iteration failed (rc={r.returncode}):\n{_tail(r.stdout)}"

    rpt_dir = project / ".edpa/reports" / f"iteration-{iter_id}"
    results = rpt_dir / "edpa_results.json"
    assert results.is_file(), (
        f"engine produced no edpa_results.json at {results}.\nstdout tail:\n{_tail(r.stdout)}"
    )

    data = json.loads(results.read_text())
    people_results = data.get("people") or []
    assert people_results, f"engine returned no per-person results: {data}"
    # The engine's own `Σ hours == capacity` verdict — the canonical invariant.
    assert data.get("all_invariants_passed") is True, f"engine invariants failed: {data}"
    assert (data.get("team_total") or 0) > 0, \
        f"engine derived 0 hours — contributors[] likely not read: {data}"

    # The reports stage (not just the engine) must have run: per-person/team
    # timesheets + a frozen audit snapshot.
    timesheets = list(rpt_dir.glob("timesheet-*.md"))
    assert timesheets, f"reports stage produced no timesheet-*.md in {rpt_dir}"
    assert (project / ".edpa/snapshots" / f"{iter_id}.json").is_file(), \
        "reports stage did not freeze a snapshot"
