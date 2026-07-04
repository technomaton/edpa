"""Tests for plugin/edpa/scripts/pi_close.py."""
import json
import sys
from pathlib import Path

import pytest  # noqa: F401
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import pi_close  # noqa: E402


def _write_results(edpa: Path, iteration_id: str, people: list) -> None:
    rep = edpa / "reports" / f"iteration-{iteration_id}"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "edpa_results.json").write_text(
        json.dumps({"iteration": iteration_id, "people": people}),
        encoding="utf-8")


def _write_people(edpa: Path, caps: dict) -> None:
    """Minimal config/people.yaml with per-person capacity_per_iteration."""
    cfg = edpa / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    people = [
        {"id": pid, "name": pid.title(), "role": "Dev",
         "capacity_per_iteration": cap}
        for pid, cap in caps.items()
    ]
    (cfg / "people.yaml").write_text(
        yaml.safe_dump({"people": people}, sort_keys=False), encoding="utf-8")


def _write_iteration(edpa: Path, it_id: str, capacity=None) -> None:
    """Closed iteration YAML shaped like edpa_iteration_close output.

    ``capacity`` (when not None) lands in the planning block — nothing in
    the product writes it today, but it stays supported as an override.
    """
    it_dir = edpa / "iterations"
    it_dir.mkdir(parents=True, exist_ok=True)
    planning = {"planned_sp": 10}
    if capacity is not None:
        planning["capacity"] = capacity
    doc = {
        "iteration": {"id": it_id, "pi": it_id.rsplit(".", 1)[0],
                      "status": "closed", "type": "Iteration"},
        "status": "closed",
        "planning": planning,
        "delivery": {"delivered_sp": 10, "velocity": 10},
    }
    (it_dir / f"{it_id}.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_total_capacity_hours_from_people_registry(tmp_path: Path) -> None:
    """D-58: the rollup summed only planning.capacity, which nothing writes,
    so every PI reported total_capacity_hours=0 even though people.yaml
    declares capacity_per_iteration for everyone (E2E: 4 people x 60 h
    x 3 iterations = 720 h/PI while per_person_hours were correct).
    The registry total per iteration must back-fill each iteration that
    carries no explicit planning.capacity."""
    edpa = tmp_path / ".edpa"
    _write_people(edpa, {"alice": 60, "bob": 60, "carol": 60, "david": 60})
    for n in (1, 2, 3):
        _write_iteration(edpa, f"PI-2026-1.{n}")

    result, err = pi_close.build_pi_results(edpa, "PI-2026-1")
    assert err is None
    assert result["summary"]["total_capacity_hours"] == 720


def test_planning_capacity_block_overrides_registry(tmp_path: Path) -> None:
    """An explicit planning.capacity wins over the registry fallback for
    that iteration — including an explicit 0 (e.g. a down iteration)."""
    edpa = tmp_path / ".edpa"
    _write_people(edpa, {"alice": 60, "bob": 60})  # 120 h/iteration fallback
    _write_iteration(edpa, "PI-2026-1.1", capacity=144)  # explicit override
    _write_iteration(edpa, "PI-2026-1.2")                # registry fallback
    _write_iteration(edpa, "PI-2026-1.3", capacity=0)    # explicit zero kept

    result, err = pi_close.build_pi_results(edpa, "PI-2026-1")
    assert err is None
    assert result["summary"]["total_capacity_hours"] == 264  # 144 + 120 + 0


def test_total_capacity_zero_without_registry_or_planning(tmp_path: Path) -> None:
    """No people.yaml and no planning.capacity → 0, not a crash (back-compat
    for repos without a capacity registry)."""
    edpa = tmp_path / ".edpa"
    _write_iteration(edpa, "PI-2026-1.1")

    result, err = pi_close.build_pi_results(edpa, "PI-2026-1")
    assert err is None
    assert result["summary"]["total_capacity_hours"] == 0


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
