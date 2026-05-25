"""
Tests for the edpa_flow_metrics MCP tool and timestamp surfacing in edpa_backlog.

Uses a temporary .edpa/ tree with synthetic backlog items that have timestamp
frontmatter. Verifies cycle-time computation, open-item age, throughput,
and the iteration/level filters.

Run: python -m pytest tests/test_mcp_flow_metrics.py -v
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import mcp_server
from mcp_server import (
    _handle_backlog,
    _handle_flow_metrics,
    _handle_item,
    _parse_timestamp,
    load_yaml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_result(result: list) -> dict | list:
    """Extract and parse JSON from a TextContent result list."""
    assert len(result) == 1, f"Expected 1 TextContent, got {len(result)}"
    return json.loads(result[0].text)


def _write_md_item(path: Path, frontmatter: dict) -> None:
    """Write a minimal .md backlog item with YAML frontmatter."""
    import yaml
    fm_text = yaml.dump(frontmatter, default_flow_style=False,
                        allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{fm_text}---\n", encoding="utf-8")


def _make_backlog(tmp_path: Path, items: list[dict]) -> Path:
    """Build a temporary .edpa/backlog/ tree from a list of item dicts.

    Each item dict must contain ``id`` and ``type``. Returns the .edpa/
    root path.
    """
    edpa_root = tmp_path / ".edpa"
    type_to_dir = {
        "Story": "stories",
        "Feature": "features",
        "Epic": "epics",
        "Initiative": "initiatives",
    }
    for item in items:
        dir_name = type_to_dir[item["type"]]
        d = edpa_root / "backlog" / dir_name
        d.mkdir(parents=True, exist_ok=True)
        _write_md_item(d / f"{item['id']}.md", item)
    return edpa_root


# ---------------------------------------------------------------------------
# _parse_timestamp unit tests
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_iso_with_z(self):
        dt = _parse_timestamp("2026-03-01T10:00:00Z")
        assert dt == datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_iso_with_offset(self):
        dt = _parse_timestamp("2026-03-01T10:00:00+00:00")
        assert dt == datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_bare_iso(self):
        dt = _parse_timestamp("2026-03-01T10:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_date_object(self):
        """YAML may parse a bare date string as datetime.date."""
        from datetime import date
        dt = _parse_timestamp(date(2026, 3, 1))
        assert dt == datetime(2026, 3, 1, tzinfo=timezone.utc)

    def test_none(self):
        assert _parse_timestamp(None) is None

    def test_empty_string(self):
        assert _parse_timestamp("") is None

    def test_garbage(self):
        assert _parse_timestamp("not-a-date") is None


# ---------------------------------------------------------------------------
# edpa_flow_metrics — cycle time
# ---------------------------------------------------------------------------


class TestFlowMetricsCycleTime:
    """Cycle time for Done items with both created_at and closed_at."""

    def test_basic_cycle_time(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "Alpha",
                "status": "Done", "iteration": "PI-1.1",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-04T00:00:00Z",
            },
            {
                "id": "S-2", "type": "Story", "title": "Beta",
                "status": "Done", "iteration": "PI-1.1",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-11T00:00:00Z",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, None))

        ct = data["cycle_time"]
        assert ct["count"] == 2
        assert ct["min"] == 3.0
        assert ct["max"] == 10.0
        assert ct["avg"] == 6.5
        assert ct["median"] == 6.5

    def test_single_item_cycle_time(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "Solo",
                "status": "Done",
                "created_at": "2026-01-01T00:00:00Z",
                "closed_at": "2026-01-06T12:00:00Z",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, None))
        ct = data["cycle_time"]
        assert ct["count"] == 1
        assert ct["min"] == ct["max"] == ct["avg"] == ct["median"] == 5.5
        assert ct["p90"] == 5.5


# ---------------------------------------------------------------------------
# edpa_flow_metrics — items without timestamps
# ---------------------------------------------------------------------------


class TestFlowMetricsNoTimestamps:
    """Graceful handling of items that lack timestamp fields."""

    def test_no_timestamps_still_counted(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "NoTS Done",
                "status": "Done", "iteration": "PI-1.1",
            },
            {
                "id": "S-2", "type": "Story", "title": "NoTS Open",
                "status": "In Progress", "iteration": "PI-1.1",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, None))

        assert data["throughput"]["total_done"] == 1
        assert data["throughput"]["total_open"] == 1
        assert data["cycle_time"]["count"] == 0
        assert data["open_items_age"]["count"] == 0
        assert data["skipped_no_timestamps"] == 2

    def test_mixed_timestamps(self, tmp_path):
        """Some items have timestamps, some do not — both are reported."""
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "WithTS",
                "status": "Done",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-03T00:00:00Z",
            },
            {
                "id": "S-2", "type": "Story", "title": "NoTS",
                "status": "Done",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, None))
        assert data["cycle_time"]["count"] == 1
        assert data["throughput"]["total_done"] == 2

        # The item detail list should contain both
        ids = [i["id"] for i in data["items_detail"]]
        assert "S-1" in ids
        assert "S-2" in ids


# ---------------------------------------------------------------------------
# edpa_flow_metrics — iteration filter
# ---------------------------------------------------------------------------


class TestFlowMetricsIterationFilter:
    def test_filter_by_iteration(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "Iter1",
                "status": "Done", "iteration": "PI-1.1",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-05T00:00:00Z",
            },
            {
                "id": "S-2", "type": "Story", "title": "Iter2",
                "status": "Done", "iteration": "PI-1.2",
                "created_at": "2026-04-01T00:00:00Z",
                "closed_at": "2026-04-02T00:00:00Z",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, "PI-1.1", None))
        assert data["throughput"]["total_done"] == 1
        assert data["cycle_time"]["count"] == 1
        assert data["cycle_time"]["min"] == 4.0
        assert data["items_detail"][0]["id"] == "S-1"


# ---------------------------------------------------------------------------
# edpa_flow_metrics — level filter
# ---------------------------------------------------------------------------


class TestFlowMetricsLevelFilter:
    def test_filter_by_level(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "StoryItem",
                "status": "Done",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-05T00:00:00Z",
            },
            {
                "id": "F-1", "type": "Feature", "title": "FeatureItem",
                "status": "Done",
                "created_at": "2026-03-01T00:00:00Z",
                "closed_at": "2026-03-10T00:00:00Z",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, "Feature"))
        assert data["throughput"]["total_done"] == 1
        assert data["cycle_time"]["count"] == 1
        assert data["cycle_time"]["min"] == 9.0
        assert data["items_detail"][0]["id"] == "F-1"


# ---------------------------------------------------------------------------
# edpa_flow_metrics — open items age
# ---------------------------------------------------------------------------


class TestFlowMetricsOpenAge:
    def test_open_item_age(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "WIP",
                "status": "In Progress",
                "created_at": "2026-01-01T00:00:00Z",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, None, None))
        assert data["open_items_age"]["count"] == 1
        # Age must be > 0 (created in the past)
        assert data["open_items_age"]["min"] > 0
        assert data["items_detail"][0]["age_days"] > 0


# ---------------------------------------------------------------------------
# edpa_flow_metrics — empty backlog
# ---------------------------------------------------------------------------


class TestFlowMetricsEmpty:
    def test_missing_backlog_dir(self, tmp_path):
        edpa = tmp_path / ".edpa"
        edpa.mkdir()
        data = parse_result(_handle_flow_metrics(edpa, None, None))
        assert "error" in data

    def test_no_matching_items(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "X",
                "status": "Done", "iteration": "PI-1.1",
            },
        ])
        data = parse_result(_handle_flow_metrics(edpa, "PI-99.99", None))
        assert data["throughput"]["total_items"] == 0
        assert data["cycle_time"]["count"] == 0


# ---------------------------------------------------------------------------
# edpa_backlog — timestamp surfacing
# ---------------------------------------------------------------------------


class TestBacklogTimestamps:
    """Verify that _handle_backlog includes timestamp fields when present."""

    def test_timestamps_appear_when_present(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "WithTS",
                "status": "Done", "iteration": "PI-1.1",
                "created_at": "2026-03-01T10:00:00Z",
                "closed_at": "2026-03-05T10:00:00Z",
                "updated_at": "2026-03-05T12:00:00Z",
            },
        ])
        data = parse_result(_handle_backlog(edpa, None, None, None))
        assert len(data) == 1
        item = data[0]
        assert "created_at" in item
        assert "closed_at" in item
        assert "updated_at" in item
        assert "2026-03-01" in item["created_at"]
        assert "2026-03-05" in item["closed_at"]

    def test_timestamps_absent_when_missing(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "NoTS",
                "status": "Done", "iteration": "PI-1.1",
            },
        ])
        data = parse_result(_handle_backlog(edpa, None, None, None))
        assert len(data) == 1
        item = data[0]
        assert "created_at" not in item
        assert "closed_at" not in item
        assert "updated_at" not in item


# ---------------------------------------------------------------------------
# edpa_item — timestamps pass through
# ---------------------------------------------------------------------------


class TestItemTimestamps:
    """edpa_item returns full frontmatter which includes timestamps."""

    def test_item_includes_timestamps(self, tmp_path):
        mcp_server._load_yaml_cache_clear()
        edpa = _make_backlog(tmp_path, [
            {
                "id": "S-1", "type": "Story", "title": "TS item",
                "status": "Done",
                "created_at": "2026-03-01T10:00:00Z",
                "closed_at": "2026-03-05T10:00:00Z",
            },
        ])
        data = parse_result(_handle_item(edpa, "S-1"))
        assert data["id"] == "S-1"
        assert "created_at" in data
        assert "closed_at" in data


# ---------------------------------------------------------------------------
# list_tools includes edpa_flow_metrics
# ---------------------------------------------------------------------------


def test_list_tools_includes_flow_metrics():
    """list_tools advertises the new edpa_flow_metrics tool."""
    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "edpa_flow_metrics" in names


# ---------------------------------------------------------------------------
# call_tool dispatcher
# ---------------------------------------------------------------------------


def test_call_tool_flow_metrics(tmp_path, monkeypatch):
    """call_tool dispatches edpa_flow_metrics correctly."""
    mcp_server._load_yaml_cache_clear()
    edpa = _make_backlog(tmp_path, [
        {
            "id": "S-1", "type": "Story", "title": "Via dispatch",
            "status": "Done",
            "created_at": "2026-03-01T00:00:00Z",
            "closed_at": "2026-03-06T00:00:00Z",
        },
    ])
    monkeypatch.setenv("EDPA_ROOT", str(edpa))
    result = asyncio.run(mcp_server.call_tool("edpa_flow_metrics", {}))
    data = parse_result(result)
    assert data["throughput"]["total_done"] == 1
    assert data["cycle_time"]["count"] == 1
    assert data["cycle_time"]["min"] == 5.0
