"""End-to-end MCP server integration tests.

Spawns plugin/edpa/scripts/mcp_server.py as a subprocess and drives it
over the real JSON-RPC stdio transport. Catches regressions where the
mcp library's Server() constructor signature changes upstream, where the
plugin path resolution drifts, or where the server crashes during
initialize handshake.

Companion to tests/test_mcp_server.py which calls handlers directly.
This module exercises the wire protocol Claude Code / Cursor / etc.
actually use.

Run: python -m pytest tests/test_mcp_integration.py -v
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

# Skip the whole module on Windows — stdio handshake details differ enough
# that the test is more trouble than it's worth there. (CI is *nix anyway.)
if sys.platform == "win32":
    pytest.skip("MCP integration tests are POSIX-only", allow_module_level=True)

# Skip if mcp not installed (defensive — CI installs requirements-dev.txt
# which includes mcp via -r requirements.txt).
mcp = pytest.importorskip("mcp", reason="mcp package not installed")

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "plugin" / "edpa" / "scripts" / "mcp_server.py"


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

class MCPClient:
    """Minimal JSON-RPC stdio client. Spawns the server, lets the test
    send/recv individual messages, then tears it down on exit."""

    def __init__(self, edpa_root: Path | None = None):
        env = os.environ.copy()
        if edpa_root is not None:
            env["EDPA_ROOT"] = str(edpa_root)
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._next_id = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=1)

    def send(self, method: str, params: dict | None = None,
             notification: bool = False):
        msg = {"jsonrpc": "2.0", "method": method,
               "params": params if params is not None else {}}
        if not notification:
            msg["id"] = self._next_id
            self._next_id += 1
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        return msg.get("id")

    def recv(self, timeout: float = 5.0) -> dict | None:
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            return None
        line = self.proc.stdout.readline()
        if not line.strip():
            return None
        return json.loads(line)

    def initialize(self) -> dict:
        self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "edpa-pytest", "version": "0"},
        })
        result = self.recv()
        assert result and "result" in result, f"initialize failed: {result}"
        # required by the protocol
        self.send("notifications/initialized", notification=True)
        return result["result"]

    def stderr_text(self) -> str:
        # Closes stdout/stderr; only call after closing stdin.
        try:
            return self.proc.stderr.read() or ""
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def edpa_workspace(tmp_path: Path) -> Path:
    """Build a minimal but valid .edpa/ tree the server can introspect."""
    edpa = tmp_path / ".edpa"
    for sub in (
        "config", "iterations", "reports", "snapshots", "data",
        "backlog/initiatives", "backlog/epics", "backlog/features",
        "backlog/stories",
    ):
        (edpa / sub).mkdir(parents=True, exist_ok=True)

    # Config — keep it tiny but real-shaped (no pis[]; PI/iter YAMLs below).
    (edpa / "config" / "edpa.yaml").write_text(
        "project:\n"
        "  name: 'MCP Integration Test Project'\n"
        "governance:\n"
        "  methodology: 'EDPA test'\n"
        "  calculation_mode: 'gates'\n"
    )
    (edpa / "iterations" / "PI-2026-1.yaml").write_text(
        "pi:\n"
        "  id: PI-2026-1\n"
        "  status: active\n"
        "  iteration_weeks: 2\n"
        "  pi_iterations: 1\n"
    )
    (edpa / "iterations" / "PI-2026-1.1.yaml").write_text(
        "iteration:\n"
        "  id: PI-2026-1.1\n"
        "  pi: PI-2026-1\n"
        "  start_date: 2026-01-05\n"
        "  end_date: 2026-01-16\n"
        "  weeks: 2\n"
        "  status: active\n"
    )
    (edpa / "config" / "people.yaml").write_text(
        "people:\n"
        "  - id: alice\n"
        "    name: 'Alice'\n"
        "    role: Dev\n"
        "    team: 'TestTeam'\n"
        "    fte: 1.0\n"
        "    capacity_per_iteration: 80\n"
    )
    (edpa / "config" / "heuristics.yaml").write_text(
        "base_weights:\n"
        "  owner: 1.0\n"
        "  reviewer: 0.30\n"
    )
    (edpa / "backlog" / "stories" / "S-1.yaml").write_text(
        "id: S-1\n"
        "type: Story\n"
        "title: 'Integration test story'\n"
        "status: Done\n"
        "js: 3\n"
        "iteration: PI-2026-1.1\n"
    )
    return edpa


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProtocolHandshake:
    """The bare-minimum lifecycle every MCP client performs."""

    def test_initialize_returns_server_info_with_version(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            info = client.initialize()
            server_info = info.get("serverInfo") or {}
            assert server_info.get("name") == "edpa", server_info
            # Version must be present and non-empty (read from plugin.json
            # at startup; "unknown" is acceptable in pathological cases
            # but not in this checkout).
            ver = server_info.get("version")
            assert ver, f"serverInfo.version missing: {server_info}"
            assert ver != "unknown", (
                f"serverInfo.version is 'unknown' — plugin.json not "
                f"resolvable from {SERVER}?"
            )

    def test_protocol_version_advertised(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            info = client.initialize()
            assert info.get("protocolVersion"), info


class TestToolsAdvertised:
    """tools/list must return the documented EDPA tool surface."""

    def test_documented_tools_returned(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/list")
            r = client.recv()
            assert r and "result" in r
            tools = r["result"]["tools"]
            names = {t["name"] for t in tools}
            assert names == {
                "edpa_status", "edpa_iterations", "edpa_people",
                "edpa_backlog", "edpa_item", "edpa_validate",
            }, f"Tool set drift: {names}"

    def test_edpa_item_requires_item_id(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/list")
            r = client.recv()
            tools = {t["name"]: t for t in r["result"]["tools"]}
            schema = tools["edpa_item"]["inputSchema"]
            assert schema["required"] == ["item_id"]


class TestToolDispatch:
    """tools/call round-trips return TextContent without crashing."""

    def test_edpa_status_returns_json_textcontent(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/call",
                        {"name": "edpa_status", "arguments": {}})
            r = client.recv()
            assert r and "result" in r, r
            content = r["result"]["content"]
            assert len(content) == 1 and content[0]["type"] == "text"
            data = json.loads(content[0]["text"])
            # The fixture set a known project name — verify the reader
            # actually finds it (regression guard for the F3 fix).
            assert data["project"] == "MCP Integration Test Project"
            assert data["current_pi"] == "PI-2026-1"
            assert data["iterations_total"] == 1

    def test_edpa_item_valid_id(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/call",
                        {"name": "edpa_item", "arguments": {"item_id": "S-1"}})
            r = client.recv()
            content = r["result"]["content"]
            data = json.loads(content[0]["text"])
            assert data["id"] == "S-1"
            assert data["status"] == "Done"

    @pytest.mark.parametrize("bad_id", [
        "../etc/passwd",
        "../../etc/shadow",
        "S/../E-1",
        "s-1",       # lowercase prefix
        "S-",        # no digits
        "S1",        # missing dash
        "S-abc",     # non-digit suffix
    ])
    def test_edpa_item_rejects_unsafe_ids(self, edpa_workspace, bad_id):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/call",
                        {"name": "edpa_item",
                         "arguments": {"item_id": bad_id}})
            r = client.recv()
            text = r["result"]["content"][0]["text"]
            assert "invalid item_id" in text, (
                f"Unsafe id {bad_id!r} was not rejected: {text}")


class TestResources:
    """resources/list should advertise the three documented URIs."""

    def test_resources_list_returns_config_and_people(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("resources/list")
            r = client.recv()
            assert r and "result" in r, r
            resources = r["result"]["resources"]
            uris = {x["uri"] for x in resources}
            assert "edpa://config" in uris
            assert "edpa://people" in uris
            # No iterations/results expected (none closed)
            assert not any(u.startswith("edpa://results/") for u in uris)


class TestObservability:
    """Stderr discipline: every call_tool must produce a log line."""

    def test_call_tool_writes_info_log(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/call",
                        {"name": "edpa_status", "arguments": {}})
            client.recv()
            # Close the session to flush stderr.
            client.close()
            logs = client.stderr_text()
            assert "INFO edpa.mcp call_tool name=edpa_status" in logs, logs

    def test_rejected_item_id_writes_warning_log(self, edpa_workspace):
        with MCPClient(edpa_workspace) as client:
            client.initialize()
            client.send("tools/call",
                        {"name": "edpa_item",
                         "arguments": {"item_id": "../etc/passwd"}})
            client.recv()
            client.close()
            logs = client.stderr_text()
            assert "WARNING edpa.mcp edpa_item: rejected" in logs, logs
