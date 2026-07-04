"""Tests for the objectives.py CLI (D-71).

objectives.py used to be library-only: ``python3 objectives.py --help`` printed
nothing, so the sole write path for PI objectives / confidence votes was the
MCP server (the E2E had to drive it through a python shim). This covers the new
argparse CLI, which layers over the SAME library functions the
``edpa_objective_set`` / ``edpa_objective_remove`` / ``edpa_confidence_vote``
MCP handlers call — so the CLI and MCP write paths produce byte-identical YAML.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import objectives as obj  # noqa: E402


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "objectives.py"), *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
    )


def _obj_yaml(edpa_dir: Path, pi: str = "PI-2026-1") -> str:
    return (edpa_dir / "pi-objectives" / f"{pi}.yaml").read_text(encoding="utf-8")


# -- the regression: a CLI now exists and self-documents ----------------------

def test_help_is_not_empty_and_lists_subcommands(tmp_path: Path) -> None:
    r = _run("--help", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), "objectives.py --help printed nothing (D-71)"
    for sub in ("set", "remove", "vote"):
        assert sub in r.stdout


# -- CLI write path == MCP/library write path (byte-identical YAML) ----------

def test_cli_set_matches_library(tmp_path: Path) -> None:
    title = "Deliver OMOP parser"
    cli = tmp_path / "cli" / ".edpa"
    cli.mkdir(parents=True)
    r = _run("set", "PI-2026-1", "alpha", "committed", title,
             "--bv", "8", "--status", "in_progress",
             "--edpa-root", str(cli), "--no-commit", cwd=tmp_path)
    assert r.returncode == 0, r.stderr

    # The MCP handler calls exactly this library function.
    lib = tmp_path / "lib" / ".edpa"
    lib.mkdir(parents=True)
    obj.set_objective(lib, "PI-2026-1", "alpha", "committed", title,
                      bv=8, status="in_progress")

    assert _obj_yaml(cli) == _obj_yaml(lib)


def test_cli_vote_matches_library(tmp_path: Path) -> None:
    cli = tmp_path / "cli" / ".edpa"
    cli.mkdir(parents=True)
    r = _run("vote", "PI-2026-1", "alpha", "4",
             "--edpa-root", str(cli), "--no-commit", cwd=tmp_path)
    assert r.returncode == 0, r.stderr

    lib = tmp_path / "lib" / ".edpa"
    lib.mkdir(parents=True)
    obj.set_confidence(lib, "PI-2026-1", "alpha", 4)

    assert _obj_yaml(cli) == _obj_yaml(lib)


def test_cli_set_then_vote_full_file_matches_library(tmp_path: Path) -> None:
    """Ticket scenario: set an objective + cast a confidence vote, then the
    whole file must equal the MCP/library-produced file."""
    title = "FHIR bridge MVP"
    cli = tmp_path / "cli" / ".edpa"
    cli.mkdir(parents=True)
    assert _run("set", "PI-2026-1", "beta", "stretch", title, "--bv", "5",
                "--edpa-root", str(cli), "--no-commit",
                cwd=tmp_path).returncode == 0
    assert _run("vote", "PI-2026-1", "beta", "3",
                "--edpa-root", str(cli), "--no-commit",
                cwd=tmp_path).returncode == 0

    lib = tmp_path / "lib" / ".edpa"
    lib.mkdir(parents=True)
    obj.set_objective(lib, "PI-2026-1", "beta", "stretch", title, bv=5)
    obj.set_confidence(lib, "PI-2026-1", "beta", 3)

    assert _obj_yaml(cli) == _obj_yaml(lib)


def test_cli_remove_matches_library(tmp_path: Path) -> None:
    title = "Temp objective"
    cli = tmp_path / "cli" / ".edpa"
    cli.mkdir(parents=True)
    _run("set", "PI-2026-1", "alpha", "committed", title,
         "--edpa-root", str(cli), "--no-commit", cwd=tmp_path)
    assert _run("remove", "PI-2026-1", "alpha", "committed", title,
                "--edpa-root", str(cli), "--no-commit",
                cwd=tmp_path).returncode == 0

    lib = tmp_path / "lib" / ".edpa"
    lib.mkdir(parents=True)
    obj.set_objective(lib, "PI-2026-1", "alpha", "committed", title)
    obj.remove_objective(lib, "PI-2026-1", "alpha", "committed", title)

    assert _obj_yaml(cli) == _obj_yaml(lib)


# -- error surfaces map to distinct exit codes (mirrors test_create_pi) -------

def test_cli_bad_kind_is_argparse_error(tmp_path: Path) -> None:
    cli = tmp_path / ".edpa"
    cli.mkdir()
    r = _run("set", "PI-2026-1", "alpha", "bogus", "T",
             "--edpa-root", str(cli), "--no-commit", cwd=tmp_path)
    assert r.returncode == 2  # argparse rejects the invalid choice


def test_cli_bad_pi_is_validation_error(tmp_path: Path) -> None:
    cli = tmp_path / ".edpa"
    cli.mkdir()
    r = _run("vote", "not-a-pi", "alpha", "4",
             "--edpa-root", str(cli), "--no-commit", cwd=tmp_path)
    assert r.returncode == 1  # library ValueError -> die()
    assert "PI-level" in r.stderr
