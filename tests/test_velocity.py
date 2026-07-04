"""Tests for plugin/edpa/scripts/velocity.py — D-60 regression.

The E2E run closed PI-2026-2.2 with planned 26 (planning-day stamp) but the
close flow backfilled planning.planned_sp = delivered (29), and the report
side ALSO derived "planned" from the current item→iteration assignment —
which by construction equals delivered once everything lands. Either way
predictability was vacuously 100%.

Contract now: planned_sp comes ONLY from the planning-time stamp; the item
rollup keeps feeding delivered_sp. Missing stamp → planned null +
predictability n/a (never 100)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import velocity  # noqa: E402


def _write_iteration(edpa: Path, it_id: str, *, planned_sp=None,
                     delivered_sp=None) -> None:
    """Closed iteration YAML; planning/delivery blocks only when given."""
    it_dir = edpa / "iterations"
    it_dir.mkdir(parents=True, exist_ok=True)
    doc: dict = {
        "iteration": {"id": it_id, "pi": it_id.rsplit(".", 1)[0],
                      "start_date": "2026-04-27", "end_date": "2026-05-15",
                      "status": "closed", "type": "Iteration"},
        "status": "closed",
    }
    if planned_sp is not None:
        doc["planning"] = {"planned_sp": planned_sp}
    if delivered_sp is not None:
        doc["delivery"] = {"delivered_sp": delivered_sp,
                           "velocity": delivered_sp}
    (it_dir / f"{it_id}.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _write_story(edpa: Path, iid: str, js: int, status: str, iteration: str) -> None:
    d = edpa / "backlog" / ("defects" if iid.startswith("D-") else "stories")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{iid}.md").write_text(
        f"---\nid: {iid}\ntype: {'Defect' if iid.startswith('D-') else 'Story'}\n"
        f"js: {js}\nstatus: {status}\niteration: {iteration}\n---\n",
        encoding="utf-8")


def test_predictability_from_planning_stamp_not_delivered(tmp_path: Path) -> None:
    """E2E PI-2026-2.2: planned 26, delivered 29 (unplanned mid-PI defect)
    → ~89.7%, not 100."""
    edpa = tmp_path / ".edpa"
    _write_iteration(edpa, "PI-2026-2.2", planned_sp=26, delivered_sp=29)

    recs = velocity.load_closed_iterations(edpa)
    assert len(recs) == 1
    assert recs[0]["planned_sp"] == 26
    assert recs[0]["delivered_sp"] == 29
    assert recs[0]["predictability_pct"] == 89.7


def test_planned_never_derived_from_item_rollup(tmp_path: Path) -> None:
    """No planning-time stamp → planned stays null and predictability is
    None (n/a), even though the item rollup could 'derive' planned=delivered
    from current assignments. Delivered still falls back to the rollup."""
    edpa = tmp_path / ".edpa"
    _write_iteration(edpa, "PI-2026-2.2")  # no planning, no delivery block
    _write_story(edpa, "S-1", 13, "Done", "PI-2026-2.2")
    _write_story(edpa, "S-2", 13, "Done", "PI-2026-2.2")
    _write_story(edpa, "D-1", 3, "Done", "PI-2026-2.2")  # mid-PI defect

    recs = velocity.load_closed_iterations(edpa)
    assert len(recs) == 1
    assert recs[0]["planned_sp"] is None
    assert recs[0]["delivered_sp"] == 29           # rollup fallback kept (D-57)
    assert recs[0]["predictability_pct"] is None   # n/a, NOT 100.0


def test_render_md_shows_na_without_plan(tmp_path: Path) -> None:
    edpa = tmp_path / ".edpa"
    _write_iteration(edpa, "PI-2026-2.1", delivered_sp=29)

    report = velocity.build_report(edpa, window=3)
    md = velocity.render_md(report)
    assert "n/a" in md
    assert "None" not in md


def test_velocity_average_unaffected_by_missing_plan(tmp_path: Path) -> None:
    edpa = tmp_path / ".edpa"
    _write_iteration(edpa, "PI-2026-1.1", planned_sp=26, delivered_sp=29)
    _write_iteration(edpa, "PI-2026-1.2", delivered_sp=27)

    report = velocity.build_report(edpa, window=3)
    assert report["average_velocity"] == 28.0
    by_id = {r["id"]: r for r in report["iterations"]}
    assert by_id["PI-2026-1.1"]["predictability_pct"] == 89.7
    assert by_id["PI-2026-1.2"]["predictability_pct"] is None
