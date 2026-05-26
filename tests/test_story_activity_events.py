"""Tests for V2.1 Krok C7.5 — engine.load_story_activity_events().

In-flight Stories with yaml_edit signals in the iteration window get
synthetic activity events; the engine credits a fraction of Story.js
to whoever did the YAML work, BEFORE the Story reaches Done.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import engine  # noqa: E402
from _md_frontmatter import save_md_item  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    (root / "backlog" / "stories").mkdir(parents=True)
    (root / "iterations").mkdir()
    return root


def _plant_story(edpa_root: Path, item_id: str, status: str = "Implementing",
                 js: int = 5) -> Path:
    p = edpa_root / "backlog" / "stories" / f"{item_id}.md"
    save_md_item(p, {
        "id": item_id, "type": "Story", "title": f"{item_id} title",
        "status": status, "js": js,
    })
    return p


def _signal(login: str = "alice", weight: float = 5.0) -> dict:
    return {
        "type": "yaml_edit:list_grow", "login": login, "weight": weight,
        "ref": "commit/abc1234", "detected_at": "2026-05-25T10:00:00Z",
        "tags": [],
    }


HEUR_DEFAULT = {"story_activity": {"credit_factor": 0.40}}
HEUR_DISABLED = {"story_activity": {"credit_factor": 0.0}}


# ─── Basic emission ────────────────────────────────────────────────────────


def test_emits_event_for_in_flight_story_with_signals(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Implementing", js=5)
    yaml_sigs = {"S-1": [_signal()]}
    events, audit = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert len(events) == 1
    e = events[0]
    assert e["id"] == "S-1@activity"
    assert e["level"] == "Story"
    assert e["job_size"] == pytest.approx(5 * 0.40)
    assert e["contributors"] == []
    assert audit[0]["item_id"] == "S-1"
    assert audit[0]["n_yaml_edit_signals"] == 1


def test_emits_per_story_with_proper_js_split(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Backlog", js=3)
    _plant_story(edpa_root, "S-2", status="Analyzing", js=8)
    yaml_sigs = {
        "S-1": [_signal("alice", 2.0)],
        "S-2": [_signal("bob", 4.0), _signal("carol", 3.0)],
    }
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert len(events) == 2
    js_by_id = {e["id"]: e["job_size"] for e in events}
    assert js_by_id["S-1@activity"] == pytest.approx(3 * 0.40)
    assert js_by_id["S-2@activity"] == pytest.approx(8 * 0.40)


# ─── Skip rules ────────────────────────────────────────────────────────────


def test_skips_done_stories(edpa_root: Path) -> None:
    """Done stories are credited by load_backlog_items — don't double-count."""
    _plant_story(edpa_root, "S-1", status="Done")
    yaml_sigs = {"S-1": [_signal()]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []


def test_skips_stories_without_yaml_edits(edpa_root: Path) -> None:
    """A Story with no edit activity in this iteration → no event."""
    _plant_story(edpa_root, "S-1", status="Implementing")
    _plant_story(edpa_root, "S-2", status="Backlog")
    yaml_sigs = {"S-2": [_signal()]}  # only S-2 had activity
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert [e["id"] for e in events] == ["S-2@activity"]


def test_skips_zero_js_stories(edpa_root: Path) -> None:
    """Story without js (or js=0) is not scoreable."""
    _plant_story(edpa_root, "S-1", status="Implementing", js=0)
    yaml_sigs = {"S-1": [_signal()]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []


def test_skips_all_when_credit_factor_zero(edpa_root: Path) -> None:
    """credit_factor=0 → C7.5 disabled, behaves like V2.0."""
    _plant_story(edpa_root, "S-1", status="Implementing")
    yaml_sigs = {"S-1": [_signal()]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DISABLED, yaml_sigs,
    )
    assert events == []


def test_skips_all_when_no_iteration(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Implementing")
    yaml_sigs = {"S-1": [_signal()]}
    events, _ = engine.load_story_activity_events(
        edpa_root, None, HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []


def test_skips_all_when_no_yaml_edits(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Implementing")
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, {},
    )
    assert events == []


# ─── Custom credit_factor ─────────────────────────────────────────────────


def test_respects_custom_credit_factor(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Implementing", js=10)
    yaml_sigs = {"S-1": [_signal()]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1",
        {"story_activity": {"credit_factor": 0.25}},
        yaml_sigs,
    )
    assert events[0]["job_size"] == pytest.approx(10 * 0.25)


# ─── Audit log shape ──────────────────────────────────────────────────────


def test_audit_records_signal_count_and_factor(edpa_root: Path) -> None:
    _plant_story(edpa_root, "S-1", status="Implementing", js=8)
    yaml_sigs = {"S-1": [_signal(), _signal("bob", 3), _signal("carol", 1)]}
    _, audit = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    a = audit[0]
    assert a["type"] == "story_activity"
    assert a["item_id"] == "S-1"
    assert a["credit_factor"] == 0.40
    assert a["story_js"] == 8
    assert a["effective_js"] == pytest.approx(8 * 0.40)
    assert a["n_yaml_edit_signals"] == 3
