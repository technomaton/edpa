#!/usr/bin/env python3
"""
EDPA E2E Install Test

Verifies that a clean project can install EDPA, plant minimal data,
and run the full pipeline (engine + traceability + pi_close + velocity)
without any root-level pollution and without depending on the source
repo's own .edpa/ data.

Mirrors the manual /tmp/edpa-clean-test workflow as an automated check.

Run: python -m pytest tests/test_e2e_install.py -v
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)


ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SRC = ROOT / "plugin"
TEMPLATE_DIR = PLUGIN_SRC / "edpa" / "templates"

ALLOWED_ROOT_ENTRIES = {".claude", ".edpa", ".git", "README.md"}


def _install_plugin(target: Path):
    """Replicate install.sh behaviour using local source — no network.

    v1.18.4+: engine vendors to `.edpa/engine/` (not `.claude/edpa/`).
    `.github/workflows/` install is delegated to /edpa:setup; install.sh
    itself only handles the engine + `.edpa/` data tree.
    """
    engine = target / ".edpa" / "engine"
    engine.mkdir(parents=True)
    for sub in ("scripts", "schemas", "templates"):
        shutil.copytree(PLUGIN_SRC / "edpa" / sub, engine / sub)
    plugin_version = json.loads((PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text())["version"]
    (engine / "VERSION").write_text(plugin_version + "\n")

    edpa = target / ".edpa"
    for sub in [
        "config", "iterations", "reports", "snapshots", "data",
        "backlog/initiatives", "backlog/epics", "backlog/features", "backlog/stories",
    ]:
        (edpa / sub).mkdir(parents=True, exist_ok=True)

    # Seed templates: people.yaml + edpa.yaml. Engine reads canonical CW
    # heuristics from .edpa/engine/templates/cw_heuristics.yaml.tmpl
    # directly — no .edpa/config/heuristics.yaml is needed.
    shutil.copy(TEMPLATE_DIR / "people.yaml.tmpl", edpa / "config" / "people.yaml")
    shutil.copy(TEMPLATE_DIR / "edpa.yaml.tmpl", edpa / "config" / "edpa.yaml")


def _plant_minimal_backlog(target: Path):
    backlog = target / ".edpa" / "backlog"
    (backlog / "initiatives" / "I-1.md").write_text(
        "---\nid: I-1\ntype: Initiative\ntitle: T\nparent: null\n---\n"
    )
    (backlog / "epics" / "E-1.md").write_text(
        "---\nid: E-1\ntype: Epic\ntitle: T\nparent: I-1\n---\n"
    )
    (backlog / "features" / "F-1.md").write_text(
        "---\nid: F-1\ntype: Feature\ntitle: T\nparent: E-1\njs: 5\n---\n"
    )
    (backlog / "stories" / "S-1.md").write_text(
        "---\nid: S-1\ntype: Story\ntitle: T\nparent: F-1\njs: 5\n"
        "status: Done\niteration: PI-2026-1.1\n"
        "contributors:\n  - person: example-arch\n    as: owner\n    cw: 1\n"
        "---\n"
    )
    (target / ".edpa" / "iterations" / "PI-2026-1.1.yaml").write_text(
        "iteration:\n"
        "  id: PI-2026-1.1\n"
        "  pi: PI-2026-1\n"
        "  status: closed\n"
        "  start_date: 2026-01-05\n"
        "  end_date: 2026-01-16\n"
        "  weeks: 2\n"
        "planning:\n"
        "  capacity: 40\n"
        "  planned_sp: 5\n"
        "delivery:\n"
        "  delivered_sp: 5\n"
        "  velocity: 5\n"
    )


def _run(target: Path, *args):
    return subprocess.run(
        [sys.executable, str(target / ".edpa" / "engine" / "scripts" / args[0]), *args[1:]],
        cwd=target, capture_output=True, text=True, encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "README.md").write_text("# Test\n")
    _install_plugin(proj)
    return proj


def test_install_creates_only_dot_directories(project):
    """install must not create any root-level non-dot entries beyond README."""
    actual = {p.name for p in project.iterdir()}
    extras = actual - ALLOWED_ROOT_ENTRIES
    assert not extras, f"unexpected root entries after install: {extras}"


def test_install_vendors_engine_under_edpa(project):
    """Engine (scripts + schemas + templates) lives in .edpa/engine/."""
    engine = project / ".edpa" / "engine"
    assert engine.is_dir()
    assert (engine / "VERSION").is_file()
    for sub in ("scripts", "schemas", "templates"):
        assert (engine / sub).is_dir(), f"missing .edpa/engine/{sub}/"


def test_install_includes_new_action_scripts(project):
    scripts = project / ".edpa" / "engine" / "scripts"
    for name in ("traceability.py", "pi_close.py", "velocity.py"):
        assert (scripts / name).is_file(), f"missing script: {name}"


def test_traceability_passes_on_valid_backlog(project):
    _plant_minimal_backlog(project)
    r = _run(project, "traceability.py")
    assert r.returncode == 0, r.stderr
    assert "All parent chains valid" in r.stdout


def test_traceability_fails_on_orphan(project):
    _plant_minimal_backlog(project)
    (project / ".edpa" / "backlog" / "stories" / "S-ORPHAN.md").write_text(
        "---\nid: S-ORPHAN\ntype: Story\ntitle: bad\n---\n"
    )
    r = _run(project, "traceability.py")
    assert r.returncode == 1
    assert "S-ORPHAN" in r.stdout


def test_pi_close_aggregates_iteration(project):
    _plant_minimal_backlog(project)
    r = _run(project, "pi_close.py", "--pi", "PI-2026-1")
    assert r.returncode == 0, r.stderr
    results = json.loads(
        (project / ".edpa" / "reports" / "pi-PI-2026-1" / "pi_results.json").read_text()
    )
    assert results["summary"]["total_delivered_sp"] == 5
    assert results["summary"]["avg_predictability_pct"] == 100.0


def test_velocity_writes_report(project):
    _plant_minimal_backlog(project)
    r = _run(project, "velocity.py")
    assert r.returncode == 0, r.stderr
    report = json.loads(
        (project / ".edpa" / "reports" / "velocity" / "velocity.json").read_text()
    )
    assert report["iteration_count"] == 1
    assert report["average_velocity"] == 5


def test_engine_runs_with_template_people(project):
    _plant_minimal_backlog(project)
    r = subprocess.run(
        [sys.executable, str(project / ".edpa" / "engine" / "scripts" / "engine.py"),
         "--edpa-root", str(project / ".edpa"),
         "--iteration", "PI-2026-1.1"],
        cwd=project, capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    assert "All invariants passed: YES" in r.stdout
    assert (project / ".edpa" / "reports" / "iteration-PI-2026-1.1" / "edpa_results.json").is_file()


def test_no_root_pollution_after_full_pipeline(project):
    _plant_minimal_backlog(project)
    _run(project, "traceability.py")
    _run(project, "pi_close.py", "--pi", "PI-2026-1")
    _run(project, "velocity.py")
    actual = {p.name for p in project.iterdir()}
    extras = actual - ALLOWED_ROOT_ENTRIES
    assert not extras, f"pipeline created root-level entries: {extras}"


def test_plugin_code_does_not_reference_source_repo(project):
    """No script may resolve paths back into the EDPA source repo."""
    forbidden = str(ROOT.resolve())
    scripts = project / ".claude" / "edpa" / "scripts"
    for py in scripts.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert forbidden not in text, f"{py.name} references source repo path"
