"""Tests for V2.1 Krok C7 — cw_heuristics.yaml wiring.

C7.1: project_setup.seed_configs seeds cw_heuristics.yaml from template.
C7.2: engine.load_heuristics fallback chain finds the V2 vendored template
      (.edpa/engine/templates/) BEFORE returning the hardcoded minimal.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import project_setup as ps  # noqa: E402
import engine  # noqa: E402


PLUGIN_TEMPLATES = ROOT / "plugin" / "edpa" / "templates"


# ─── C7.1 — seed cw_heuristics.yaml ────────────────────────────────────────


@pytest.fixture
def fresh_project(tmp_path: Path) -> Path:
    """Tmp project with vendored engine + templates, no .edpa/config seeded yet."""
    project = tmp_path / "proj"
    eng = project / ".edpa" / "engine"
    eng.mkdir(parents=True)
    shutil.copytree(PLUGIN_TEMPLATES, eng / "templates")
    return project


def test_seed_configs_writes_cw_heuristics(fresh_project: Path) -> None:
    ps.seed_configs(fresh_project)
    out = fresh_project / ".edpa" / "config" / "cw_heuristics.yaml"
    assert out.exists()
    content = out.read_text()
    assert "signals:" in content
    assert "gate_weights:" in content
    assert "Feature:" in content
    assert "Implementing→Validating" in content


def test_seed_configs_idempotent_preserves_user_edits(fresh_project: Path) -> None:
    ps.seed_configs(fresh_project)
    out = fresh_project / ".edpa" / "config" / "cw_heuristics.yaml"
    out.write_text("# USER OVERRIDE\nsignals:\n  commit_author: 9.99\n")
    ps.seed_configs(fresh_project)
    assert "USER OVERRIDE" in out.read_text()


# ─── C7.2 — load_heuristics fallback path ──────────────────────────────────


def test_load_heuristics_prefers_config_seeded_file(fresh_project: Path) -> None:
    """When .edpa/config/cw_heuristics.yaml exists, use it (not template)."""
    config_dir = fresh_project / ".edpa" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "cw_heuristics.yaml").write_text(
        "signals:\n  commit_author: 99.0\n"
    )
    h = engine.load_heuristics(fresh_project / ".edpa")
    assert h["signals"]["commit_author"] == 99.0


def test_load_heuristics_falls_back_to_v2_vendored_template(
    fresh_project: Path,
) -> None:
    """No config file present → V2 vendored template at
    .edpa/engine/templates/ is the next fallback (V2.1 C7.2 fix).
    Without the fix this falls all the way through to the hardcoded
    minimal which has no gate_weights."""
    # fresh_project has no .edpa/config/cw_heuristics.yaml.
    h = engine.load_heuristics(fresh_project / ".edpa")
    # Template defines gate_weights — hardcoded minimal does not.
    assert "gate_weights" in h
    assert "Feature" in h["gate_weights"]


def test_load_heuristics_minimal_fallback_when_nothing_present(
    tmp_path: Path,
) -> None:
    """If no config file AND no vendored template → hardcoded minimal."""
    edpa = tmp_path / ".edpa"
    edpa.mkdir()
    h = engine.load_heuristics(edpa)
    assert h == {
        "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
    }
    # No gate_weights → engine.load_gate_events returns []
    assert "gate_weights" not in h


def test_load_heuristics_v1_legacy_path_still_works(tmp_path: Path) -> None:
    """V1 layout (.claude/edpa/templates/) is the secondary fallback."""
    edpa = tmp_path / ".edpa"
    edpa.mkdir()
    legacy_dir = tmp_path / ".claude" / "edpa" / "templates"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "cw_heuristics.yaml.tmpl").write_text(
        "signals:\n  commit_author: 77.0\n"
    )
    h = engine.load_heuristics(edpa)
    assert h["signals"]["commit_author"] == 77.0
