"""D-73 — story-activity credit must be scoped to THIS iteration's signals.

The synthetic ``S-<id>@activity`` event credits in-flight refinement work
before a Story reaches Done. Regression (D-62 adjacency): the event copied
the Story's frontmatter ``contributors[]`` WHOLESALE — cw shares aggregated
from ALL-TIME evidence — so a person who edited the Story in an EARLIER
iteration received story-activity credit in a LATER one. The shares must
instead be recomputed from ONLY the iteration-windowed, non-neutralized
(weight>0, not out_of_iteration — consistent with D-62) yaml_edit signals
that actually fed the event.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import engine  # noqa: E402
from _md_frontmatter import save_md_item  # noqa: E402


HEUR = {"story_activity": {"credit_factor": 0.40}}


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "backlog" / "stories").mkdir(parents=True)
    (root / "iterations").mkdir()
    return root


def _materialized_yaml_edit(person: str, weight: float, at: str,
                            tags=None) -> dict:
    """Materialized evidence[] shape (resolved ``person`` id, ``at`` ISO) —
    what the engine actually reads via ``_yaml_edit_from_evidence``, matching
    the E2E story fixtures (S-10.md) and ``_neutralized_signal`` in
    test_story_activity_events.py. NOT the pre-materialization ``login`` shape.
    """
    return {
        "type": "yaml_edit", "person": person,
        "weight": weight, "raw_weight": weight, "discount": 1.0,
        "ref": f"commit/{person[:4]}0000/S-20.md", "at": at,
        "tags": list(tags or []),
    }


# Two-iteration Story: alice groomed it in PI-2026-1.1, bob in PI-2026-1.2.
# The frontmatter contributors[] is the ALL-TIME aggregate (50/50) — this is
# exactly what the buggy path copied wholesale into the activity event.
ALLTIME_CONTRIBUTORS = [
    {"person": "alice", "cw": 0.5, "contribution_score": 5.0, "signals": []},
    {"person": "bob", "cw": 0.5, "contribution_score": 5.0, "signals": []},
]


def _plant_two_iter_story(edpa_root: Path) -> None:
    save_md_item(edpa_root / "backlog" / "stories" / "S-20.md", {
        "id": "S-20", "type": "Story", "title": "Spans two iterations",
        "status": "Implementing", "js": 10,
        "contributors": ALLTIME_CONTRIBUTORS,
    })


def test_activity_credit_scoped_to_window_not_all_time(edpa_root: Path) -> None:
    """Only bob edited S-20 inside PI-2026-1.2 → only bob is credited, even
    though the frontmatter contributors[] also lists alice (her work landed
    in PI-2026-1.1)."""
    _plant_two_iter_story(edpa_root)
    yaml_sigs = {"S-20": [
        _materialized_yaml_edit("bob", 3.0, "2026-02-05T10:00:00+00:00"),
    ]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR, yaml_sigs,
    )
    assert len(events) == 1
    contribs = events[0]["contributors"]
    people = {c["person"] for c in contribs}
    assert people == {"bob"}, f"alice leaked all-time credit into window: {people}"
    assert contribs[0]["cw"] == pytest.approx(1.0)


def test_activity_shares_split_by_windowed_weight(edpa_root: Path) -> None:
    """Two people active in-window → shares proportional to their in-window
    yaml_edit weight, NOT the frontmatter cw (which is 50/50 alice/bob)."""
    _plant_two_iter_story(edpa_root)
    yaml_sigs = {"S-20": [
        _materialized_yaml_edit("bob", 3.0, "2026-02-05T10:00:00+00:00"),
        _materialized_yaml_edit("carol", 1.0, "2026-02-06T10:00:00+00:00"),
    ]}
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR, yaml_sigs,
    )
    cw = {c["person"]: c["cw"] for c in events[0]["contributors"]}
    assert cw == {"bob": pytest.approx(0.75), "carol": pytest.approx(0.25)}
    assert "alice" not in cw  # all-time-only contributor must not appear
    assert sum(cw.values()) == pytest.approx(1.0)


def test_neutralized_windowed_signal_excluded_from_shares(edpa_root: Path) -> None:
    """A neutralized (weight 0 + out_of_iteration) in-window signal earns no
    share and does not dilute the live editors — consistent with D-62."""
    _plant_two_iter_story(edpa_root)
    neutral = _materialized_yaml_edit(
        "alice", 0, "2026-02-04T10:00:00+00:00", tags=["out_of_iteration"])
    live = _materialized_yaml_edit("bob", 4.0, "2026-02-05T10:00:00+00:00")
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR, {"S-20": [neutral, live]},
    )
    cw = {c["person"]: c["cw"] for c in events[0]["contributors"]}
    assert cw == {"bob": pytest.approx(1.0)}


def test_windowed_recompute_end_to_end_invariant_holds(edpa_root: Path) -> None:
    """Full E2E shape: S-20 evidence[] holds yaml_edit signals from two
    iterations; the reader windows to PI-2026-1.2, the activity event credits
    only the in-window editor (bob), and each person's derived hours still
    sum to capacity (per-person invariant preserved).
    """
    save_md_item(edpa_root / "backlog" / "stories" / "S-20.md", {
        "id": "S-20", "type": "Story", "title": "Spans two iterations",
        "status": "Implementing", "js": 10,
        "contributors": ALLTIME_CONTRIBUTORS,
        "evidence": [
            # alice's refinement — PI-2026-1.1, BEFORE the target window.
            _materialized_yaml_edit("alice", 5.0, "2026-01-10T10:00:00+00:00"),
            # bob's refinement — inside PI-2026-1.2's window.
            _materialized_yaml_edit("bob", 5.0, "2026-02-05T10:00:00+00:00"),
        ],
    })
    (edpa_root / "iterations" / "PI-2026-1.2.yaml").write_text(
        "iteration:\n  id: PI-2026-1.2\n"
        "  start_date: '2026-01-26'\n  end_date: '2026-02-13'\n",
        encoding="utf-8",
    )
    from transitions import parse_iteration_dates  # noqa: E402
    start, end = parse_iteration_dates(
        edpa_root / "iterations" / "PI-2026-1.2.yaml")

    # Reader windows evidence[] to bob's in-window signal only.
    yaml_sigs = engine._yaml_edit_from_evidence(edpa_root, start, end)
    assert len(yaml_sigs.get("S-20", [])) == 1
    assert yaml_sigs["S-20"][0]["person"] == "bob"

    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.2", HEUR, yaml_sigs,
    )
    assert {c["person"] for c in events[0]["contributors"]} == {"bob"}

    capacity = {
        "teams": [{"id": "alpha", "planning_factor": 0.8}],
        "people": [
            {"id": "alice", "name": "Alice", "role": "Dev",
             "capacity_per_iteration": 60},
            {"id": "bob", "name": "Bob", "role": "Dev",
             "capacity_per_iteration": 60},
        ],
    }
    # alice's real PI-2026-1.2 delivery is a separate Done story.
    done = {"id": "S-19", "level": "Story", "job_size": 5,
            "contributors": [{"person": "alice", "cw": 1.0,
                              "contribution_score": 4.0, "signals": []}]}
    results = engine.run_edpa(capacity, HEUR, [done] + events)
    by_id = {r["id"]: r for r in results}

    # Bug repro: under the old wholesale copy, alice's items would include
    # 'S-20@activity' (her all-time 0.5 share). Scoped recompute keeps it
    # bob-only.
    assert "S-20@activity" not in {i["id"] for i in by_id["alice"]["items"]}
    assert "S-20@activity" in {i["id"] for i in by_id["bob"]["items"]}
    assert by_id["alice"]["total_derived"] == pytest.approx(60)
    assert by_id["bob"]["total_derived"] == pytest.approx(60)
    assert all(r["invariant_ok"] for r in results)
