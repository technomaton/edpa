"""Tests for V2 MCP write tools (mcp_server.py + id_counter.py).

Covers all 8 write handlers:
  - edpa_item_create
  - edpa_item_update
  - edpa_item_transition
  - edpa_item_link_parent
  - edpa_iteration_create
  - edpa_iteration_close
  - edpa_pi_create
  - edpa_people_upsert

Each test uses an isolated tmp .edpa/ tree (no shared state with the
repo's real .edpa/). The id_counter file lock means concurrent test
processes need a per-test root, which tmp_path provides.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import mcp_server  # noqa: E402
from mcp_server import (  # noqa: E402
    _handle_item_create,
    _handle_item_link_parent,
    _handle_item_transition,
    _handle_item_update,
    _handle_iteration_close,
    _handle_iteration_create,
    _handle_people_upsert,
    _handle_pi_create,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    """Empty .edpa/ tree with minimal config files."""
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    (root / "backlog").mkdir()
    (root / "iterations").mkdir()
    for d in ("initiatives", "epics", "features", "stories", "defects", "events", "risks"):
        (root / "backlog" / d).mkdir()
    (root / "config" / "people.yaml").write_text(
        yaml.safe_dump({"people": [
            {"id": "alice", "name": "Alice", "role": "Dev", "fte": 1.0, "capacity": 80},
        ]})
    )
    yield root
    mcp_server._load_yaml_cache_clear()


def _parse(result: list) -> dict:
    """Decode a successful JSON TextContent response."""
    assert len(result) == 1
    text = result[0].text
    assert not text.startswith("ERROR"), f"unexpected error: {text}"
    return json.loads(text)


def _is_err(result: list) -> bool:
    return len(result) == 1 and result[0].text.startswith("ERROR")


def _read_md(edpa_root: Path, item_id: str) -> dict:
    """Quick helper: load an item's frontmatter via _md_frontmatter."""
    sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))
    from _md_frontmatter import load_md
    file_path = mcp_server._find_item_file(edpa_root, item_id)
    assert file_path is not None
    return load_md(file_path) or {}


# ---------------------------------------------------------------------------
# edpa_item_create
# ---------------------------------------------------------------------------

def test_create_initiative(edpa_root: Path) -> None:
    data = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "Platform 2026",
    }))
    assert data["id"] == "I-1"
    assert data["type"] == "Initiative"
    md = _read_md(edpa_root, "I-1")
    assert md["title"] == "Platform 2026"
    assert md["status"] == "Funnel"


# ---------------------------------------------------------------------------
# WSJF strict defaults (V2.1 Krok C1)
# ---------------------------------------------------------------------------

def test_create_writes_all_wsjf_fields_even_when_unspecified(edpa_root: Path) -> None:
    """V2.1: js/bv/tc/rr_oe/wsjf are always present in YAML (default 0).

    Previously they were omitted when unspecified, which meant the engine
    silently coerced None→0. Strict defaults surface that "this item
    hasn't been WSJF-scored yet" visibly to humans reading the YAML."""
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I",
    }))
    md = _read_md(edpa_root, "I-1")
    for field in ("js", "bv", "tc", "rr_oe"):
        assert field in md, f"{field} missing — strict defaults broken"
        assert md[field] == 0
    assert md["wsjf"] == 0.0  # js=0 → wsjf=0 (not div-by-zero)


def test_create_with_partial_wsjf_zero_fills_rest(edpa_root: Path) -> None:
    """If user passes only --js, bv/tc/rr_oe still get 0 defaults."""
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I", "js": 5,
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["js"] == 5
    assert md["bv"] == 0
    assert md["tc"] == 0
    assert md["rr_oe"] == 0
    assert md["wsjf"] == 0.0


