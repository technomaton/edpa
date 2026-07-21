"""Regression tests for D-42 — frontmatter read hardening in the engine.

EDPA's model is that humans/agents hand-edit backlog ``.md`` files. A blank
``status:`` parses as None and a quoted ``js: "5"`` parses as str — both
previously aborted the whole engine run with a context-free traceback
(AttributeError / TypeError), even though validate_syntax.py accepts
float-coercible js values. The engine readers must skip-and-warn instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import engine  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    (root / "backlog" / "stories").mkdir(parents=True)
    (root / "backlog" / "features").mkdir(parents=True)
    (root / "iterations").mkdir()
    return root


def _write_story(edpa_root: Path, item_id: str, frontmatter: str) -> Path:
    """Write a raw story .md so blank/quoted YAML scalars survive verbatim."""
    p = edpa_root / "backlog" / "stories" / f"{item_id}.md"
    p.write_text(
        f"---\nid: {item_id}\ntype: Story\ntitle: T\n{frontmatter}\n---\n",
        encoding="utf-8",
    )
    return p


# ─── load_backlog_items ─────────────────────────────────────────────────────


def test_blank_status_is_skipped_not_crashed(edpa_root: Path) -> None:
    """`status:` with no value parses as None — must not AttributeError."""
    _write_story(edpa_root, "S-1", "status:\njs: 5")
    items, _ = engine.load_backlog_items(edpa_root)
    assert items == []


def test_quoted_js_is_coerced(edpa_root: Path) -> None:
    """js: "5" is validator-blessed (float-coercible) — accept, don't raise."""
    _write_story(edpa_root, "S-1", 'status: Done\njs: "5"')
    items, _ = engine.load_backlog_items(edpa_root)
    assert len(items) == 1
    assert items[0]["job_size"] == pytest.approx(5.0)


def test_unquoted_js_keeps_exact_value(edpa_root: Path) -> None:
    """Well-formed items are untouched by the coercion guard."""
    _write_story(edpa_root, "S-1", "status: Done\njs: 8")
    items, _ = engine.load_backlog_items(edpa_root)
    assert items[0]["job_size"] == 8


def test_non_numeric_js_warns_and_skips(edpa_root: Path, capsys) -> None:
    """Garbage js skips ONE item with a warning — the run keeps going."""
    _write_story(edpa_root, "S-1", 'status: Done\njs: "a lot"')
    _write_story(edpa_root, "S-2", "status: Done\njs: 3")
    items, _ = engine.load_backlog_items(edpa_root)
    assert [i["id"] for i in items] == ["S-2"]
    err = capsys.readouterr().err
    assert "S-1" in err
    assert "js must be numeric" in err
    assert "S-1.md" in err  # warning names the offending file


def test_blank_js_is_skipped(edpa_root: Path) -> None:
    _write_story(edpa_root, "S-1", "status: Done\njs:")
    items, _ = engine.load_backlog_items(edpa_root)
    assert items == []


# ─── load_story_activity_events ─────────────────────────────────────────────


HEUR = {"story_activity": {"credit_factor": 0.40}}
SIG = {
    "type": "yaml_edit", "login": "alice", "weight": 5.0,
    "ref": "commit/abc1234", "detected_at": "2026-05-25T10:00:00Z",
}


def test_story_activity_coerces_quoted_js(edpa_root: Path) -> None:
    _write_story(edpa_root, "S-1", 'status: Implementing\njs: "5"')
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR, {"S-1": [SIG]},
    )
    assert len(events) == 1
    assert events[0]["job_size"] == pytest.approx(5 * 0.40)


def test_story_activity_skips_non_numeric_js(edpa_root: Path, capsys) -> None:
    _write_story(edpa_root, "S-1", "status: Implementing\njs: five")
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR, {"S-1": [SIG]},
    )
    assert events == []
    assert "js must be numeric" in capsys.readouterr().err


