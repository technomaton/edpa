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
    """Returns correct project name, PI, team size, capacity, active iteration.

    Iteration dates are read from .edpa/iterations/PI-2026-1.4.yaml — if
    that file's start/end dates change (e.g. when the cadence is
    reshuffled), update the asserts below to match. The 1-week-iteration
    schedule of PI-2026-1 was set in commit 0417727 (5×1 week instead of
    the original 2×2 weeks)."""
    data = parse_result(_handle_status(EDPA_ROOT))

    assert data["project"] == "Medical Platform & Datovy e-shop"
    assert data["current_pi"] == "PI-2026-1"
    assert data["team_size"] == 9
    assert data["total_capacity_per_iteration"] == 400
    assert data["active_iteration"] == "PI-2026-1.4"
    assert data["active_iteration_start"] == "2026-04-27"
    assert data["active_iteration_end"] == "2026-05-01"
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
    """Returns all 5 iterations of the active PI.

    end_date for iteration 1 reflects the 1-week cadence (commit
    0417727 changed PI-2026-1 from 2×2 weeks to 5×1 week)."""
    data = parse_result(_handle_iterations(EDPA_ROOT, None))
    iters = data["iterations"]
    assert len(iters) == 5
    ids = [i["id"] for i in iters]
    assert "PI-2026-1.1" in ids
    assert "PI-2026-1.5" in ids
    # ISO date fields replace the legacy "dates" string.
    assert iters[0]["start_date"] == "2026-04-06"
    assert iters[0]["end_date"] == "2026-04-10"


def test_handle_iterations_filter_active():
    """Returns only active iteration(s)."""
    data = parse_result(_handle_iterations(EDPA_ROOT, "active"))
    iters = data["iterations"]
    assert len(iters) >= 1
    assert all(i["status"] == "active" for i in iters)
    assert iters[0]["id"] == "PI-2026-1.4"


def test_handle_iterations_filter_closed():
    """Returns only closed iterations."""
    data = parse_result(_handle_iterations(EDPA_ROOT, "closed"))
    iters = data["iterations"]
    assert len(iters) == 3
    assert all(i["status"] == "closed" for i in iters)


def test_handle_iterations_has_results():
    """Checks has_results flag accuracy — reports dir is empty so all should be False."""
    data = parse_result(_handle_iterations(EDPA_ROOT, None))
    for it in data["iterations"]:
        assert "has_results" in it
        assert isinstance(it["has_results"], bool)


# ---------------------------------------------------------------------------
# edpa_people
# ---------------------------------------------------------------------------

def test_handle_people_all():
    """Returns all 9 people with the documented field set."""
    data = parse_result(_handle_people(EDPA_ROOT, None))
    assert len(data) == 9

    # Verify known entries
    urbanek = next(p for p in data if p["id"] == "urbanek")
    assert urbanek["role"] == "Arch"
    assert urbanek["team"] == "CVUT"
    assert urbanek["fte"] == 0.5
    assert urbanek["capacity"] == 40
    # github is part of the surface — None when missing, login string when set.
    assert "github" in urbanek


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
    """Returns items from all type directories including Defect/Task/Event/Risk."""
    data = parse_result(_handle_backlog(EDPA_ROOT, None, None, None))
    # 27 stories + 6 features + 3 epics + 1 initiative + defects/events/risks
    assert len(data) >= 37

    types_found = set(i["type"] for i in data)
    assert "Story" in types_found
    assert "Feature" in types_found
    assert "Epic" in types_found
    assert "Initiative" in types_found
    assert "Defect" in types_found


def test_handle_backlog_filter_iteration():
    """Filters by iteration ID."""
    data = parse_result(_handle_backlog(EDPA_ROOT, "PI-2026-1.1", None, None))
    assert len(data) >= 5  # at least 5 stories in PI-2026-1.1
    assert all(i["iteration"] == "PI-2026-1.1" for i in data)