def test_create_wsjf_computed_when_all_inputs_present(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I",
        "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["wsjf"] == round((8 + 3 + 2) / 5, 2)


def test_update_zero_fills_missing_wsjf_fields_on_legacy_items(edpa_root: Path) -> None:
    """Legacy items written before V2.1 may lack js/bv/tc/rr_oe. An
    update operation backfills them to 0 so subsequent reads are
    deterministic."""
    sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))
    from _md_frontmatter import save_md_item
    # Plant a legacy item missing the WSJF block entirely.
    path = edpa_root / "backlog" / "initiatives" / "I-1.md"
    save_md_item(path, {
        "id": "I-1", "type": "Initiative", "title": "Legacy", "status": "Funnel",
    })
    # Touch via update → all WSJF fields should appear at 0.
    _parse(_handle_item_update(edpa_root, {
        "item_id": "I-1", "fields": {"title": "Renamed"},
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["title"] == "Renamed"
    for f in ("js", "bv", "tc", "rr_oe"):
        assert md[f] == 0
    assert md["wsjf"] == 0.0


def test_update_recomputes_wsjf_when_inputs_change_to_zero(edpa_root: Path) -> None:
    """Zeroing one input → wsjf re-derived. (Regression guard: V2.0's
    conditional `if bv or tc or rr` skipped the recompute on
    all-zero-but-still-explicit, leaving stale wsjf.)"""
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I",
        "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["wsjf"] > 0

    _parse(_handle_item_update(edpa_root, {
        "item_id": "I-1", "fields": {"bv": 0, "tc": 0, "rr_oe": 0},
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["wsjf"] == 0.0


def test_create_story_under_feature(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E1", "parent": "I-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Feature", "title": "F1", "parent": "E-1"}))
    data = _parse(_handle_item_create(edpa_root, {
        "type": "Story", "title": "Login flow", "parent": "F-1",
        "js": 5, "bv": 8, "tc": 3, "rr_oe": 2,
    }))
    assert data["id"] == "S-1"
    md = _read_md(edpa_root, "S-1")
    assert md["parent"] == "F-1"
    assert md["wsjf"] == round((8 + 3 + 2) / 5, 2)


def test_create_id_monotonic(edpa_root: Path) -> None:
    for n in range(1, 4):
        data = _parse(_handle_item_create(edpa_root, {
            "type": "Initiative", "title": f"I{n}",
        }))
        assert data["id"] == f"I-{n}"


def test_create_invalid_type_errors(edpa_root: Path) -> None:
    assert _is_err(_handle_item_create(edpa_root, {"type": "Saga", "title": "x"}))


def test_create_empty_title_errors(edpa_root: Path) -> None:
    assert _is_err(_handle_item_create(edpa_root, {"type": "Initiative", "title": "   "}))


def test_create_story_requires_parent(edpa_root: Path) -> None:
    result = _handle_item_create(edpa_root, {"type": "Story", "title": "orphan"})
    assert _is_err(result)
    assert "requires --parent" in result[0].text


def test_create_parent_must_exist(edpa_root: Path) -> None:
    result = _handle_item_create(edpa_root, {
        "type": "Story", "title": "x", "parent": "F-999",
    })
    assert _is_err(result)
    assert "not found" in result[0].text


def test_create_parent_type_mismatch(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I1"}))
    result = _handle_item_create(edpa_root, {
        "type": "Story", "title": "x", "parent": "I-1",
    })
    assert _is_err(result)
    assert "expected" in result[0].text


def test_create_with_body(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I", "body": "## Description\nPilot phase.\n",
    }))
    sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))
    from _md_frontmatter import load_md
    path = mcp_server._find_item_file(edpa_root, "I-1")
    full = load_md(path)
    assert "Pilot phase" in full["body"]


def test_create_event_with_two_letter_prefix(edpa_root: Path) -> None:
    data = _parse(_handle_item_create(edpa_root, {
        "type": "Event", "title": "Sprint review",
    }))
    assert data["id"] == "EV-1"


# ---------------------------------------------------------------------------
# edpa_item_update
# ---------------------------------------------------------------------------

def test_update_changes_fields(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I1"}))
    data = _parse(_handle_item_update(edpa_root, {
        "item_id": "I-1",
        "fields": {"title": "Renamed", "js": 8},
    }))
    assert set(data["updated"]) == {"title", "js"}
    md = _read_md(edpa_root, "I-1")
    assert md["title"] == "Renamed"
    assert md["js"] == 8


def test_update_recomputes_wsjf(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "I", "js": 5, "bv": 8,
    }))
    _parse(_handle_item_update(edpa_root, {
        "item_id": "I-1",
        "fields": {"tc": 3, "rr_oe": 2},
    }))
    md = _read_md(edpa_root, "I-1")
    assert md["wsjf"] == round((8 + 3 + 2) / 5, 2)


def test_update_rejects_status(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    result = _handle_item_update(edpa_root, {
        "item_id": "I-1",
        "fields": {"status": "Done"},
    })
    assert _is_err(result)
    assert "edpa_item_transition" in result[0].text


def test_update_rejects_parent(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    result = _handle_item_update(edpa_root, {
        "item_id": "I-1",
        "fields": {"parent": "I-99"},
    })
    assert _is_err(result)
    assert "edpa_item_link_parent" in result[0].text


def test_update_missing_item_errors(edpa_root: Path) -> None:
    result = _handle_item_update(edpa_root, {
        "item_id": "I-99",
        "fields": {"title": "x"},
    })
    assert _is_err(result)


def test_update_empty_fields_errors(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    assert _is_err(_handle_item_update(edpa_root, {"item_id": "I-1", "fields": {}}))


# ---------------------------------------------------------------------------
# edpa_item_transition
# ---------------------------------------------------------------------------

def test_transition_story_to_done_stamps_closed_at(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E", "parent": "I-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Feature", "title": "F", "parent": "E-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Story", "title": "S", "parent": "F-1"}))
    data = _parse(_handle_item_transition(edpa_root, {
        "item_id": "S-1", "status": "Done",
    }))
    assert data["status"] == "Done"
    assert data["closed_at"] is not None
    md = _read_md(edpa_root, "S-1")
    assert md["closed_at"] == data["closed_at"]


def test_transition_preserves_existing_closed_at(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E", "parent": "I-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Feature", "title": "F", "parent": "E-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Story", "title": "S", "parent": "F-1"}))
    first = _parse(_handle_item_transition(edpa_root, {
        "item_id": "S-1", "status": "Done",
    }))
    _parse(_handle_item_transition(edpa_root, {
        "item_id": "S-1", "status": "Releasing",
    }))
    second = _parse(_handle_item_transition(edpa_root, {
        "item_id": "S-1", "status": "Done",
    }))
    assert second["closed_at"] == first["closed_at"]


def test_transition_invalid_status_for_type(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    # Initiative uses PORTFOLIO_STATUSES; "Validating" is delivery-only.
    result = _handle_item_transition(edpa_root, {
        "item_id": "I-1", "status": "Validating",
    })
    assert _is_err(result)
    assert "not valid for Initiative" in result[0].text


def test_transition_event_skips_status_workflow(edpa_root: Path) -> None:
    """Event/Risk have no enforced workflow → any string accepted."""
    _parse(_handle_item_create(edpa_root, {"type": "Event", "title": "Retro"}))
    data = _parse(_handle_item_transition(edpa_root, {
        "item_id": "EV-1", "status": "completed",
    }))
    assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# edpa_item_link_parent
# ---------------------------------------------------------------------------

def test_link_parent_sets_field(edpa_root: Path) -> None:
    """Defect has flexible parent rules (PARENT_RULES[Defect]=None);
    link_parent on a parentless Defect writes the field unconditionally."""
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E", "parent": "I-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Feature", "title": "F", "parent": "E-1"}))
    _parse(_handle_item_create(edpa_root, {"type": "Defect", "title": "bug"}))

    data = _parse(_handle_item_link_parent(edpa_root, {
        "item_id": "D-1", "parent_id": "F-1",
    }))
    assert data["parent"] == "F-1"
    md = _read_md(edpa_root, "D-1")
    assert md["parent"] == "F-1"


def test_link_parent_rejects_type_mismatch(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I2"}))
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E", "parent": "I-1"}))
    # Try to link Epic to another Epic (should be Initiative).
    _parse(_handle_item_create(edpa_root, {"type": "Epic", "title": "E2", "parent": "I-2"}))
    result = _handle_item_link_parent(edpa_root, {
        "item_id": "E-2", "parent_id": "E-1",
    })
    assert _is_err(result)
    assert "expected" in result[0].text


def test_link_parent_rejects_self(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    result = _handle_item_link_parent(edpa_root, {
        "item_id": "I-1", "parent_id": "I-1",
    })
    assert _is_err(result)
    assert "own parent" in result[0].text


def test_link_parent_missing_parent_errors(edpa_root: Path) -> None:
    _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "I"}))
    result = _handle_item_link_parent(edpa_root, {
        "item_id": "I-1", "parent_id": "I-99",
    })
    assert _is_err(result)


# ---------------------------------------------------------------------------
# edpa_iteration_create
# ---------------------------------------------------------------------------

def test_iteration_create_writes_yaml(edpa_root: Path) -> None:
    data = _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1",
        "start_date": "2026-07-06",
        "end_date": "2026-07-12",
    }))
    assert data["id"] == "PI-2026-2.1"
    iter_path = edpa_root / "iterations" / "PI-2026-2.1.yaml"
    assert iter_path.exists()
    parsed = yaml.safe_load(iter_path.read_text())
    assert parsed["iteration"]["id"] == "PI-2026-2.1"
    assert parsed["iteration"]["pi"] == "PI-2026-2"
    assert parsed["iteration"]["status"] == "planned"


def test_iteration_create_derives_pi_from_root_id(edpa_root: Path) -> None:
    """ID without dot → pi field equals id (e.g. PI-2026-1 → pi: PI-2026-1)."""
    _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-3",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }))
    parsed = yaml.safe_load(
        (edpa_root / "iterations" / "PI-2026-3.yaml").read_text()
    )
    assert parsed["iteration"]["pi"] == "PI-2026-3"


def test_iteration_create_rejects_duplicate(edpa_root: Path) -> None:
    _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-06", "end_date": "2026-07-12",
    }))
    result = _handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-06", "end_date": "2026-07-12",
    })
    assert _is_err(result)
    assert "already exists" in result[0].text