def test_story_activity_blank_status_not_crashed(edpa_root: Path) -> None:
    """Blank status == in-flight: still creditable, never a crash."""
    _write_story(edpa_root, "S-1", "status:\njs: 5")
    events, _ = engine.load_story_activity_events(
        edpa_root, "PI-2026-1.1", HEUR, {"S-1": [SIG]},
    )
    assert len(events) == 1


# ─── load_gate_events ───────────────────────────────────────────────────────


ITER_YAML = (
    "iteration:\n"
    "  id: PI-2026-1.1\n  pi: PI-2026-1\n  status: closed\n"
    "  start_date: 2026-04-06\n  end_date: 2026-04-17\n  weeks: 2\n"
)

FEATURE_MD = (
    "---\n"
    "id: F-1\ntype: Feature\ntitle: T\nparent: E-1\n"
    "js: {js}\nstatus: Implementing\niteration: PI-2026-1\n"
    "contributors:\n  - person: alice\n    cw: 1\n"
    "evidence:\n"
    "  - type: state_transition\n"
    "    from_status: Funnel\n"
    "    to_status: Implementing\n"
    "    at: \"2026-04-07T10:00:00+00:00\"\n"
    "    person: alice\n"
    "    ref: commit/abc1234\n"
    "---\n"
)

GATE_HEUR = {"gate_weights": {"Feature": {"Funnel→Implementing": 0.25}}}
PEOPLE = [{"id": "alice", "github": "alice"}]


def _plant_gate_fixture(edpa_root: Path, js: str) -> None:
    (edpa_root / "iterations" / "PI-2026-1.1.yaml").write_text(
        ITER_YAML, encoding="utf-8")
    (edpa_root / "backlog" / "features" / "F-1.md").write_text(
        FEATURE_MD.format(js=js), encoding="utf-8")


def test_gate_event_coerces_quoted_parent_js(edpa_root: Path) -> None:
    _plant_gate_fixture(edpa_root, js='"8"')
    events, _ = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR, people=PEOPLE,
    )
    assert len(events) == 1
    assert events[0]["job_size"] == pytest.approx(8 * 0.25)


def test_gate_event_skips_non_numeric_parent_js(edpa_root: Path, capsys) -> None:
    _plant_gate_fixture(edpa_root, js="huge")
    events, _ = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR, people=PEOPLE,
    )
    assert events == []
    assert "js must be numeric" in capsys.readouterr().err


# ─── D-82: gate-event attribution chain (window → passthrough → author) ─────


FEATURE_MD_WINDOWED = (
    "---\n"
    "id: F-1\ntype: Feature\ntitle: T\nparent: E-1\n"
    "js: 8\nstatus: Implementing\niteration: PI-2026-1\n"
    "contributors:\n  - person: alice\n    cw: 1\n"
    "evidence:\n"
    "  - type: state_transition\n"
    "    from_status: Funnel\n"
    "    to_status: Implementing\n"
    "    at: \"2026-04-07T10:00:00+00:00\"\n"
    "    person: alice\n"
    "    ref: commit/abc1234\n"
    "  - type: yaml_edit\n"
    "    person: bob\n"
    "    weight: 2.0\n"
    "    ref: commit/def5678/F-1.md\n"
    "    at: \"2026-04-07T11:00:00+00:00\"\n"
    "  - type: yaml_edit\n"
    "    person: carol\n"
    "    weight: 1.0\n"
    "    ref: commit/def9999/F-1.md\n"
    "    at: \"2026-04-08T11:00:00+00:00\"\n"
    "---\n"
)

FEATURE_MD_NO_CONTRIBUTORS = (
    "---\n"
    "id: F-1\ntype: Feature\ntitle: T\nparent: E-1\n"
    "js: 8\nstatus: Implementing\niteration: PI-2026-1\n"
    "evidence:\n"
    "  - type: state_transition\n"
    "    from_status: Funnel\n"
    "    to_status: Implementing\n"
    "    at: \"2026-04-07T10:00:00+00:00\"\n"
    "    person: alice\n"
    "    ref: commit/abc1234\n"
    "---\n"
)

