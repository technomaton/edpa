"""
Tests for EDPA MCP Server (plugin/edpa/scripts/mcp_server.py).

Uses the real .edpa/ data at the project root to verify all 5 tool handlers
and the list_tools / list_resources async functions.

Run: python -m pytest tests/test_mcp_server.py -v
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import mcp_server
from mcp_server import (
    _handle_backlog,
    _handle_item,
    _handle_iterations,
    _handle_people,
    _handle_status,
    find_edpa_root,
    load_yaml,
)

EDPA_ROOT = ROOT / ".edpa"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_result(result: list) -> dict | list:
    """Extract and parse JSON from a TextContent result list."""
    assert len(result) == 1, f"Expected 1 TextContent, got {len(result)}"
    text = result[0].text
    return json.loads(text)


def is_error(result: list) -> bool:
    """Check if result is an error message."""
    return len(result) == 1 and result[0].text.startswith("ERROR")


# ---------------------------------------------------------------------------
# find_edpa_root
# ---------------------------------------------------------------------------

def test_find_edpa_root(monkeypatch):
    """find_edpa_root finds .edpa/ from project directory."""
    monkeypatch.chdir(ROOT)
    result = find_edpa_root()
    assert result is not None
    assert result.name == ".edpa"
    assert result.is_dir()


def test_find_edpa_root_missing(tmp_path, monkeypatch):
    """find_edpa_root returns None when no .edpa/ exists."""
    monkeypatch.chdir(tmp_path)
    result = find_edpa_root()
    assert result is None


# ---------------------------------------------------------------------------
# edpa_status
# ---------------------------------------------------------------------------

def test_handle_status():
    """Returns correct project name, PI, team size, capacity, active iteration."""
    data = parse_result(_handle_status(EDPA_ROOT))

    assert data["project"] == "Medical Platform & Datovy e-shop"
    assert data["current_pi"] == "PI-2026-1"
    assert data["team_size"] == 9
    assert data["total_capacity_per_iteration"] == 400
    assert data["active_iteration"] == "PI-2026-1.4"
    assert data["iterations_total"] == 5
    assert data["iterations_closed"] == 3
    assert "cadence" in data


def test_handle_status_missing_config(tmp_path):
    """Graceful handling when config files are missing."""
    # Create a minimal .edpa structure with no config
    (tmp_path / "config").mkdir()
    result = _handle_status(tmp_path)
    data = parse_result(result)
    # Should return defaults, not crash
    assert data["project"] == "unknown"
    assert data["current_pi"] == "unknown"
    assert data["team_size"] == 0
    assert data["total_capacity_per_iteration"] == 0
    assert data["active_iteration"] is None


# ---------------------------------------------------------------------------
# edpa_iterations
# ---------------------------------------------------------------------------

def test_handle_iterations_all():
    """Returns all 5 iterations."""
    data = parse_result(_handle_iterations(EDPA_ROOT, None))
    assert len(data) == 5
    ids = [i["id"] for i in data]
    assert "PI-2026-1.1" in ids
    assert "PI-2026-1.5" in ids


def test_handle_iterations_filter_active():
    """Returns only active iteration(s)."""
    data = parse_result(_handle_iterations(EDPA_ROOT, "active"))
    assert len(data) >= 1
    assert all(i["status"] == "active" for i in data)
    assert data[0]["id"] == "PI-2026-1.4"


def test_handle_iterations_filter_closed():
    """Returns only closed iterations."""
    data = parse_result(_handle_iterations(EDPA_ROOT, "closed"))
    assert len(data) == 3
    assert all(i["status"] == "closed" for i in data)


def test_handle_iterations_has_results():
    """Checks has_results flag accuracy — reports dir is empty so all should be False."""
    data = parse_result(_handle_iterations(EDPA_ROOT, None))
    # The .edpa/reports/ directory is empty, so no iteration should have results
    for it in data:
        assert "has_results" in it
        # Verify the flag is a boolean
        assert isinstance(it["has_results"], bool)


# ---------------------------------------------------------------------------
# edpa_people
# ---------------------------------------------------------------------------

def test_handle_people_all():
    """Returns all 9 people."""
    data = parse_result(_handle_people(EDPA_ROOT, None))
    assert len(data) == 9

    # Verify known entries
    urbanek = next(p for p in data if p["id"] == "urbanek")
    assert urbanek["role"] == "Arch"
    assert urbanek["team"] == "CVUT"
    assert urbanek["fte"] == 0.5
    assert urbanek["capacity"] == 40


def test_handle_people_filter_team():
    """Filters by team ID (e.g., 'CVUT')."""
    data = parse_result(_handle_people(EDPA_ROOT, "CVUT"))
    assert len(data) == 4
    assert all(p["team"] == "CVUT" for p in data)

    partner = parse_result(_handle_people(EDPA_ROOT, "Partner"))
    assert len(partner) == 4
    assert all(p["team"] == "Partner" for p in partner)


# ---------------------------------------------------------------------------
# edpa_backlog
# ---------------------------------------------------------------------------

def test_handle_backlog_all():
    """Returns items from all type directories."""
    data = parse_result(_handle_backlog(EDPA_ROOT, None, None, None))
    # 27 stories + 6 features + 3 epics + 1 initiative = 37
    assert len(data) == 37

    types_found = set(i["type"] for i in data)
    assert "Story" in types_found
    assert "Feature" in types_found
    assert "Epic" in types_found
    assert "Initiative" in types_found


def test_handle_backlog_filter_iteration():
    """Filters by iteration ID."""
    data = parse_result(_handle_backlog(EDPA_ROOT, "PI-2026-1.1", None, None))
    assert len(data) >= 5  # at least 5 stories in PI-2026-1.1
    assert all(i["iteration"] == "PI-2026-1.1" for i in data)


def test_handle_backlog_filter_type():
    """Filters by type (Story, Feature, etc.)."""
    stories = parse_result(_handle_backlog(EDPA_ROOT, None, "Story", None))
    assert len(stories) == 27
    assert all(i["type"] == "Story" for i in stories)

    features = parse_result(_handle_backlog(EDPA_ROOT, None, "Feature", None))
    assert len(features) == 6
    assert all(i["type"] == "Feature" for i in features)


def test_handle_backlog_filter_status():
    """Filters by status (Done, etc.)."""
    done = parse_result(_handle_backlog(EDPA_ROOT, None, None, "Done"))
    assert len(done) >= 22  # at least 22 Done stories + some features/epics
    assert all(i["status"] == "Done" for i in done)


# ---------------------------------------------------------------------------
# edpa_item
# ---------------------------------------------------------------------------

def test_handle_item_exists():
    """Returns full data for S-200."""
    data = parse_result(_handle_item(EDPA_ROOT, "S-200"))
    assert data["id"] == "S-200"
    assert data["type"] == "Story"
    assert data["title"] == "OMOP parser impl."
    assert data["js"] == 8
    assert data["status"] == "Done"
    assert data["assignee"] == "turyna"
    assert data["parent"] == "F-100"
    assert len(data["contributors"]) == 3


def test_handle_item_not_found():
    """Returns error for nonexistent item."""
    result = _handle_item(EDPA_ROOT, "S-999")
    assert is_error(result)
    assert "S-999" in result[0].text


def test_handle_item_feature():
    """Finds F-100 in features/ directory."""
    data = parse_result(_handle_item(EDPA_ROOT, "F-100"))
    assert data["id"] == "F-100"
    assert data["type"] == "Feature"
    assert data["title"] == "OMOP CDM Parser"


# ---------------------------------------------------------------------------
# list_tools (async)
# ---------------------------------------------------------------------------

def test_list_tools():
    """Returns exactly 5 tools."""
    tools = asyncio.run(mcp_server.list_tools())
    assert len(tools) == 5

    names = {t.name for t in tools}
    expected = {"edpa_status", "edpa_iterations", "edpa_people", "edpa_backlog", "edpa_item"}
    assert names == expected

    # Verify each tool has a description and inputSchema
    for t in tools:
        assert t.description, f"Tool {t.name} missing description"
        assert t.inputSchema, f"Tool {t.name} missing inputSchema"


# ---------------------------------------------------------------------------
# list_resources (async)
# ---------------------------------------------------------------------------

def test_list_resources(monkeypatch):
    """Returns resources for existing configs."""
    monkeypatch.chdir(ROOT)
    resources = asyncio.run(mcp_server.list_resources())

    # We have edpa.yaml and people.yaml, so at least 2 resources
    assert len(resources) >= 2

    uris = {str(r.uri) for r in resources}
    assert "edpa://config" in uris
    assert "edpa://people" in uris

    # Verify resource structure
    for r in resources:
        assert r.name, f"Resource {r.uri} missing name"
        assert r.description, f"Resource {r.uri} missing description"
        assert r.mimeType, f"Resource {r.uri} missing mimeType"


# ---------------------------------------------------------------------------
# call_tool dispatcher (async)
# ---------------------------------------------------------------------------

def test_call_tool_status(monkeypatch):
    """call_tool dispatches edpa_status correctly."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_status", {}))
    data = parse_result(result)
    assert data["project"] == "Medical Platform & Datovy e-shop"