def test_iteration_create_rejects_bad_id(edpa_root: Path) -> None:
    assert _is_err(_handle_iteration_create(edpa_root, {
        "id": "bogus", "start_date": "2026-07-06", "end_date": "2026-07-12",
    }))


# ---------------------------------------------------------------------------
# edpa_pi_create (thin delegate to create_pi.py)
# ---------------------------------------------------------------------------

def test_pi_create_writes_pi_block(edpa_root: Path) -> None:
    data = _parse(_handle_pi_create(edpa_root, {
        "id": "PI-2026-2",
        "start_date": "2026-07-06",
        "pi_iterations": 5,
        "status": "active",
    }))
    assert data["id"] == "PI-2026-2"
    assert data["path"] == ".edpa/iterations/PI-2026-2.yaml"
    pi_path = edpa_root / "iterations" / "PI-2026-2.yaml"
    assert pi_path.exists()
    parsed = yaml.safe_load(pi_path.read_text())
    assert parsed["pi"]["id"] == "PI-2026-2"
    assert parsed["pi"]["status"] == "active"
    assert parsed["pi"]["iteration_weeks"] == 1
    assert parsed["pi"]["pi_iterations"] == 5
    assert parsed["pi"]["start_date"] == "2026-07-06"
    # A PI-level file must NOT carry an iteration: block.
    assert "iteration" not in parsed


