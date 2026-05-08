"""Unit tests for detect_contributors.py — focused on the
`/contribute @person weight:X [as:role]` directive parser added in
v1.10 to close the PR-body manual-attribution gap surfaced by the
2026-05-08 real-evidence E2E."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `plugin/edpa/scripts` importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent /
                      "plugin" / "edpa" / "scripts"))

import detect_contributors as dc  # noqa: E402


# -- parse_contribute_directives ---------------------------------------------


def test_parse_basic_weight_only():
    """A directive with only `weight:X` keeps role unset (caller defaults)."""
    out = dc.parse_contribute_directives("/contribute @alice weight:0.5")
    assert out == {"alice": {"cw": 0.5, "role": None}}


def test_parse_with_explicit_role():
    """`as:owner` lets the directive override the inferred role."""
    out = dc.parse_contribute_directives(
        "/contribute @bob weight:0.7 as:owner")
    assert out == {"bob": {"cw": 0.7, "role": "owner"}}


def test_parse_role_case_insensitive():
    out = dc.parse_contribute_directives(
        "/contribute @bob weight:0.5 as:OWNER")
    assert out["bob"]["role"] == "owner"


def test_parse_multiple_directives():
    body = """
    PR description here.
    /contribute @alice weight:0.5
    /contribute @bob weight:0.3 as:reviewer
    /contribute @charlie weight:0.2 as:consulted
    """
    out = dc.parse_contribute_directives(body)
    assert set(out) == {"alice", "bob", "charlie"}
    assert out["alice"]["cw"] == 0.5
    assert out["bob"] == {"cw": 0.3, "role": "reviewer"}
    assert out["charlie"] == {"cw": 0.2, "role": "consulted"}


def test_parse_drops_invalid_weight_out_of_range():
    """Weights outside [0,1] are silently dropped — keeps detect runs
    robust against typos like `weight:5` (operator meant 0.5)."""
    out = dc.parse_contribute_directives(
        "/contribute @alice weight:1.5\n"
        "/contribute @bob weight:0.5"
    )
    assert "alice" not in out
    assert out["bob"]["cw"] == 0.5


def test_parse_drops_unknown_role():
    out = dc.parse_contribute_directives(
        "/contribute @alice weight:0.5 as:Dev"  # job title, not evidence role
    )
    assert out == {}


def test_parse_drops_non_numeric_weight():
    out = dc.parse_contribute_directives(
        "/contribute @alice weight:abc"
    )
    assert out == {}


def test_parse_handles_empty_body():
    assert dc.parse_contribute_directives("") == {}
    assert dc.parse_contribute_directives(None) == {}


def test_parse_last_directive_wins_for_same_login():
    """If a body has two directives for the same person, the later one
    wins. This lets users `/contribute @x weight:0.3` early in the PR
    description and `/contribute @x weight:0.6 as:owner` later to
    correct themselves without editing the original line."""
    body = (
        "/contribute @alice weight:0.3\n"
        "/contribute @alice weight:0.6 as:owner"
    )
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": {"cw": 0.6, "role": "owner"}}


def test_parse_directive_inline_with_other_text():
    body = "Closes #123. /contribute @alice weight:0.4 as:key Thanks!"
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": {"cw": 0.4, "role": "key"}}


def test_parse_login_with_dashes_underscores():
    body = "/contribute @alice-dev weight:0.5\n/contribute @bob_qa weight:0.3"
    out = dc.parse_contribute_directives(body)
    assert "alice-dev" in out
    assert "bob_qa" in out


def test_parse_case_insensitive_directive_keyword():
    body = "/Contribute @alice weight:0.5"
    out = dc.parse_contribute_directives(body)
    assert out == {"alice": {"cw": 0.5, "role": None}}


def test_parse_evidence_roles_constant_unchanged():
    """If someone widens the EVIDENCE_ROLES set we want the engine
    contract to drift in lockstep — this test pins the canonical set."""
    assert dc.EVIDENCE_ROLES == {"owner", "key", "reviewer", "consulted"}
