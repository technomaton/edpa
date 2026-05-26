"""Tests for plugin/edpa/scripts/migrate_evidence_rename.py.

Covers the V2.0→V2.1 rename of ``ci_signals[]`` → ``evidence[]`` in
backlog YAML, plus the backward-compatible read path in
``detect_contributors.read_evidence``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import migrate_evidence_rename as mig  # noqa: E402
import detect_contributors as dc  # noqa: E402
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


_SAMPLE_SIGNAL = {
    "type": "pr_author", "person": "alice", "weight": 3.4,
    "ref": "PR#1:author", "at": "2026-05-26T12:00:00Z",
}


# ---------------------------------------------------------------------------
# normalizer
# ---------------------------------------------------------------------------

def test_normalize_renames_legacy_block() -> None:
    item = {"id": "S-1", "type": "Story", "title": "x",
            "ci_signals": [_SAMPLE_SIGNAL]}
    out, changed = mig._normalize_item(item)
    assert changed is True
    assert "ci_signals" not in out
    assert out["evidence"] == [_SAMPLE_SIGNAL]


def test_normalize_noop_when_only_evidence() -> None:
    item = {"id": "S-1", "type": "Story", "title": "x",
            "evidence": [_SAMPLE_SIGNAL]}
    _, changed = mig._normalize_item(item)
    assert changed is False


def test_normalize_noop_when_neither_block() -> None:
    item = {"id": "S-1", "type": "Story", "title": "x"}
    _, changed = mig._normalize_item(item)
    assert changed is False


def test_normalize_merges_both_blocks_dedup_by_ref() -> None:
    """Edge case: hand-edited YAML has both blocks. Merge by ref."""
    other = {**_SAMPLE_SIGNAL, "ref": "PR#2:author", "person": "bob"}
    item = {"id": "S-1", "type": "Story", "title": "x",
            "ci_signals": [_SAMPLE_SIGNAL],
            "evidence": [other]}
    out, changed = mig._normalize_item(item)
    assert changed is True
    assert "ci_signals" not in out
    refs = {s["ref"] for s in out["evidence"]}
    assert refs == {"PR#1:author", "PR#2:author"}


def test_normalize_when_both_blocks_have_same_ref_evidence_wins() -> None:
    """Same ref in both → evidence[] entry takes precedence."""
    legacy = {**_SAMPLE_SIGNAL, "person": "OLD"}
    new = {**_SAMPLE_SIGNAL, "person": "NEW"}
    item = {"id": "S-1", "type": "Story", "title": "x",
            "ci_signals": [legacy],
            "evidence": [new]}
    out, _ = mig._normalize_item(item)
    assert len(out["evidence"]) == 1
    assert out["evidence"][0]["person"] == "NEW"


# ---------------------------------------------------------------------------
# migrate() over directory tree
# ---------------------------------------------------------------------------

def test_migrate_touches_only_legacy_files(edpa_root: Path) -> None:
    _plant(edpa_root, "stories",
           {"id": "S-1", "type": "Story", "title": "legacy",
            "ci_signals": [_SAMPLE_SIGNAL]})
    _plant(edpa_root, "stories",
           {"id": "S-2", "type": "Story", "title": "modern",
            "evidence": [_SAMPLE_SIGNAL]})
    _plant(edpa_root, "stories",
           {"id": "S-3", "type": "Story", "title": "empty"})

    result = mig.migrate(edpa_root)
    assert len(result["touched"]) == 1
    assert "S-1.md" in result["touched"][0]
    assert len(result["skipped"]) == 2

    legacy = load_md(edpa_root / "backlog" / "stories" / "S-1.md")
    assert "ci_signals" not in legacy
    assert legacy["evidence"] == [_SAMPLE_SIGNAL]


def test_migrate_dry_run_does_not_write(edpa_root: Path) -> None:
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x",
                "ci_signals": [_SAMPLE_SIGNAL]})
    mig.migrate(edpa_root, dry_run=True)
    fresh = load_md(p)
    assert "ci_signals" in fresh, "dry-run leaked a write"
    assert "evidence" not in fresh


def test_migrate_idempotent(edpa_root: Path) -> None:
    _plant(edpa_root, "stories",
           {"id": "S-1", "type": "Story", "title": "x",
            "ci_signals": [_SAMPLE_SIGNAL]})
    mig.migrate(edpa_root)
    second = mig.migrate(edpa_root)
    assert second["touched"] == []


# ---------------------------------------------------------------------------
# Backward-compat reader (detect_contributors.read_evidence)
# ---------------------------------------------------------------------------

def test_read_evidence_falls_back_to_legacy_ci_signals(edpa_root: Path) -> None:
    """V2.0 items not yet migrated → read_evidence picks up ci_signals[]."""
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x",
                "ci_signals": [_SAMPLE_SIGNAL]})
    signals = dc.read_evidence(p)
    assert len(signals) == 1
    assert signals[0]["login"] == "alice"
    assert signals[0]["type"] == "pr_author"


def test_read_evidence_prefers_new_block_when_both_present(edpa_root: Path) -> None:
    """If both blocks present, evidence[] takes precedence (forward state)."""
    other = {**_SAMPLE_SIGNAL, "ref": "PR#2:author", "person": "bob"}
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x",
                "ci_signals": [_SAMPLE_SIGNAL],
                "evidence": [other]})
    signals = dc.read_evidence(p)
    assert len(signals) == 1
    assert signals[0]["login"] == "bob"
    assert signals[0]["ref"] == "PR#2:author"


def test_read_evidence_returns_empty_for_neither_block(edpa_root: Path) -> None:
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x"})
    assert dc.read_evidence(p) == []


def test_read_ci_signals_alias_still_works(edpa_root: Path) -> None:
    """Backward-compat alias for V2.0 callers should not have been removed."""
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x",
                "ci_signals": [_SAMPLE_SIGNAL]})
    assert dc.read_ci_signals(p) == dc.read_evidence(p)


# ---------------------------------------------------------------------------
# sync_pr_contributions auto-migrates on write
# ---------------------------------------------------------------------------

def test_sync_pr_contributions_drops_legacy_block_on_write(
    edpa_root: Path,
) -> None:
    """Running the CI script on a legacy item migrates it as a side effect."""
    import sync_pr_contributions as spc
    p = _plant(edpa_root, "stories",
               {"id": "S-1", "type": "Story", "title": "x",
                "ci_signals": [_SAMPLE_SIGNAL]})

    new_signal_payload = [{
        "item_id": "S-1",
        "signal": {
            "type": "pr_reviewer", "person": "bob", "weight": 2.25,
            "ref": "PR#2:review:RV1", "at": "2026-05-26T13:00:00Z",
        },
    }]
    spc.apply_signals(edpa_root, new_signal_payload)

    fresh = load_md(p)
    assert "ci_signals" not in fresh
    # Both signals present in evidence[] (legacy merged + new added)
    refs = {s["ref"] for s in fresh["evidence"]}
    assert refs == {"PR#1:author", "PR#2:review:RV1"}