def test_handle_backlog_filter_type():
    """Filters by type (Story, Feature, etc.)."""
    stories = parse_result(_handle_backlog(EDPA_ROOT, None, "Story", None))
    assert len(stories) >= 27  # S-227 added in E2
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
    """Returns the documented EDPA V2 tool surface (10 read + 13 write).

    edpa_sync_people was removed in V2.0 along with sync_collaborators.py.
    edpa_pi_create was added in 2.2.0; edpa_pi_board (PI planning HTML),
    edpa_item_link_dep (dependencies), edpa_item_roam (ROAM), and the PI
    objectives tools (set / remove / confidence) added later.
    edpa_forecast_pi added in F1; edpa_pi_metrics added in E2.
    """
    tools = asyncio.run(mcp_server.list_tools())
    assert len(tools) == 23

    names = {t.name for t in tools}
    expected_read = {"edpa_status", "edpa_iterations", "edpa_people",
                     "edpa_backlog", "edpa_item", "edpa_validate",
                     "edpa_flow_metrics", "edpa_pi_board", "edpa_forecast_pi",
                     "edpa_pi_metrics"}
    expected_write = {"edpa_item_create", "edpa_item_update",
                      "edpa_item_transition", "edpa_item_link_parent",
                      "edpa_item_link_dep", "edpa_item_roam",
                      "edpa_objective_set", "edpa_objective_remove",
                      "edpa_confidence_vote",
                      "edpa_iteration_create", "edpa_iteration_close",
                      "edpa_pi_create", "edpa_people_upsert"}
    assert names == expected_read | expected_write

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
    iters = data["iterations"]
    assert len(iters) >= 1
    assert iters[0]["id"] == "PI-2026-1.4"


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
    # PI/iteration data has moved to .edpa/iterations/*.yaml, so check for
    # surviving edpa.yaml landmarks instead.
    assert "iterations_dir" in content
    assert "evidence" in content


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


def test_read_resource_invalid_iteration_id_rejected(monkeypatch):
    """read_resource rejects path-traversal and invalid iteration ids."""
    monkeypatch.chdir(ROOT)
    for bad in ("../../foo", "../etc/passwd", "foo bar", "'; drop", ""):
        content = asyncio.run(mcp_server.read_resource(f"edpa://results/{bad}"))
        assert "ERROR" in content, f"expected ERROR for iteration id {bad!r}, got: {content[:80]}"


def test_sibling_path_does_not_leak_sys_path():
    """_sibling_path() must clean up sys.path after the with-block."""
    before = list(sys.path)
    with mcp_server._sibling_path():
        pass
    assert sys.path == before, "sys.path leaked after _sibling_path() exited"


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


# ---------------------------------------------------------------------------
# Production-hardening checks (added in v1.3-beta)
# ---------------------------------------------------------------------------


class TestItemIdValidation:
    """`_safe_item_id` must accept only `<UPPER>-<digits>` and reject everything
    else. Without this guard the call_tool dispatch could feed arbitrary
    strings to the file lookup and rely on prefix_map to filter — which is
    brittle and easy to regress."""

    def test_accepts_canonical_ids(self):
        for good in ("S-1", "F-12", "E-100", "I-9", "T-99999", "D-1"):
            assert mcp_server._safe_item_id(good) == good

    def test_rejects_path_traversal(self):
        for bad in ("../etc/passwd", "S/../E-1", "..", "/etc/passwd"):
            assert mcp_server._safe_item_id(bad) is None

    def test_rejects_lowercase_or_empty_prefix(self):
        for bad in ("s-1", "-1", "S1", "S-", "-S-1", " S-1", "S-1 "):
            assert mcp_server._safe_item_id(bad) is None

    def test_rejects_non_digits_after_dash(self):
        for bad in ("S-abc", "S-1a", "S-1.0", "S-1_2"):
            assert mcp_server._safe_item_id(bad) is None

    def test_rejects_non_string(self):
        for bad in (None, 123, [], {}):
            assert mcp_server._safe_item_id(bad) is None

    def test_call_tool_rejects_unsafe_id(self):
        result = asyncio.run(mcp_server.call_tool(
            "edpa_item", {"item_id": "../etc/passwd"}))
        assert is_error(result)
        assert "invalid item_id" in result[0].text


