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


def _write_backlog_item(edpa: Path, type_dir: str, item_id: str, **fields) -> None:
    """Backlog item as .md frontmatter (the real on-disk item shape)."""
    d = edpa / "backlog" / type_dir
    d.mkdir(parents=True, exist_ok=True)
    fm = {"id": item_id, **fields}
    (d / f"{item_id}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\nBody.\n",
        encoding="utf-8")


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


def test_features_completed_via_child_iterations(tmp_path: Path) -> None:
    """D-59: features are planned at PI level and typically carry no
    ``iteration`` of their own, so the own-field-only filter returned []
    even with every feature Done (E2E: 6 Done features, all attributed
    to their PI only through child stories/defects). A Done feature must
    also attribute via child Story/Defect ``parent`` refs whose iteration
    falls inside the PI."""
    edpa = tmp_path / ".edpa"
    # E2E shape: Done features carry no iteration; children carry it.
    _write_backlog_item(edpa, "features", "F-1", type="Feature",
                        title="MQTT ingestion", status="Done", parent="E-1",
                        js=20, wsjf=1.3)
    _write_backlog_item(edpa, "features", "F-2", type="Feature",
                        title="Buffering", status="Done", parent="E-1",
                        js=20, wsjf=1.7)
    _write_backlog_item(edpa, "features", "F-5", type="Feature",
                        title="Alerting", status="Done", parent="E-2",
                        js=10, wsjf=1.1)
    _write_backlog_item(edpa, "stories", "S-1", type="Story", parent="F-1",
                        status="Done", iteration="PI-2026-1.1", js=5)
    # No story for F-2 in this PI — a defect fixed there attributes too.
    _write_backlog_item(edpa, "defects", "D-1", type="Defect", parent="F-2",
                        status="Done", iteration="PI-2026-1.3", js=3)
    # F-5's work ran entirely in the NEXT PI.
    _write_backlog_item(edpa, "stories", "S-14", type="Story", parent="F-5",
                        status="Done", iteration="PI-2026-2.1", js=5)

    done = pi_close.features_completed(edpa, "PI-2026-1")
    assert [f["id"] for f in done] == ["F-1", "F-2"]
    assert done[0]["title"] == "MQTT ingestion"
    assert done[0]["js"] == 20

    assert [f["id"] for f in pi_close.features_completed(edpa, "PI-2026-2")] \
        == ["F-5"]

    # …and the attribution lands in the PI rollup report.
    _write_iteration(edpa, "PI-2026-1.1")
    result, err = pi_close.build_pi_results(edpa, "PI-2026-1")
    assert err is None
    assert [f["id"] for f in result["features_completed"]] == ["F-1", "F-2"]


