"""Tests for V2 MCP write-tool idempotency layer (krok 1.5).

Each write handler is wrapped with ``@_idempotent(tool_name)``: passing
an ``idempotency_key`` makes a second call with the same key return the
cached response instead of running the handler again. Critical for
retry safety (network glitch, client double-tap).
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
    _handle_item_update,
    _handle_item_transition,
    _handle_iteration_create,
    _handle_people_upsert,
    _idempotency_lookup,
    _idempotency_record,
)


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (root / "backlog" / d).mkdir(parents=True)
    (root / "config" / "people.yaml").write_text(
        yaml.safe_dump({"people": [
            {"id": "alice", "name": "Alice", "role": "Dev", "fte": 1.0, "capacity": 80},
        ]})
    )
    yield root
    mcp_server._load_yaml_cache_clear()


def _parse(result: list) -> dict:
    return json.loads(result[0].text)


# ---------------------------------------------------------------------------
# Direct lookup/record helpers
# ---------------------------------------------------------------------------

def test_lookup_returns_none_when_log_missing(edpa_root: Path) -> None:
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "key1") is None


def test_record_then_lookup_roundtrip(edpa_root: Path) -> None:
    _idempotency_record(edpa_root, "edpa_item_create", "key1", '{"id": "I-1"}')
    cached = _idempotency_lookup(edpa_root, "edpa_item_create", "key1")
    assert cached == '{"id": "I-1"}'


def test_lookup_different_key_returns_none(edpa_root: Path) -> None:
    _idempotency_record(edpa_root, "edpa_item_create", "key1", '{"id": "I-1"}')
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "key2") is None


def test_lookup_different_tool_returns_none(edpa_root: Path) -> None:
    _idempotency_record(edpa_root, "edpa_item_create", "key1", '{"id": "I-1"}')
    assert _idempotency_lookup(edpa_root, "edpa_item_update", "key1") is None


def test_empty_key_is_no_op(edpa_root: Path) -> None:
    """Empty/missing key bypasses idempotency — fresh result each time."""
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "") is None
    _idempotency_record(edpa_root, "edpa_item_create", "", '{"id": "X"}')
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "") is None


# ---------------------------------------------------------------------------
# Decorator on real handlers
# ---------------------------------------------------------------------------

def test_create_with_key_returns_same_id_on_retry(edpa_root: Path) -> None:
    first = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "Platform", "idempotency_key": "ulid-A",
    }))
    second = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "DIFFERENT TITLE",  # ignored on retry
        "idempotency_key": "ulid-A",
    }))
    assert first["id"] == second["id"] == "I-1"
    # Only one file on disk — handler not re-run
    files = list((edpa_root / "backlog" / "initiatives").glob("*.md"))
    assert len(files) == 1


def test_create_without_key_always_creates_new(edpa_root: Path) -> None:
    a = _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "A"}))
    b = _parse(_handle_item_create(edpa_root, {"type": "Initiative", "title": "B"}))
    assert a["id"] == "I-1"
    assert b["id"] == "I-2"


def test_create_different_keys_create_different_items(edpa_root: Path) -> None:
    a = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "A", "idempotency_key": "k1",
    }))
    b = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "B", "idempotency_key": "k2",
    }))
    assert a["id"] != b["id"]


def test_create_error_response_not_cached(edpa_root: Path) -> None:
    """ERROR responses are not idempotency-cached → user can fix + retry."""
    # First call: invalid type → ERROR
    err = _handle_item_create(edpa_root, {
        "type": "Invalid", "title": "x", "idempotency_key": "k1",
    })
    assert err[0].text.startswith("ERROR")
    # Retry with same key but valid type → fresh execution, ID I-1
    ok = _parse(_handle_item_create(edpa_root, {
        "type": "Initiative", "title": "x", "idempotency_key": "k1",
    }))
    assert ok["id"] == "I-1"


def test_iteration_create_idempotent(edpa_root: Path) -> None:
    first = _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-01", "end_date": "2026-07-07",
        "idempotency_key": "iter-1",
    }))
    # Second call would normally fail (already exists), but idempotency wins.
    second = _parse(_handle_iteration_create(edpa_root, {
        "id": "PI-2026-2.1", "start_date": "2026-07-01", "end_date": "2026-07-07",
        "idempotency_key": "iter-1",
    }))
    assert first == second


def test_people_upsert_idempotency_key_not_stored_as_field(edpa_root: Path) -> None:
    """idempotency_key must not leak into people.yaml."""
    _parse(_handle_people_upsert(edpa_root, {
        "id": "bob", "name": "Bob", "role": "Dev",
        "idempotency_key": "k1",
    }))
    parsed = yaml.safe_load(
        (edpa_root / "config" / "people.yaml").read_text()
    )
    bob = next(p for p in parsed["people"] if p["id"] == "bob")
    assert "idempotency_key" not in bob


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_expired_entry_not_returned(edpa_root: Path) -> None:
    """Entry older than TTL → lookup returns None (handler will re-run)."""
    # Manually write a stale entry from 2 days ago.
    log = mcp_server._idempotency_path(edpa_root)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({
        "ts": "2026-05-23T10:00:00Z",  # > 24h before "now" in this test run
        "tool": "edpa_item_create",
        "key": "stale-key",
        "response": '{"id": "I-99"}',
    }) + "\n")
    # Even though we wrote it, lookup should refuse because of TTL
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "stale-key") is None


def test_recent_entry_returned(edpa_root: Path) -> None:
    """Fresh entry → lookup returns it."""
    _idempotency_record(edpa_root, "edpa_item_create", "fresh", '{"id": "I-1"}')
    assert _idempotency_lookup(edpa_root, "edpa_item_create", "fresh") == '{"id": "I-1"}'