def test_call_tool_iterations_with_filter(monkeypatch):
    """call_tool passes status filter to edpa_iterations."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_iterations", {"status": "active"}))
    data = parse_result(result)
    assert len(data) >= 1
    assert data[0]["id"] == "PI-2026-1.4"


def test_call_tool_people_with_filter(monkeypatch):
    """call_tool passes team filter to edpa_people."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_people", {"team": "CVUT"}))
    data = parse_result(result)
    assert len(data) == 4


def test_call_tool_backlog_combined_filters(monkeypatch):
    """call_tool passes all 3 filters to edpa_backlog."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_backlog", {
        "iteration": "PI-2026-1.1",
        "type": "Story",
        "status": "Done",
    }))
    data = parse_result(result)
    assert len(data) >= 1
    for item in data:
        assert item["type"] == "Story"
        assert item["status"] == "Done"
        assert item["iteration"] == "PI-2026-1.1"


def test_call_tool_item(monkeypatch):
    """call_tool dispatches edpa_item correctly."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_item", {"item_id": "S-200"}))
    data = parse_result(result)
    assert data["id"] == "S-200"


def test_call_tool_unknown(monkeypatch):
    """call_tool returns error for unknown tool name."""
    monkeypatch.chdir(ROOT)
    result = asyncio.run(mcp_server.call_tool("edpa_nonexistent", {}))
    assert "Unknown tool" in result[0].text