def _write_iteration_raw(edpa: Path, it_id: str, *, planned_sp=None,
                         delivered_sp=None) -> None:
    """Closed iteration with planning/delivery blocks only when given."""
    it_dir = edpa / "iterations"
    it_dir.mkdir(parents=True, exist_ok=True)
    doc: dict = {
        "iteration": {"id": it_id, "pi": it_id.rsplit(".", 1)[0],
                      "status": "closed", "type": "Iteration"},
        "status": "closed",
    }
    if planned_sp is not None:
        doc["planning"] = {"planned_sp": planned_sp}
    if delivered_sp is not None:
        doc["delivery"] = {"delivered_sp": delivered_sp, "velocity": delivered_sp}
    (it_dir / f"{it_id}.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_predictability_not_100_when_unplanned_scope_lands(tmp_path: Path) -> None:
    """D-60 (E2E PI-2026-2.2): planned 26 at planning time, delivered 29 after
    an unplanned mid-PI defect. Close must not backfill planned=delivered, and
    the rollup must report ~89.7% — deviation from plan — not 100%."""
    edpa = tmp_path / ".edpa"
    _write_iteration_raw(edpa, "PI-2026-2.2", planned_sp=26, delivered_sp=29)

    result, err = pi_close.build_pi_results(edpa, "PI-2026-2")
    assert err is None
    it = result["iterations"][0]
    assert it["planned_sp"] == 26
    assert it["delivered_sp"] == 29
    assert it["predictability_pct"] == 89.7
    assert result["summary"]["avg_predictability_pct"] == 89.7


def test_predictability_na_without_planning_stamp(tmp_path: Path) -> None:
    """D-60: no planning-time stamp → planned stays null and predictability
    reports n/a. The old code derived planned from CURRENT item assignment
    (which equals delivered once everything is Done) → vacuous 100%."""
    edpa = tmp_path / ".edpa"
    _write_iteration_raw(edpa, "PI-2026-2.2")  # neither planning nor delivery
    # All items Done — the rollup would "derive" planned == delivered == 29.
    _write_backlog_item(edpa, "stories", "S-1", type="Story", js=13,
                        status="Done", iteration="PI-2026-2.2")
    _write_backlog_item(edpa, "stories", "S-2", type="Story", js=13,
                        status="Done", iteration="PI-2026-2.2")
    _write_backlog_item(edpa, "defects", "D-1", type="Defect", js=3,
                        status="Done", iteration="PI-2026-2.2")

    result, err = pi_close.build_pi_results(edpa, "PI-2026-2")
    assert err is None
    it = result["iterations"][0]
    assert it["planned_sp"] is None
    assert it["delivered_sp"] == 29                # rollup fallback kept (D-57)
    assert it["predictability_pct"] is None        # n/a, NOT 100.0
    assert result["summary"]["total_planned_sp"] == 0
    assert result["summary"]["avg_predictability_pct"] is None

    md = pi_close.render_summary_md(result)
    assert "n/a" in md
    assert "None%" not in md


def test_avg_predictability_averages_stamped_iterations_only(tmp_path: Path) -> None:
    """D-60: the PI average is the mean of the per-iteration predictabilities
    that exist. A totals ratio would compare stamped planned SP against
    delivered SP including UNSTAMPED iterations (26 planned vs 29+8 delivered
    → bogus 70.3%); the unstamped iteration must simply not contribute."""
    edpa = tmp_path / ".edpa"
    _write_iteration_raw(edpa, "PI-2026-2.2", planned_sp=26, delivered_sp=29)
    _write_iteration_raw(edpa, "PI-2026-2.3", delivered_sp=8)  # no stamp

    result, err = pi_close.build_pi_results(edpa, "PI-2026-2")
    assert err is None
    assert result["summary"]["avg_predictability_pct"] == 89.7
    assert result["summary"]["total_delivered_sp"] == 37
    assert result["summary"]["total_planned_sp"] == 26


def test_features_completed_own_field_status_and_prefix_guards(tmp_path: Path) -> None:
    """Own ``iteration``/``pi`` fields still attribute; a non-Done feature
    never counts (even with Done children in the PI); ``PI-2026-1`` must
    not prefix-match ``PI-2026-10.*``; a null iteration must not crash."""
    edpa = tmp_path / ".edpa"
    _write_backlog_item(edpa, "features", "F-1", type="Feature", title="A",
                        status="Done", iteration="PI-2026-1.2")
    _write_backlog_item(edpa, "features", "F-2", type="Feature", title="B",
                        status="Done", pi="PI-2026-1")
    # Done, but belongs to PI-2026-10 — a raw startswith would leak it in.
    _write_backlog_item(edpa, "features", "F-3", type="Feature", title="C",
                        status="Done", iteration="PI-2026-10.1")
    # Child Done inside the PI, but the feature itself is not Done.
    _write_backlog_item(edpa, "features", "F-4", type="Feature", title="D",
                        status="Implementing")
    _write_backlog_item(edpa, "stories", "S-40", type="Story", parent="F-4",
                        status="Done", iteration="PI-2026-1.1", js=3)
    # Done with an explicit null iteration — no crash, no match.
    _write_backlog_item(edpa, "features", "F-6", type="Feature", title="E",
                        status="Done", iteration=None)

    done = pi_close.features_completed(edpa, "PI-2026-1")
    assert [f["id"] for f in done] == ["F-1", "F-2"]