FEATURE_MD_ONLY_EXCLUDED_SIGNALS = (
    "---\n"
    "id: F-1\ntype: Feature\ntitle: T\nparent: E-1\n"
    "js: 8\nstatus: Implementing\niteration: PI-2026-1\n"
    "contributors:\n  - person: alice\n    cw: 1\n"
    "evidence:\n"
    "  - type: state_transition\n"
    "    from_status: Funnel\n"
    "    to_status: Implementing\n"
    "    at: \"2026-04-07T10:00:00+00:00\"\n"
    "    person: alice\n"
    "    ref: commit/abc1234\n"
    "  - type: yaml_edit\n"
    "    person: bob\n"
    "    weight: 2.0\n"
    "    ref: commit/old0000/F-1.md\n"
    "    at: \"2026-03-01T11:00:00+00:00\"\n"
    "  - type: agent_contribution\n"
    "    person: _claude\n"
    "    agent: claude-test\n"
    "    weight: 1.0\n"
    "    ref: commit/abc1234/agent/claude-test\n"
    "    at: \"2026-04-07T10:30:00+00:00\"\n"
    "---\n"
)


def _plant_feature(edpa_root: Path, content: str) -> None:
    (edpa_root / "iterations" / "PI-2026-1.1.yaml").write_text(
        ITER_YAML, encoding="utf-8")
    (edpa_root / "backlog" / "features" / "F-1.md").write_text(
        content, encoding="utf-8")


def test_gate_event_prefers_in_window_shares(edpa_root: Path) -> None:
    """D-82 chain step 1: gate contributors are recomputed from the parent's
    IN-WINDOW evidence (bob 2.0 / carol 1.0), NOT copied from the all-time
    contributors[] (alice) — pre-D-82 alice kept scoring at gates in
    iterations she never touched the item (cross-iteration ghost credit)."""
    _plant_feature(edpa_root, FEATURE_MD_WINDOWED)
    events, audit = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR,
        people=[{"id": "alice"}, {"id": "bob"}, {"id": "carol"}],
    )
    assert len(events) == 1
    by_person = {c["person"]: c for c in events[0]["contributors"]}
    assert set(by_person) == {"bob", "carol"}
    assert by_person["bob"]["cw"] == pytest.approx(2 / 3, abs=0.001)
    assert by_person["carol"]["cw"] == pytest.approx(1 / 3, abs=0.001)
    assert audit[0]["attribution"] == "window"


def test_gate_event_passthrough_attribution_without_window_signals(
        edpa_root: Path) -> None:
    """D-82 chain step 2: no in-window credit signals → the all-time
    contributors[] passthrough (pre-D-82 behavior) applies."""
    _plant_feature(edpa_root, FEATURE_MD.format(js="8"))
    events, audit = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR, people=PEOPLE,
    )
    assert [c["person"] for c in events[0]["contributors"]] == ["alice"]
    assert audit[0]["attribution"] == "passthrough"


def test_gate_event_author_attribution_when_no_contributors(
        edpa_root: Path) -> None:
    """D-82 chain step 3 (v1.17.1): no in-window signals AND no
    contributors[] → the transition author is credited at cw=1.0."""
    _plant_feature(edpa_root, FEATURE_MD_NO_CONTRIBUTORS)
    events, audit = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR, people=PEOPLE,
    )
    assert [c["person"] for c in events[0]["contributors"]] == ["alice"]
    assert events[0]["contributors"][0]["cw"] == 1.0
    assert audit[0]["attribution"] == "author"


def test_gate_event_window_ignores_out_of_window_and_agent_signals(
        edpa_root: Path) -> None:
    """D-82 reader exclusions: out-of-window edits don't count, and
    agent_contribution (_claude — not a people.yaml member) never dilutes
    human shares. Both excluded here → passthrough to alice."""
    _plant_feature(edpa_root, FEATURE_MD_ONLY_EXCLUDED_SIGNALS)
    events, audit = engine.load_gate_events(
        edpa_root, "PI-2026-1.1", GATE_HEUR, people=PEOPLE,
    )
    assert [c["person"] for c in events[0]["contributors"]] == ["alice"]
    assert audit[0]["attribution"] == "passthrough"
