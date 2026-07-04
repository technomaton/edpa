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


# ─── D-62 — neutralized signals must not credit ───────────────────────────
# Materialize-time gating (D-28/D-29) neutralizes out-of-window signals:
# weight zeroed (original kept in raw_weight) + tag out_of_iteration. They
# stay in evidence[] for the audit trail but must never credit — C7.5 has
# to mirror the crediting rule detect_contributors.aggregate_signals
# applies (zero-weight → skip). E2E regression: david got 7.81h in
# PI-2026-1.2 from a neutralized S-12 refinement that was the story's
# ONLY in-window yaml_edit signal.


def _neutralized_signal(person: str = "david") -> dict:
    """Materialized-evidence shape after D-28/D-29 gating (E2E S-12,
    commit 6fbd7c6 @ 2026-02-10, inside PI-2026-1.2's window)."""
    return {
        "type": "yaml_edit", "person": person,
        "weight": 0, "raw_weight": 0.12, "discount": 1.0,
        "ref": "commit/6fbd7c6/S-12.md", "at": "2026-02-10T08:45:00+00:00",
        "tags": ["vol+0.1", "out_of_iteration"],
    }


def test_neutralized_signals_do_not_emit_event(edpa_root: Path) -> None:
    """A story whose only in-window activity was gated to weight 0 +
    out_of_iteration gets NO synthetic event (and no audit entry)."""
    _plant_story(edpa_root, "S-12", status="Backlog", js=8)
    yaml_sigs = {"S-12": [_neutralized_signal()]}
    events, audit = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []
    assert audit == []


def test_zero_weight_signal_without_tag_does_not_credit(edpa_root: Path) -> None:
    """weight==0 alone is non-crediting — mirror of
    detect_contributors.aggregate_signals (analytics-only records)."""
    _plant_story(edpa_root, "S-1", status="Implementing", js=5)
    yaml_sigs = {"S-1": [_signal("alice", weight=0.0)]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []


def test_out_of_iteration_tag_alone_does_not_credit(edpa_root: Path) -> None:
    """The out_of_iteration tag is non-crediting even if a positive
    weight slipped through gating."""
    _plant_story(edpa_root, "S-1", status="Implementing", js=5)
    sig = _signal("alice", weight=2.0)
    sig["tags"] = ["out_of_iteration"]
    yaml_sigs = {"S-1": [sig]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []


def test_mixed_signals_credit_only_live_ones(edpa_root: Path) -> None:
    """Live + neutralized signals on one story: event IS emitted, but
    the audit counts only the crediting signals."""
    _plant_story(edpa_root, "S-1", status="Implementing", js=5)
    yaml_sigs = {"S-1": [_signal("alice", 2.0), _neutralized_signal("alice")]}
    events, audit = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR_DEFAULT, yaml_sigs,
    )
    assert [e["id"] for e in events] == ["S-1@activity"]
    assert audit[0]["n_yaml_edit_signals"] == 1


def test_e2e_shape_neutralized_refinement_zero_hours_invariant_holds(
        edpa_root: Path) -> None:
    """Full E2E regression shape (PI-2026-1.2 / S-12 / david):

    An in-flight story assigned to a LATER iteration carries materialized
    contributors[] plus one evidence[] signal inside THIS iteration's
    window that gating neutralized. The reader keeps the signal visible
    (audit trail), the story-activity path must not credit it, and the
    person's capacity redistributes over their real work — derived hours
    still sum to capacity.
    """
    save_md_item(edpa_root / "backlog" / "stories" / "S-12.md", {
        "id": "S-12", "type": "Story", "title": "Fleet health dashboard",
        "status": "Backlog", "js": 8, "iteration": "PI-2026-1.3",
        "evidence": [_neutralized_signal("david")],
        "contributors": [{
            "person": "david", "cw": 1.0, "contribution_score": 4.0,
            "signals": [{"type": "commit_author", "ref": "commit/7b46209",
                         "weight": 4.0,
                         "detected_at": "2026-01-05T10:12:00+01:00"}],
        }],
    })
    (edpa_root / "iterations" / "PI-2026-1.2.yaml").write_text(
        "iteration:\n"
        "  id: PI-2026-1.2\n"
        "  start_date: '2026-01-26'\n"
        "  end_date: '2026-02-13'\n",
        encoding="utf-8",
    )

    from transitions import parse_iteration_dates  # noqa: E402
    start, end = parse_iteration_dates(
        edpa_root / "iterations" / "PI-2026-1.2.yaml")

    # Reader stays faithful: the neutralized signal is audit-visible.
    yaml_sigs = engine._yaml_edit_from_evidence(edpa_root, start, end)
    assert len(yaml_sigs.get("S-12", [])) == 1
    assert yaml_sigs["S-12"][0]["weight"] == 0

    # ...but it feeds no story-activity credit.
    events, audit = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR_DEFAULT, yaml_sigs,
    )
    assert events == []
    assert audit == []

    # Invariant: david's capacity redistributes over his real Done work.
    capacity = {
        "teams": [{"id": "alpha", "planning_factor": 0.8}],
        "people": [{"id": "david", "name": "David", "role": "Dev",
                    "capacity_per_iteration": 60}],
    }
    done_item = {
        "id": "S-11", "level": "Story", "job_size": 5,
        "contributors": [{"person": "david", "cw": 1.0,
                          "contribution_score": 4.0, "signals": []}],
    }
    results = engine.run_edpa(capacity, HEUR_DEFAULT, [done_item] + events)
    (david,) = results
    assert [i["id"] for i in david["items"]] == ["S-11"]
    assert david["total_derived"] == pytest.approx(60)
    assert david["invariant_ok"] is True
