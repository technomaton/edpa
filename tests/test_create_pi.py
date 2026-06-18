"""Tests for create_pi.py — the PI-level metadata file creator.

create_pi.py is the single source of behavior for PI creation: the
``edpa_pi_create`` MCP tool imports :func:`create_pi.create_pi`, and the
``/edpa:create-pi`` command shells out to its CLI.
These cover the importable core (``create_pi``) and the CLI (subprocess),
mirroring ``test_capacity_overrides.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import create_pi as cp  # noqa: E402


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "iterations").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "people.yaml").write_text(
        yaml.safe_dump({"people": [
            {"id": "alice", "name": "Alice", "capacity_per_iteration": 40},
        ]})
    )
    return root


# -- core: create_pi() --------------------------------------------------------

def test_create_pi_writes_pi_block(edpa_root: Path) -> None:
    result = cp.create_pi(edpa_root, "PI-2026-2", start_date="2026-07-06",
                          iteration_weeks=2, pi_iterations=5, status="active")
    assert result["id"] == "PI-2026-2"
    pi_path = edpa_root / "iterations" / "PI-2026-2.yaml"
    assert pi_path.exists()
    assert yaml.safe_load(pi_path.read_text()) == {"pi": {
        "id": "PI-2026-2", "status": "active", "iteration_weeks": 2,
        "pi_iterations": 5, "start_date": "2026-07-06",
    }}


def test_create_pi_defaults(edpa_root: Path) -> None:
    cp.create_pi(edpa_root, "PI-2026-3")
    parsed = yaml.safe_load(
        (edpa_root / "iterations" / "PI-2026-3.yaml").read_text())
    assert parsed["pi"]["status"] == "planning"
    assert parsed["pi"]["iteration_weeks"] == 1
    assert "pi_iterations" not in parsed["pi"]
    assert "start_date" not in parsed["pi"]


@pytest.mark.parametrize("bad", ["PI-2026-2.1", "bogus", "", "pi-2026-2"])
def test_create_pi_rejects_non_pi_level_id(edpa_root: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        cp.create_pi(edpa_root, bad)


def test_create_pi_rejects_duplicate(edpa_root: Path) -> None:
    cp.create_pi(edpa_root, "PI-2026-2")
    with pytest.raises(ValueError, match="already exists"):
        cp.create_pi(edpa_root, "PI-2026-2")


def test_create_pi_rejects_bad_status(edpa_root: Path) -> None:
    with pytest.raises(ValueError, match="status"):
        cp.create_pi(edpa_root, "PI-2026-2", status="bogus")


def test_create_pi_rejects_bad_date(edpa_root: Path) -> None:
    with pytest.raises(ValueError, match="start_date"):
        cp.create_pi(edpa_root, "PI-2026-2", start_date="2026/07/06")


@pytest.mark.parametrize("weeks", [0, -1, "1"])
def test_create_pi_rejects_bad_weeks(edpa_root: Path, weeks) -> None:
    with pytest.raises(ValueError, match="iteration_weeks"):
        cp.create_pi(edpa_root, "PI-2026-2", iteration_weeks=weeks)


# -- round-trip: file is consumed cleanly by the loader ----------------------

def test_created_pi_read_by_loader_no_missing_warning(edpa_root: Path) -> None:
    from _pi_loader import derive_pis  # noqa: E402
    cp.create_pi(edpa_root, "PI-2026-2", start_date="2026-07-06",
                 end_date="2026-08-02", iteration_weeks=1, pi_iterations=4,
                 status="active")
    pis, diags = derive_pis(edpa_root)
    pi = next((p for p in pis if p["id"] == "PI-2026-2"), None)
    assert pi is not None
    assert pi["status"] == "active"
    assert pi["pi_iterations"] == 4
    # The pi: file exists, so no missing_pi_yaml warning.
    assert not any(d.get("code") == "missing_pi_yaml" for d in diags)


# -- CLI: main() via subprocess ----------------------------------------------

def _run_cli(edpa_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "create_pi.py"), *args],
        cwd=str(edpa_root.parent), capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_creates_with_no_commit(edpa_root: Path) -> None:
    r = _run_cli(edpa_root, "PI-2026-2", "--start", "2026-07-06",
                 "--weeks", "1", "--iterations", "5", "--no-commit")
    assert r.returncode == 0, r.stderr
    parsed = yaml.safe_load(
        (edpa_root / "iterations" / "PI-2026-2.yaml").read_text())
    assert parsed["pi"]["id"] == "PI-2026-2"
    assert parsed["pi"]["pi_iterations"] == 5


def test_cli_rejects_iteration_level_id(edpa_root: Path) -> None:
    r = _run_cli(edpa_root, "PI-2026-2.1", "--no-commit")
    assert r.returncode == 1
    assert "PI-YYYY-N" in r.stderr


def test_cli_rejects_duplicate(edpa_root: Path) -> None:
    assert _run_cli(edpa_root, "PI-2026-2", "--no-commit").returncode == 0
    r = _run_cli(edpa_root, "PI-2026-2", "--no-commit")
    assert r.returncode == 1
    assert "already exists" in r.stderr


def test_cli_bad_status_is_argparse_error(edpa_root: Path) -> None:
    r = _run_cli(edpa_root, "PI-2026-2", "--status", "bogus", "--no-commit")
    assert r.returncode == 2  # argparse usage error