class TestCallToolErrorHandling:
    """call_tool must return a TextContent error rather than raising — a raised
    exception would close the stdio session and look like a server crash to
    the MCP client."""

    def test_handler_exception_returns_text_error(self, monkeypatch):
        def boom(_root):
            raise RuntimeError("synthetic failure")
        monkeypatch.setattr(mcp_server, "_handle_status", boom)
        result = asyncio.run(mcp_server.call_tool("edpa_status", {}))
        assert is_error(result)
        assert "internal error" in result[0].text

    def test_unknown_tool_returns_text_error(self):
        result = asyncio.run(mcp_server.call_tool("not_a_real_tool", {}))
        assert is_error(result) or "Unknown tool" in result[0].text

    def test_missing_edpa_root_returns_text_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDPA_ROOT", str(tmp_path))
        # tmp_path has no .edpa marker, find_edpa_root returns None for non-.edpa
        # path. Make it walk up from a clean cwd.
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EDPA_ROOT", raising=False)
        result = asyncio.run(mcp_server.call_tool("edpa_status", {}))
        assert is_error(result)
        assert ".edpa/" in result[0].text


class TestServerIdentity:
    """Server identity should advertise the plugin version so MCP clients can
    surface it in logs / debug output."""

    def test_version_resolved_from_plugin_manifest(self):
        # SERVER_VERSION is read at import time. If plugin.json was readable,
        # it must match exactly. If not, the literal "unknown" is acceptable
        # but unexpected in this checkout.
        assert mcp_server.SERVER_VERSION
        assert mcp_server.SERVER_VERSION != ""
        manifest = ROOT / "plugin" / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            expected = json.loads(manifest.read_text())["version"]
            assert mcp_server.SERVER_VERSION == expected, (
                f"SERVER_VERSION={mcp_server.SERVER_VERSION!r} but "
                f"plugin.json has {expected!r}")

    def test_server_carries_version(self):
        # mcp.server.Server stores version when constructed with it.
        v = getattr(mcp_server.server, "version", None)
        assert v == mcp_server.SERVER_VERSION


class TestLoggingSetup:
    """Logger writes to stderr (stdout is reserved for JSON-RPC)."""

    def test_logger_has_stderr_handler(self):
        log = mcp_server.logger
        stderr_handlers = [
            h for h in log.handlers
            if isinstance(h, __import__("logging").StreamHandler)
            and getattr(h, "stream", None) is sys.stderr
        ]
        assert stderr_handlers, "logger must have a stderr StreamHandler"


