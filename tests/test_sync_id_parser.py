"""Regression tests for sync.map_gh_items_to_edpa title-to-ID parser.

Background: commit 5363149 introduced `plen = len(prefix) - 1` (intent was
to generalize the 2-char prefix logic to also accept "D-" / "EV-").
The off-by-one left the dash inside `candidate[plen:]`, so `.isdigit()`
always returned False — `map_gh_items_to_edpa` silently returned an
empty dict for every real GH issue, and `sync push` then treated every
local item as "not yet on GH" and created duplicate issues on each run.

If these tests fail, the parser is broken again and sync push will
duplicate issues. Do NOT relax them.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugin" / "edpa" / "scripts"))

from sync import DEFAULT_SYNC_CONFIG, map_gh_items_to_edpa  # noqa: E402


FIELDS = DEFAULT_SYNC_CONFIG["fields_mapping"]


def _gh_item(issue_num: int, title: str, level: str = "Initiative"):
    """Build a fixture that matches the `gh project item-list --format json` shape."""
    return {
        "id": f"PVTI_test_{issue_num}",
        "title": title,
        "status": "Todo",
        "content": {
            "number": issue_num,
            "title": title,
            "type": "Issue",
            "url": f"https://github.com/x/y/issues/{issue_num}",
        },
        "issueType": {"name": level},
    }


def test_parses_initiative_id():
    data = {"items": [_gh_item(1, "I-1: bootstrap")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert "I-1" in mapped, f"I-1 missing from mapped keys: {list(mapped)}"


def test_parses_two_digit_id():
    data = {"items": [_gh_item(11, "F-11: profile mgmt", level="Feature")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert "F-11" in mapped


def test_parses_three_digit_id():
    data = {"items": [_gh_item(200, "S-200: OMOP parser", level="Story")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert "S-200" in mapped


def test_parses_ev_prefix():
    """Event prefix is 3 chars ("EV-"); regression spot for the off-by-one."""
    data = {"items": [_gh_item(7, "EV-7: PI planning", level="Story")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert "EV-7" in mapped


def test_parses_all_prefixes():
    data = {"items": [
        _gh_item(1, "I-1: init", level="Initiative"),
        _gh_item(2, "E-2: epic", level="Epic"),
        _gh_item(3, "F-3: feat", level="Feature"),
        _gh_item(4, "S-4: story", level="Story"),
        _gh_item(5, "D-5: defect", level="Story"),
        _gh_item(6, "EV-6: event", level="Story"),
    ]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert set(mapped) == {"I-1", "E-2", "F-3", "S-4", "D-5", "EV-6"}


def test_skips_unprefixed_titles():
    data = {"items": [_gh_item(99, "Random title, no prefix")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert mapped == {}


def test_does_not_collide_on_duplicate_ids():
    """If two GH issues share the same EDPA prefix (duplicate-create
    regression), they collide in the mapping. This test documents the
    behaviour, not endorses it — the duplicate-create itself should be
    prevented upstream by sync push consulting issue_map."""
    data = {"items": [
        _gh_item(1, "I-1: original"),
        _gh_item(8, "I-1: duplicate"),
    ]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    assert "I-1" in mapped
    assert len(mapped) == 1