def test_pi_create_defaults(edpa_root: Path) -> None:
    """Minimal id → status planning, iteration_weeks 1, no dates/count."""
    _parse(_handle_pi_create(edpa_root, {"id": "PI-2026-4"}))
    parsed = yaml.safe_load(
        (edpa_root / "iterations" / "PI-2026-4.yaml").read_text())
    assert parsed["pi"]["status"] == "planning"
    assert parsed["pi"]["iteration_weeks"] == 1
    assert "pi_iterations" not in parsed["pi"]
    assert "start_date" not in parsed["pi"]


def test_pi_create_rejects_iteration_level_id(edpa_root: Path) -> None:
    """An iteration id (with .N suffix) is not a PI-level id."""
    result = _handle_pi_create(edpa_root, {"id": "PI-2026-2.1"})
    assert _is_err(result)
    assert "PI-YYYY-N" in result[0].text


def test_pi_create_rejects_bad_id(edpa_root: Path) -> None:
    assert _is_err(_handle_pi_create(edpa_root, {"id": "bogus"}))


def test_pi_create_rejects_duplicate(edpa_root: Path) -> None:
    _parse(_handle_pi_create(edpa_root, {"id": "PI-2026-2"}))
    result = _handle_pi_create(edpa_root, {"id": "PI-2026-2"})
    assert _is_err(result)
    assert "already exists" in result[0].text


