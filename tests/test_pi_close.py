"""Tests for plugin/edpa/scripts/pi_close.py."""
import json
import sys
from pathlib import Path

import pytest  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import pi_close  # noqa: E402


def _write_results(edpa: Path, iteration_id: str, people: list) -> None:
    rep = edpa / "reports" / f"iteration-{iteration_id}"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "edpa_results.json").write_text(
        json.dumps({"iteration": iteration_id, "people": people}),
        encoding="utf-8")


def test_aggregate_engine_results_reads_people_total_derived(tmp_path: Path) -> None:
    """D-32: aggregate_engine_results must read the engine's real
    edpa_results.json schema — top-level ``people`` (not ``allocations``),
    entries keyed ``id`` + ``total_derived`` (not ``person``/``derived_hours``).
    The mismatch made PI close silently roll up ZERO engine-derived hours.
    It must also SUM a person's hours across the PI's iterations."""
    edpa = tmp_path / ".edpa"
    _write_results(edpa, "PI-2026-1.1", [
        {"id": "alice", "name": "Alice", "role": "Dev", "capacity": 60,
         "total_derived": 10.0, "items": [], "invariant_ok": True},
        {"id": "bob", "name": "Bob", "role": "Arch", "capacity": 40,
         "total_derived": 5.5, "items": [], "invariant_ok": True},
    ])
    _write_results(edpa, "PI-2026-1.2", [
        {"id": "alice", "name": "Alice", "role": "Dev", "capacity": 60,
         "total_derived": 3.0, "items": [], "invariant_ok": True},
    ])

    out = pi_close.aggregate_engine_results(
        edpa, "PI-2026-1", ["PI-2026-1.1", "PI-2026-1.2"])
    assert out is not None
    by_person = {e["person"]: e["derived_hours"] for e in out}
    assert by_person["alice"] == 13.0  # 10.0 + 3.0 summed across iterations
    assert by_person["bob"] == 5.5


def test_aggregate_engine_results_none_when_no_results(tmp_path: Path) -> None:
    """No edpa_results.json on disk → None (handled gracefully)."""
    edpa = tmp_path / ".edpa"
    (edpa / "reports").mkdir(parents=True)
    assert pi_close.aggregate_engine_results(edpa, "PI-2026-1", ["PI-2026-1.1"]) is None