class TestLoadYAMLCache:
    """`load_yaml` caches parsed content keyed by (path, st_mtime_ns).
    These tests pin the cache contract: repeated reads against an
    unchanged file hit the cache; touching the file invalidates;
    overflowing the cap evicts the oldest entry."""

    def setup_method(self):
        mcp_server._load_yaml_cache_clear()

    def teardown_method(self):
        mcp_server._load_yaml_cache_clear()

    def test_repeat_read_returns_same_object(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("a: 1\n")
        first = mcp_server.load_yaml(f)
        second = mcp_server.load_yaml(f)
        # Same dict instance — proves we returned the cached object,
        # not a freshly-parsed copy.
        assert first is second

    def test_mtime_change_invalidates(self, tmp_path):
        import os, time
        f = tmp_path / "a.yaml"
        f.write_text("a: 1\n")
        first = mcp_server.load_yaml(f)
        # Force a different mtime even on filesystems with coarse
        # timestamp resolution.
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        # Also rewrite content so the change is observable.
        f.write_text("a: 2\n")
        second = mcp_server.load_yaml(f)
        assert first is not second
        assert second["a"] == 2

    def test_disappeared_file_returns_none_and_drops_cache(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("a: 1\n")
        mcp_server.load_yaml(f)  # warm the cache
        assert f in mcp_server._LOAD_YAML_CACHE
        f.unlink()
        assert mcp_server.load_yaml(f) is None

    def test_cache_is_bounded(self, tmp_path):
        cap = mcp_server._LOAD_YAML_CACHE_MAX
        # Create cap + 5 distinct files, load each once.
        files = []
        for i in range(cap + 5):
            f = tmp_path / f"item-{i}.yaml"
            f.write_text(f"i: {i}\n")
            mcp_server.load_yaml(f)
            files.append(f)
        # Cache holds at most `cap` entries.
        assert len(mcp_server._LOAD_YAML_CACHE) <= cap
        # The five oldest were evicted.
        for f in files[:5]:
            assert f not in mcp_server._LOAD_YAML_CACHE
        # The most-recent five are still there.
        for f in files[-5:]:
            assert f in mcp_server._LOAD_YAML_CACHE

    def test_lru_recency_protects_hot_entries(self, tmp_path):
        """A file that keeps getting read must NOT be evicted in favor of
        cap-many fresh files. Strict-LRU: re-reading bumps recency."""
        cap = mcp_server._LOAD_YAML_CACHE_MAX
        hot = tmp_path / "hot.yaml"
        hot.write_text("hot: 1\n")
        mcp_server.load_yaml(hot)
        # Now load `cap` other files, but re-touch `hot` between each
        # so it remains the most recent.
        for i in range(cap):
            f = tmp_path / f"cold-{i}.yaml"
            f.write_text(f"i: {i}\n")
            mcp_server.load_yaml(f)
            mcp_server.load_yaml(hot)  # recency bump
        # `hot` survives.
        assert hot in mcp_server._LOAD_YAML_CACHE
        # The earliest cold entry was evicted.
        assert (tmp_path / "cold-0.yaml") not in mcp_server._LOAD_YAML_CACHE

    def test_handlers_benefit_from_cache(self, tmp_path):
        """End-to-end: calling _handle_status twice in a row, with no
        filesystem change, must do the second pass without parsing."""
        # Build a minimal .edpa/ tree on the new schema (pis[] gone, PI/iter
        # YAMLs in iterations/).
        (tmp_path / "config").mkdir()
        (tmp_path / "iterations").mkdir()
        (tmp_path / "config" / "edpa.yaml").write_text(
            "project:\n  name: 'CacheTest'\n"
        )
        (tmp_path / "iterations" / "PI-2026-1.yaml").write_text(
            "pi:\n  id: PI-2026-1\n  status: active\n"
            "  iteration_weeks: 1\n  pi_iterations: 1\n"
        )
        (tmp_path / "iterations" / "PI-2026-1.1.yaml").write_text(
            "iteration:\n  id: PI-2026-1.1\n  pi: PI-2026-1\n"
            "  start_date: 2026-01-05\n  end_date: 2026-01-09\n"
            "  status: active\n"
        )
        (tmp_path / "config" / "people.yaml").write_text(
            "people:\n  - id: a\n    name: A\n    role: Dev\n"
            "    capacity_per_iteration: 80\n"
        )
        # First call: cache empty.
        mcp_server._load_yaml_cache_clear()
        mcp_server._handle_status(tmp_path)
        first_size = len(mcp_server._LOAD_YAML_CACHE)
        assert first_size > 0
        # Second call: cache should still hold the same entries with the
        # same mtime. Size cannot have grown.
        mcp_server._handle_status(tmp_path)
        assert len(mcp_server._LOAD_YAML_CACHE) == first_size
