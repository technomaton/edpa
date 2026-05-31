"""Tests for _sp_rollup.iteration_sp — derive planned/delivered SP from items.

Regression for the E2E finding that velocity.py / pi_close.py reported 0 SP /
None predictability because iteration YAMLs carry no rolled-up story points
(SP live on individual Story/Defect `js` fields)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from _sp_rollup import iteration_sp  # noqa: E402
from _md_frontmatter import save_md_item  # noqa: E402


def _item(edpa: Path, kind_dir: str, iid: str, itype: str, iteration, js, status):
    (edpa / "backlog" / kind_dir).mkdir(parents=True, exist_ok=True)
    save_md_item(edpa / "backlog" / kind_dir / f"{iid}.md", {
        "id": iid, "type": itype, "title": iid,
        "status": status, "iteration": iteration, "js": js,
    })


def test_iteration_sp_sums_js_and_counts_done(tmp_path: Path) -> None:
    edpa = tmp_path / ".edpa"
    _item(edpa, "stories", "S-1", "Story", "PI-2026-1.1", 5, "Done")
    _item(edpa, "stories", "S-2", "Story", "PI-2026-1.1", 3, "Implementing")
    _item(edpa, "stories", "S-3", "Story", "PI-2026-1.2", 8, "Done")
    _item(edpa, "defects", "D-1", "Defect", "PI-2026-1.1", 2, "Done")

    sp = iteration_sp(edpa)
    # 1.1: planned 5+3+2=10, delivered (Done only) 5+2=7
    assert sp["PI-2026-1.1"] == {"planned_sp": 10, "delivered_sp": 7}
    # 1.2: planned 8, delivered 8
    assert sp["PI-2026-1.2"] == {"planned_sp": 8, "delivered_sp": 8}


def test_iteration_sp_ignores_items_without_iteration(tmp_path: Path) -> None:
    edpa = tmp_path / ".edpa"
    _item(edpa, "stories", "S-9", "Story", None, 5, "Done")
    assert iteration_sp(edpa) == {}


def test_iteration_sp_empty_when_no_backlog(tmp_path: Path) -> None:
    assert iteration_sp(tmp_path / ".edpa") == {}