# ---------------------------------------------------------------------------
# edpa_iteration_close
# ---------------------------------------------------------------------------

def test_iteration_close_sets_status(edpa_root: Path) -> None:
    _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-06", "end_date": "2026-07-12",
    }))
    data = _parse(_handle_iteration_close(edpa_root, {"id": "PI-2026-2.1"}))
    assert data["status"] == "closed"
    parsed = yaml.safe_load(
        (edpa_root / "iterations" / "PI-2026-2.1.yaml").read_text()
    )
    assert parsed["iteration"]["status"] == "closed"
    # Regression: lifecycle "closed" must ALSO be set at the top level, which
    # pi_close / reports / board / the e2e verifier read (nested iteration.status
    # is the planning-state key consumed by loader-lifted readers).
    assert parsed["status"] == "closed"


def test_iteration_close_idempotent(edpa_root: Path) -> None:
    _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-06", "end_date": "2026-07-12",
    }))
    _parse(_handle_iteration_close(edpa_root, {"id": "PI-2026-2.1"}))
    data = _parse(_handle_iteration_close(edpa_root, {"id": "PI-2026-2.1"}))
    assert data.get("already_closed") is True


def test_iteration_close_missing_errors(edpa_root: Path) -> None:
    assert _is_err(_handle_iteration_close(edpa_root, {"id": "PI-2099-1.1"}))


# ---------------------------------------------------------------------------
# edpa_people_upsert
# ---------------------------------------------------------------------------

def test_people_upsert_creates_new(edpa_root: Path) -> None:
    data = _parse(_handle_people_upsert(edpa_root, {
        "id": "bob", "name": "Bob", "role": "Dev", "fte": 0.5, "capacity": 40,
    }))
    assert data["action"] == "created"
    parsed = yaml.safe_load(
        (edpa_root / "config" / "people.yaml").read_text()
    )
    bob = next(p for p in parsed["people"] if p["id"] == "bob")
    assert bob["role"] == "Dev"
    assert bob["fte"] == 0.5


def test_people_upsert_updates_existing(edpa_root: Path) -> None:
    data = _parse(_handle_people_upsert(edpa_root, {
        "id": "alice", "role": "Lead",
    }))
    assert data["action"] == "updated"
    parsed = yaml.safe_load(
        (edpa_root / "config" / "people.yaml").read_text()
    )
    alice = next(p for p in parsed["people"] if p["id"] == "alice")
    assert alice["role"] == "Lead"
    # name preserved from fixture
    assert alice["name"] == "Alice"


def test_people_upsert_new_requires_name(edpa_root: Path) -> None:
    result = _handle_people_upsert(edpa_root, {"id": "charlie", "role": "Dev"})
    assert _is_err(result)
    assert "requires 'name'" in result[0].text


def test_people_upsert_rejects_bad_id(edpa_root: Path) -> None:
    assert _is_err(_handle_people_upsert(edpa_root, {"id": "../etc/passwd"}))
    assert _is_err(_handle_people_upsert(edpa_root, {"id": "UpperCase"}))


def test_people_upsert_rejects_unknown_field(edpa_root: Path) -> None:
    result = _handle_people_upsert(edpa_root, {
        "id": "alice", "salary": 1000,
    })
    assert _is_err(result)


# ---------------------------------------------------------------------------
# Path-traversal hardening
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "S-1; rm -rf /",
    "S--1",
    "lowercase-1",
])
def test_unsafe_item_id_rejected_everywhere(edpa_root: Path, bad: str) -> None:
    for handler, payload in [
        (_handle_item_update, {"item_id": bad, "fields": {"title": "x"}}),
        (_handle_item_transition, {"item_id": bad, "status": "Done"}),
        (_handle_item_link_parent, {"item_id": bad, "parent_id": "I-1"}),
    ]:
        assert _is_err(handler(edpa_root, payload)), f"{handler.__name__} accepted {bad!r}"