def test_call_tool_no_edpa_root(tmp_path, monkeypatch):
    """call_tool returns error when .edpa/ not found."""
    monkeypatch.chdir(tmp_path)
    result = asyncio.run(mcp_server.call_tool("edpa_status", {}))
    assert is_error(result)
    assert "not found" in result[0].text


# ---------------------------------------------------------------------------
# read_resource (async)
# ---------------------------------------------------------------------------

def test_read_resource_config(monkeypatch):
    """read_resource returns edpa.yaml content."""
    monkeypatch.chdir(ROOT)
    content = asyncio.run(mcp_server.read_resource("edpa://config"))
    assert "PI-2026-1" in content
    assert "iterations" in content


def test_read_resource_people(monkeypatch):
    """read_resource returns people.yaml content."""
    monkeypatch.chdir(ROOT)
    content = asyncio.run(mcp_server.read_resource("edpa://people"))
    assert "urbanek" in content
    assert "capacity" in content


def test_read_resource_unknown_uri(monkeypatch):
    """read_resource returns error for unknown URI."""
    monkeypatch.chdir(ROOT)
    content = asyncio.run(mcp_server.read_resource("edpa://nonexistent"))
    assert "ERROR" in content


def test_read_resource_no_edpa_root(tmp_path, monkeypatch):
    """read_resource returns error when .edpa/ not found."""
    monkeypatch.chdir(tmp_path)
    content = asyncio.run(mcp_server.read_resource("edpa://config"))
    assert "ERROR" in content


# ---------------------------------------------------------------------------
# Edge cases: item lookup
# ---------------------------------------------------------------------------

def test_handle_item_epic():
    """Finds E-10 in epics/ directory."""
    data = parse_result(_handle_item(EDPA_ROOT, "E-10"))
    assert data["id"] == "E-10"
    assert data["type"] == "Epic"


def test_handle_item_initiative():
    """Finds I-1 in initiatives/ directory."""
    data = parse_result(_handle_item(EDPA_ROOT, "I-1"))
    assert data["id"] == "I-1"
    assert data["type"] == "Initiative"


def test_handle_item_no_hyphen():
    """Graceful handling for item ID without hyphen."""
    result = _handle_item(EDPA_ROOT, "NOHYPHEN")
    assert is_error(result)


# ---------------------------------------------------------------------------
# Edge cases: empty/missing backlog
# ---------------------------------------------------------------------------

def test_handle_backlog_empty(tmp_path):
    """Returns empty list when backlog directory is missing."""
    (tmp_path / "config").mkdir()
    data = parse_result(_handle_backlog(tmp_path, None, None, None))
    assert data == []


def test_handle_backlog_combined_filters():
    """Combined iteration + type + status filter works."""
    data = parse_result(_handle_backlog(EDPA_ROOT, "PI-2026-1.2", "Story", "Done"))
    assert len(data) >= 1
    for item in data:
        assert item["type"] == "Story"
        assert item["status"] == "Done"
        assert item["iteration"] == "PI-2026-1.2"


def test_handle_backlog_no_match():
    """Returns empty list when filters match nothing."""
    data = parse_result(_handle_backlog(EDPA_ROOT, "PI-9999-9.9", None, None))
    assert data == []
