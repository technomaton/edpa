"""Tests for plugin/edpa/scripts/migrate_wsjf_defaults.py.

Verifies the V2.0→V2.1 backfill that adds explicit 0 values for
js/bv/tc/rr_oe/wsjf on legacy items missing those fields.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import migrate_wsjf_defaults as mig  # noqa: E402
from _md_frontmatter import load_md, save_md_item  # noqa: E402


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (root / "backlog" / d).mkdir(parents=True)
    return root


def _plant(edpa_root: Path, type_dir: str, item: dict) -> Path:
    p = edpa_root / "backlog" / type_dir / f"{item['id']}.md"
    save_md_item(p, item)
    return p


# ---------------------------------------------------------------------------
# Per-item normalizer
# ---------------------------------------------------------------------------

def test_normalize_adds_missing_fields_as_zero() -> None:
    item, changed = mig._normalize_item(
        {"id": "I-1", "type": "Initiative", "title": "Legacy"},
    )
    assert changed is True
    for f in ("js", "bv", "tc", "rr_oe"):
        assert item[f] == 0
    assert item["wsjf"] == 0.0


def test_normalize_recomputes_wsjf_from_existing_inputs() -> None:
    item, changed = mig._normalize_item(
        {"id": "S-1", "type": "Story", "title": "x",
         "js": 5, "bv": 8, "tc": 3, "rr_oe": 2},
    )
    assert changed is True  # wsjf was missing
    assert item["wsjf"] == round((8 + 3 + 2) / 5, 2)


def test_normalize_noop_when_already_complete() -> None:
    complete = {"id": "S-1", "type": "Story", "title": "x",
                "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
                "wsjf": round((8 + 3 + 2) / 5, 2)}
    item, changed = mig._normalize_item(dict(complete))
    assert changed is False


def test_normalize_corrects_stale_wsjf() -> None:
    """wsjf out of date with inputs → recomputed."""
    item, changed = mig._normalize_item(
        {"id": "S-1", "type": "Story", "title": "x",
         "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
         "wsjf": 99.9},  # wrong
    )
    assert changed is True
    assert item["wsjf"] == round((8 + 3 + 2) / 5, 2)


# ---------------------------------------------------------------------------
# migrate() over a real directory tree
# ---------------------------------------------------------------------------

def test_migrate_touches_only_legacy_files(edpa_root: Path) -> None:
    _plant(edpa_root, "initiatives",
           {"id": "I-1", "type": "Initiative", "title": "Legacy",
            "status": "Funnel"})  # no WSJF block
    _plant(edpa_root, "stories",
           {"id": "S-1", "type": "Story", "title": "Modern",
            "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
            "wsjf": round((8 + 3 + 2) / 5, 2)})

    result = mig.migrate(edpa_root)
    assert len(result["touched"]) == 1
    assert len(result["skipped"]) == 1
    assert "I-1.md" in result["touched"][0]

    legacy = load_md(edpa_root / "backlog" / "initiatives" / "I-1.md")
    assert legacy["js"] == 0
    assert legacy["wsjf"] == 0.0


def test_migrate_dry_run_does_not_write(edpa_root: Path) -> None:
    _plant(edpa_root, "stories",
           {"id": "S-1", "type": "Story", "title": "Legacy"})

    mig.migrate(edpa_root, dry_run=True)

    legacy = load_md(edpa_root / "backlog" / "stories" / "S-1.md")
    assert "js" not in legacy, "dry-run leaked a write to disk"


def test_migrate_idempotent(edpa_root: Path) -> None:
    _plant(edpa_root, "stories",
           {"id": "S-1", "type": "Story", "title": "Legacy"})
    mig.migrate(edpa_root)
    second = mig.migrate(edpa_root)
    assert second["touched"] == [], "second run should be a no-op"
    assert len(second["skipped"]) == 1


def test_migrate_handles_empty_backlog(edpa_root: Path) -> None:
    """Empty .edpa/backlog/ → no-op success."""
    result = mig.migrate(edpa_root)
    assert result == {"touched": [], "skipped": []}
