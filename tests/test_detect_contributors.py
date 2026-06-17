"""Unit tests for detect_contributors.py — v1.11 single-source CW pipeline.

Tests cover:
- /contribute directive parser (additive, no role clause)
- aggregate_signals (per-item normalization to cw shares)
- find_backlog_file, load_people_map, load_signal_weights helpers
- _parse_relative_since
- Edge cases per v1.11 RFC (0 signals, single contributor 100% share)
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent /
                      "plugin" / "edpa" / "scripts"))

import detect_contributors as dc  # noqa: E402


# ─── R-2: multi-contract addressable by id ──────────────────────────────────


def _people_root(tmp_path, people):
    cfg = tmp_path / ".edpa" / "config"
    cfg.mkdir(parents=True)
    (cfg / "people.yaml").write_text(yaml.safe_dump({"people": people}))
    return tmp_path / ".edpa"


def test_load_people_map_resolves_id_to_itself(tmp_path):
    """R-2: two contracts sharing one github handle are each addressable by
    their unique id via `/contribute @<id>` (the shared handle is ambiguous)."""
    root = _people_root(tmp_path, [
        {"id": "bob-arch", "github": "bob-shared", "email": "ba@x"},
        {"id": "bob-pm", "github": "bob-shared", "email": "bp@x"},
    ])
    m = dc.load_people_map(root)
    assert m["bob-arch"] == "bob-arch"
    assert m["bob-pm"] == "bob-pm"
    assert m["bob-shared"] in ("bob-arch", "bob-pm")  # shared handle: one contract


def test_aggregate_credits_contract_by_id(tmp_path):
    """A /contribute signal addressed to an id credits that exact id even when
    the github handle is shared with another contract."""
    root = _people_root(tmp_path, [
        {"id": "bob-arch", "github": "bob-shared"},
        {"id": "bob-pm", "github": "bob-shared"},
    ])
    out = dc.aggregate_signals(
        [{"type": "manual:commit_message", "login": "bob-pm",
          "weight": 3.0, "ref": "commit/x/contrib/bob-pm"}],
        dc.load_people_map(root),
    )
    assert out is not None and out[0]["person"] == "bob-pm"


# ─── parse_contribute_directives ────────────────────────────────────────────


def test_parse_basic_weight_only():
    """v1.11: directive returns {login: weight} — no role classification."""
    out = dc.parse_contribute_directives("/contribute @alice weight:0.5")
    assert out == {"alice": 0.5}


def test_parse_role_clause_silently_ignored():
    """`as:role` clause is parsed by the regex but stripped — v1.11 design
    treats /contribute as a pure additive signal. Role is derived at
    display time from signal type."""
    out = dc.parse_contribute_directives(
        "/contribute @bob weight:0.7 as:owner"
    )
    # Only the login + weight survives; role information is dropped.
    assert out == {"bob": 0.7}


def test_parse_multiple_directives_different_logins():
    body = textwrap.dedent("""
        Closes #137.
        /contribute @alice weight:0.5
        /contribute @bob weight:0.3
        /contribute @charlie weight:0.2
    """)
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": 0.5, "bob": 0.3, "charlie": 0.2}


def test_parse_multiple_directives_same_login_stack():
    """v1.11: multiple /contribute lines for the same login on the same
    surface stack additively. Each is a separate signal contribution."""
    body = (
        "/contribute @alice weight:0.3\n"
        "/contribute @alice weight:0.4\n"
        "/contribute @alice weight:0.1"
    )
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": pytest.approx(0.8)}


def test_parse_drops_negative_weight():
    out = dc.parse_contribute_directives(
        "/contribute @alice weight:-0.5\n/contribute @bob weight:0.5"
    )
    assert "alice" not in out
    assert out["bob"] == 0.5


def test_parse_accepts_weight_above_1():
    """v1.11 allows weights > 1.0 — they're additive signal contributions,
    not normalized cw values. The per-item normalization clamps the final
    cw to [0,1] regardless of how big a single signal weight is."""
    out = dc.parse_contribute_directives("/contribute @alice weight:5.0")
    assert out == {"alice": 5.0}


def test_parse_drops_non_numeric_weight():
    out = dc.parse_contribute_directives("/contribute @alice weight:abc")
    assert out == {}


def test_parse_handles_empty_body():
    assert dc.parse_contribute_directives("") == {}
    assert dc.parse_contribute_directives(None) == {}


def test_parse_directive_inline_with_other_text():
    body = "Closes #123. /contribute @alice weight:0.4 Thanks!"
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": 0.4}


def test_parse_login_with_dashes_underscores():
    body = "/contribute @alice-dev weight:0.5\n/contribute @bob_qa weight:0.3"
    out = dc.parse_contribute_directives(body)
    assert "alice-dev" in out
    assert "bob_qa" in out


def test_parse_case_insensitive_directive_keyword():
    body = "/Contribute @alice weight:0.5"
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": 0.5}


# ─── aggregate_signals (per-item normalization) ─────────────────────────────


def test_aggregate_basic_three_persons():
    """Standard case: three contributors with different signal mixes.
    cw is per-item share, must sum to 1.0."""
    sigs = [
        {"type": "assignee", "ref": "issue#1", "login": "turyna",
         "weight": 4.0, "detected_at": "2026-05-08T12:00:00Z"},
        {"type": "commit_author", "ref": "pr#10/commit/abc",
         "login": "turyna", "weight": 1.0,
         "detected_at": "2026-05-08T12:00:00Z"},
        {"type": "pr_author", "ref": "pr#10", "login": "mtury",
         "weight": 2.0, "detected_at": "2026-05-08T12:00:00Z"},
        {"type": "issue_comment", "ref": "issue#1/comment/c1",
         "login": "jurby", "weight": 0.5,
         "detected_at": "2026-05-08T12:00:00Z"},
    ]
    people_map = {"turyna": "turyna", "mtury": "mtury", "jurby": "jurby"}
    result = dc.aggregate_signals(sigs, people_map)
    assert result is not None
    assert len(result) == 3
    by_person = {c["person"]: c for c in result}
    assert by_person["turyna"]["contribution_score"] == 5.0
    assert by_person["mtury"]["contribution_score"] == 2.0
    assert by_person["jurby"]["contribution_score"] == 0.5
    assert by_person["turyna"]["cw"] == pytest.approx(5.0 / 7.5, abs=0.001)
    assert by_person["mtury"]["cw"] == pytest.approx(2.0 / 7.5, abs=0.001)
    assert by_person["jurby"]["cw"] == pytest.approx(0.5 / 7.5, abs=0.001)
    cw_sum = sum(c["cw"] for c in result)
    assert cw_sum == pytest.approx(1.0, abs=0.001)


def test_aggregate_single_contributor_full_share():
    sigs = [
        {"type": "assignee", "ref": "issue#42", "login": "alice",
         "weight": 4.0, "detected_at": "2026-05-08T12:00:00Z"},
    ]
    people_map = {"alice": "alice"}
    result = dc.aggregate_signals(sigs, people_map)
    assert len(result) == 1
    assert result[0]["person"] == "alice"
    assert result[0]["cw"] == 1.0
    assert result[0]["contribution_score"] == 4.0


def test_aggregate_zero_signals_returns_none():
    """v1.11 edge case: warn-and-skip path. Caller decides what to do."""
    assert dc.aggregate_signals([], {}) is None


def test_aggregate_resolves_login_via_people_map():
    """GitHub login should be mapped to canonical person id."""
    sigs = [
        {"type": "pr_author", "ref": "pr#1", "login": "MartinTuryna",
         "weight": 2.0, "detected_at": "2026-05-08T12:00:00Z"},
    ]
    people_map = {"martinturyna": "turyna"}  # case-folded keys
    result = dc.aggregate_signals(sigs, people_map)
    assert len(result) == 1
    assert result[0]["person"] == "turyna"


def test_aggregate_signals_sorted_deterministic():
    """Two detect runs on identical state must produce byte-identical
    YAML — signals[] sorted by (type, ref) inside each contributor."""
    sigs = [
        {"type": "commit_author", "ref": "pr#1/commit/zzz", "login": "a",
         "weight": 1.0, "detected_at": "t"},
        {"type": "commit_author", "ref": "pr#1/commit/aaa", "login": "a",
         "weight": 1.0, "detected_at": "t"},
        {"type": "assignee", "ref": "issue#1", "login": "a",
         "weight": 4.0, "detected_at": "t"},
    ]
    result = dc.aggregate_signals(sigs, {"a": "a"})
    types_and_refs = [(s["type"], s["ref"]) for s in result[0]["signals"]]
    assert types_and_refs == [
        ("assignee", "issue#1"),
        ("commit_author", "pr#1/commit/aaa"),
        ("commit_author", "pr#1/commit/zzz"),
    ]


def test_aggregate_persons_sorted_by_score_desc():
    """Highest contributor first in YAML for human readability."""
    sigs = [
        {"type": "issue_comment", "ref": "issue#1/c/1", "login": "low",
         "weight": 0.5, "detected_at": "t"},
        {"type": "assignee", "ref": "issue#1", "login": "high",
         "weight": 4.0, "detected_at": "t"},
        {"type": "pr_author", "ref": "pr#1", "login": "mid",
         "weight": 2.0, "detected_at": "t"},
    ]
    result = dc.aggregate_signals(sigs, {})
    persons_in_order = [c["person"] for c in result]
    assert persons_in_order == ["high", "mid", "low"]


def test_aggregate_strips_login_from_signals():
    """The internal `login` field used during aggregation must NOT leak
    into the persisted YAML — only person+cw+signals(type/ref/weight/...)."""
    sigs = [
        {"type": "assignee", "ref": "issue#1", "login": "alice",
         "weight": 4.0, "detected_at": "t"},
    ]
    result = dc.aggregate_signals(sigs, {})
    assert "login" not in result[0]["signals"][0]


# ─── helpers ────────────────────────────────────────────────────────────────


def test_extract_item_ids():
    text = "PR title for S-200, fixes F-100 and E-10. Touches I-1 maybe T-3."
    assert set(dc.extract_item_ids(text)) == {"S-200", "F-100", "E-10",
                                              "I-1", "T-3"}


def test_extract_item_ids_handles_none():
    assert dc.extract_item_ids("") == []
    assert dc.extract_item_ids(None) == []


def test_load_signal_weights_falls_back_to_defaults(tmp_path):
    """No config → return DEFAULT_SIGNAL_WEIGHTS."""
    edpa_root = tmp_path / ".edpa"
    edpa_root.mkdir()
    weights = dc.load_signal_weights(edpa_root)
    assert weights == dc.DEFAULT_SIGNAL_WEIGHTS


def test_load_signal_weights_overrides_from_config(tmp_path):
    edpa_root = tmp_path / ".edpa"
    (edpa_root / "config").mkdir(parents=True)
    (edpa_root / "config" / "cw_heuristics.yaml").write_text(yaml.safe_dump({
        "signals": {"commit_author": 5.0, "issue_comment": 1.0},
    }))
    weights = dc.load_signal_weights(edpa_root)
    assert weights["commit_author"] == 5.0
    assert weights["issue_comment"] == 1.0
    # Non-overridden keys keep defaults
    assert weights["pr_reviewer"] == dc.DEFAULT_SIGNAL_WEIGHTS["pr_reviewer"]


def test_load_people_map(tmp_path):
    edpa_root = tmp_path / ".edpa"
    (edpa_root / "config").mkdir(parents=True)
    (edpa_root / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [
            {"id": "turyna", "github": "MartinTuryna", "email": "m@x.cz"},
            {"id": "jurby", "github": "jurby"},
        ]
    }))
    m = dc.load_people_map(edpa_root)
    # Lookups are case-folded
    assert m["martinturyna"] == "turyna"
    assert m["m@x.cz"] == "turyna"
    assert m["jurby"] == "jurby"


def test_find_backlog_file(tmp_path):
    edpa_root = tmp_path / ".edpa"
    (edpa_root / "backlog" / "stories").mkdir(parents=True)
    (edpa_root / "backlog" / "stories" / "S-1.md").touch()
    (edpa_root / "backlog" / "features").mkdir(parents=True)
    (edpa_root / "backlog" / "features" / "F-1.md").touch()
    assert dc.find_backlog_file(edpa_root, "S-1").name == "S-1.md"
    assert dc.find_backlog_file(edpa_root, "F-1").name == "F-1.md"
    assert dc.find_backlog_file(edpa_root, "S-99") is None


# ─── _parse_relative_since ─────────────────────────────────────────────────


def test_parse_relative_since_days():
    dt = dc._parse_relative_since("7days")
    assert dt is not None
    # Should be approximately 7 days ago (within seconds)
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    delta = now - dt
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_parse_relative_since_weeks():
    dt = dc._parse_relative_since("2weeks")
    from datetime import datetime, timezone, timedelta
    delta = datetime.now(timezone.utc) - dt
    assert timedelta(days=13, hours=23) < delta < timedelta(days=14, hours=1)


def test_parse_relative_since_iso_date():
    dt = dc._parse_relative_since("2026-01-15")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 15


def test_parse_relative_since_invalid_returns_none():
    assert dc._parse_relative_since("garbage") is None
    assert dc._parse_relative_since("") is None


# ─── _signal helper structure ───────────────────────────────────────────────


def test_signal_record_shape():
    sig = dc._signal("assignee", "issue#1", "alice", 4.0)
    assert sig["type"] == "assignee"
    assert sig["ref"] == "issue#1"
    assert sig["login"] == "alice"
    assert sig["weight"] == 4.0
    assert "detected_at" in sig
    assert "excerpt" not in sig  # only set when explicitly provided


def test_signal_with_excerpt():
    sig = dc._signal("manual:pr_body", "pr#1/body", "alice", 0.5,
                     excerpt="/contribute @alice weight:0.5")
    assert sig["excerpt"] == "/contribute @alice weight:0.5"


def test_excerpt_for_finds_matching_line():
    body = textwrap.dedent("""
        Closes #137

        /contribute @turyna weight:0.5
        /contribute @bob weight:0.3
    """)
    line = dc._excerpt_for(body, "turyna")
    assert "/contribute @turyna weight:0.5" in line


def test_excerpt_for_returns_empty_when_no_match():
    assert dc._excerpt_for("just text, no directives", "alice") == ""
