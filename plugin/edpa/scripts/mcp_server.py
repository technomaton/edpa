#!/usr/bin/env python3
"""
EDPA MCP Server — exposes .edpa/ project data to AI assistants.

Read-only server that provides structured access to EDPA configuration,
iterations, people, and backlog items. Works with any MCP client
(Claude Code, Cursor, Codex CLI, etc.).

Usage:
    python3 .claude/edpa/scripts/mcp_server.py

Environment:
    EDPA_ROOT       Override .edpa/ lookup (default: walk up from cwd)
    EDPA_LOG_LEVEL  DEBUG | INFO (default) | WARNING | ERROR
    EDPA_LOG_FILE   Optional path; falls back to stderr only
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import statistics
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml",
          file=sys.stderr)
    sys.exit(1)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Resource, TextContent, Tool
except ImportError:
    print("ERROR: 'mcp' package required. Install with: pip install mcp",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging — stderr only (stdout is reserved for JSON-RPC)
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    level_name = os.environ.get("EDPA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log = logging.getLogger("edpa.mcp")
    log.setLevel(level)
    if log.handlers:
        return log
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s edpa.mcp %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    log.addHandler(stderr_handler)
    log_file = os.environ.get("EDPA_LOG_FILE")
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            log.addHandler(file_handler)
        except OSError as exc:
            log.warning("Could not open EDPA_LOG_FILE=%s (%s); stderr only",
                        log_file, exc)
    return log


logger = _setup_logging()

# ---------------------------------------------------------------------------
# Server identity (version comes from plugin.json — single source of truth)
# ---------------------------------------------------------------------------

def _read_plugin_version() -> str:
    """Read version from plugin.json next to the script's plugin root.

    Walks up from this file: scripts/mcp_server.py -> edpa/ -> plugin root,
    where .claude-plugin/plugin.json lives. Falls back to "unknown" if the
    manifest is missing (e.g. running from a checkout without symlinks).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")
            except (OSError, ValueError):
                return "unknown"
    return "unknown"


SERVER_VERSION = _read_plugin_version()

# ---------------------------------------------------------------------------
# Input validation — guards against path traversal in tool parameters
# ---------------------------------------------------------------------------

# Item IDs are <type-prefix>-<digits>: S-200, F-12, I-1, D-3, T-99,
# plus 2-letter EV-3 (Event) and 1-letter R-2 (Risk) added in V2.
ITEM_ID_RE = re.compile(r"^[A-Z]{1,3}-\d{1,9}$")
ITERATION_ID_RE = re.compile(r"^PI-\d{4}-\d{1,2}(?:\.\d{1,2})?$")
PERSON_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _safe_item_id(item_id: str) -> str | None:
    """Return item_id if it matches the allowed shape, else None."""
    if not isinstance(item_id, str):
        return None
    return item_id if ITEM_ID_RE.match(item_id) else None


def _safe_iteration_id(iter_id: str) -> str | None:
    if not isinstance(iter_id, str):
        return None
    return iter_id if ITERATION_ID_RE.match(iter_id) else None


def _safe_person_id(person_id: str) -> str | None:
    if not isinstance(person_id, str):
        return None
    return person_id if PERSON_ID_RE.match(person_id) else None


@contextlib.contextmanager
def _sibling_path():
    """Temporarily add this file's directory to sys.path for sibling imports.

    Uses try/finally to guarantee removal even if the import raises, preventing
    the path from leaking into long-running MCP sessions.
    """
    sibling = str(Path(__file__).resolve().parent)
    sys.path.insert(0, sibling)
    try:
        yield
    finally:
        try:
            sys.path.remove(sibling)
        except ValueError:
            pass


# Type metadata — single source of truth for write tools (mirrors
# backlog.py constants; kept here to avoid an import cycle until
# Krok 2 refactors backlog.py to import from id_counter).
TYPE_DIRS = {
    "Initiative": "initiatives",
    "Epic":       "epics",
    "Feature":    "features",
    "Story":      "stories",
    "Defect":     "defects",
    "Event":      "events",
    "Risk":       "risks",
}
PARENT_RULES = {
    "Initiative": None,
    "Epic":       "Initiative",
    "Feature":    "Epic",
    "Story":      "Feature",
    "Defect":     None,
    "Event":      None,
    "Risk":       None,
}
PORTFOLIO_STATUSES = ("Funnel", "Reviewing", "Analyzing", "Ready", "Implementing", "Done")
DELIVERY_STATUSES = (
    "Funnel", "Analyzing", "Backlog", "Implementing",
    "Validating", "Deploying", "Releasing", "Done",
)
PORTFOLIO_TYPES = {"Initiative", "Epic"}
DELIVERY_TYPES = {"Feature", "Story", "Defect"}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def find_edpa_root() -> Path | None:
    """Find .edpa/ directory. Checks EDPA_ROOT env var first, then walks up from CWD."""
    env_root = os.environ.get("EDPA_ROOT")
    if env_root:
        p = Path(env_root)
        if p.is_dir():
            return p
    p = Path.cwd()
    while p != p.parent:
        if (p / ".edpa").is_dir():
            return p / ".edpa"
        p = p.parent
    return None


# Bounded LRU cache for parsed YAML, keyed by (path, st_mtime_ns).
# Repeated `tools/call` against an unchanged backlog is the common case
# (Claude Code asks "what's in PI-X?" then immediately "show me S-1
# from there?"); without a cache each invocation re-parses every YAML
# file from scratch. Bound at 64 entries — large enough for a 3-level
# hierarchy plus per-iteration files, small enough that a one-shot
# scan of a 1000-item backlog can't balloon resident memory.
_LOAD_YAML_CACHE: "OrderedDict[Path, tuple[int, dict]]" = OrderedDict()
_LOAD_YAML_CACHE_MAX = 64


def _load_yaml_cache_clear() -> None:
    """Test helper — drop all cached entries."""
    _LOAD_YAML_CACHE.clear()


def load_yaml(path: Path) -> dict | None:
    """Load a YAML file (or Markdown-with-frontmatter), return None on failure.

    Caches parsed contents keyed by (path, st_mtime_ns). Backlog items
    (`.md` files under .edpa/backlog/) are parsed via
    ``_md_frontmatter.load_md`` — frontmatter fields plus a ``body`` key.
    Config / iteration files (`.yaml`) are parsed via PyYAML.
    Cache is bounded; the least-recently-used entry is evicted when
    the cap is reached.
    """
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("load_yaml stat(%s) failed: %s", path, exc)
        return None

    cached = _LOAD_YAML_CACHE.get(path)
    if cached is not None and cached[0] == st.st_mtime_ns:
        # Move to end so it counts as recently-used for eviction.
        _LOAD_YAML_CACHE.move_to_end(path)
        return cached[1]

    try:
        if path.suffix == ".md":
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            try:
                from _md_frontmatter import load_md as _load_md  # noqa: E402
            finally:
                _sys.path.pop(0)
            data = _load_md(path) or {}
        else:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("load_yaml(%s) failed: %s", path, exc)
        # Drop a stale cached version; next caller should re-attempt.
        _LOAD_YAML_CACHE.pop(path, None)
        return None

    # Insert / refresh; evict oldest when over the cap.
    _LOAD_YAML_CACHE[path] = (st.st_mtime_ns, data)
    _LOAD_YAML_CACHE.move_to_end(path)
    while len(_LOAD_YAML_CACHE) > _LOAD_YAML_CACHE_MAX:
        _LOAD_YAML_CACHE.popitem(last=False)
    return data

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

server = Server("edpa", version=SERVER_VERSION)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="edpa_status",
            description="Get EDPA project status: current PI, active iteration, team size, total capacity.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="edpa_iterations",
            description="List all iterations with id, status, dates, and type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: closed, active, planned. Omit for all.",
                        "enum": ["closed", "active", "planned"],
                    }
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_people",
            description="List team members with id, name, role, FTE, capacity, and team.",
            inputSchema={
                "type": "object",
                "properties": {
                    "team": {
                        "type": "string",
                        "description": "Filter by team ID. Omit for all.",
                    }
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_backlog",
            description="List backlog items from .edpa/backlog/. Filterable by iteration, type, or status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "iteration": {
                        "type": "string",
                        "description": "Filter by iteration ID (e.g., PI-2026-1.3).",
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by item type.",
                        "enum": ["Story", "Feature", "Epic", "Initiative"],
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status (e.g., Done, In Progress, Planned).",
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item",
            description="Get detail for a single backlog item by ID (e.g., S-200, F-100).",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "Item ID (e.g., S-200, F-100, E-10).",
                    }
                },
                "required": ["item_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_validate",
            description="Validate iterations/*.yaml continuity and schema. Returns errors and warnings.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="edpa_flow_metrics",
            description=(
                "Compute flow metrics: cycle time, lead time, throughput, and "
                "average age of open items. Requires timestamp data from a prior "
                "sync pull."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "iteration": {
                        "type": "string",
                        "description": "Filter by iteration ID (e.g., PI-2026-1.3).",
                    },
                    "level": {
                        "type": "string",
                        "description": "Filter by item level.",
                        "enum": ["Story", "Feature", "Epic", "Initiative"],
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_create",
            description=(
                "Create a new backlog item. Allocates the next local ID via "
                "id_counter (no gh call), validates parent type hierarchy "
                "(Story→Feature→Epic→Initiative), and writes "
                ".edpa/backlog/{type}/{ID}.md with frontmatter + body."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(TYPE_DIRS.keys())},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "body": {"type": "string"},
                    "parent": {"type": "string"},
                    "iteration": {"type": "string"},
                    "assignee": {"type": "string"},
                    "status": {"type": "string"},
                    "js": {"type": "integer", "minimum": 0},
                    "bv": {"type": "integer", "minimum": 0},
                    "tc": {"type": "integer", "minimum": 0},
                    "rr_oe": {"type": "integer", "minimum": 0},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["type", "title"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_update",
            description=(
                "Update one or more frontmatter fields on an existing item. "
                "Atomic — all fields applied or none. Use edpa_item_transition "
                "for status changes (it also stamps closed_at on Done)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "fields": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "iteration": {"type": "string"},
                            "iteration_half": {"type": "integer", "minimum": 1, "maximum": 2},
                            "assignee": {"type": "string"},
                            "js": {"type": "integer", "minimum": 0},
                            "bv": {"type": "integer", "minimum": 0},
                            "tc": {"type": "integer", "minimum": 0},
                            "rr_oe": {"type": "integer", "minimum": 0},
                        },
                        "additionalProperties": False,
                        "minProperties": 1,
                    },
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["item_id", "fields"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_transition",
            description=(
                "Change an item's status. Validates against the SAFe workflow for "
                "its type (portfolio vs delivery). Auto-stamps closed_at when "
                "transitioning to Done (first time only)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "status": {"type": "string"},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["item_id", "status"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_link_parent",
            description=(
                "Set the parent reference on an item. Validates parent exists "
                "and matches the expected type per the hierarchy "
                "(Story→Feature, Feature→Epic, Epic→Initiative)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "parent_id": {"type": "string"},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["item_id", "parent_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_iteration_create",
            description=(
                "Create a new iteration YAML at .edpa/iterations/{id}.yaml. "
                "The PI parent ID is derived from the iteration ID (e.g. "
                "PI-2026-1.3 → PI-2026-1). Status defaults to 'planned'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "start_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "end_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "type": {"type": "string", "enum": ["Iteration", "IP"]},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["id", "start_date", "end_date"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_iteration_close",
            description=(
                "Mark an iteration as closed in its YAML file. Does NOT run "
                "the engine or generate reports — those are orchestrated by "
                "the edpa:close-iteration skill."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_link_dep",
            description=(
                "Add or remove a dependency on a backlog item. depends_on=[B] "
                "on item A means 'A depends on B' (B must land first) — the "
                "program board's dependency arrows. Validates both items exist, "
                "refuses a self-loop, and (on add) refuses an edge that would "
                "create a cycle. action: 'add' (default) | 'remove'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "depends_on_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["item_id", "depends_on_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_item_roam",
            description=(
                "Set the ROAM classification (resolved / owned / accepted / "
                "mitigated) on a Risk item. The PI planning ROAM board groups "
                "risks into these four columns. Applies only to Risk items."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "roam_status": {
                        "type": "string",
                        "enum": ["resolved", "owned", "accepted", "mitigated"],
                    },
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["item_id", "roam_status"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_objective_set",
            description=(
                "Add or update a PI objective for a team (upsert by title) in "
                ".edpa/pi-objectives/<pi>.yaml. kind: 'committed' | 'stretch'. "
                "bv 1-10 (default 5); status planned/in_progress/done (default "
                "planned). Creates the file/team as needed. Rendered on the PI "
                "planning Objectives board."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pi": {"type": "string"},
                    "team": {"type": "string"},
                    "kind": {"type": "string", "enum": ["committed", "stretch"]},
                    "title": {"type": "string", "minLength": 1},
                    "bv": {"type": "integer", "minimum": 1, "maximum": 10},
                    "status": {"type": "string", "enum": ["planned", "in_progress", "done"]},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["pi", "team", "kind", "title"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_objective_remove",
            description=(
                "Remove a PI objective by (team, kind, title) from "
                ".edpa/pi-objectives/<pi>.yaml."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pi": {"type": "string"},
                    "team": {"type": "string"},
                    "kind": {"type": "string", "enum": ["committed", "stretch"]},
                    "title": {"type": "string", "minLength": 1},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["pi", "team", "kind", "title"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_confidence_vote",
            description=(
                "Set a team's PI confidence vote (1-5) in "
                ".edpa/pi-objectives/<pi>.yaml. Drives the Objectives board's "
                "predictability summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pi": {"type": "string"},
                    "team": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 1, "maximum": 5},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["pi", "team", "confidence"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_pi_create",
            description=(
                "Create the PI-level metadata file at "
                ".edpa/iterations/{id}.yaml (top-level `pi:` block). The id "
                "must be PI-level (PI-YYYY-N) — NOT an iteration id with a "
                ".N suffix. Does NOT create child iterations (use "
                "edpa_iteration_create); status defaults to 'planning'. "
                "Delegates to create_pi.py — the single source of behavior "
                "also used by the /edpa:create-pi command."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "start_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "end_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "iteration_weeks": {"type": "integer", "minimum": 1},
                    "pi_iterations": {"type": "integer", "minimum": 1},
                    "status": {"type": "string", "enum": ["planning", "active", "closed"]},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_pi_close",
            description=(
                "Close a Program Increment: verify every child iteration is "
                "closed, flip the PI-level `pi.status` to 'closed' in "
                ".edpa/iterations/{id}.yaml, and (re)write the PI rollup report "
                "(.edpa/reports/pi-{id}/pi_results.json + summary.md). The id "
                "must be PI-level (PI-YYYY-N) — NOT an iteration id. Pass "
                "force=true to roll up even if some iterations are still open "
                "(skips the guard). Write only; no git commit (the "
                "/edpa:close-pi command owns the commit). Delegates to "
                "pi_close.py — the single source of behavior. Re-runnable: "
                "regenerates the rollup, no-op on an already-closed status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "force": {"type": "boolean"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_pi_board",
            description=(
                "Generate the self-contained PI planning / overview HTML for a "
                "PI (program board, objectives, ROAM, portfolio, capacity) at "
                ".edpa/reports/pi-{id}/pi-{id}.html and return its path. A "
                "read-only projection of .edpa/ — safe to re-run after edits. "
                "Optional 'pi' (default: planning > active > first). Delegates to "
                "pi_planning.py — the single source also used by /edpa:pi-planning."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pi": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_people_upsert",
            description=(
                "Add a new person to .edpa/config/people.yaml or update fields "
                "on an existing one. Atomic write via tmp + rename."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "team": {"type": "string"},
                    "fte": {"type": "number", "minimum": 0, "maximum": 1},
                    "capacity": {"type": "number", "minimum": 0},
                    "github": {"type": "string"},
                    "availability": {"type": "string"},
                    "idempotency_key": {"type": "string", "maxLength": 128},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_forecast_pi",
            description=(
                "Monte-Carlo PI completion forecast. Fits a velocity distribution "
                "from the last N closed iterations and simulates remaining-iteration "
                "delivery 1000×, returning p20/p50/p80 delivery bands, completion "
                "probability, and a scope recommendation. Read-only — does not "
                "modify any files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pi": {"type": "string", "description": "PI ID, e.g. PI-2026-2"},
                    "window": {"type": "integer", "minimum": 2, "maximum": 20,
                               "description": "Velocity history window (default 3)"},
                    "simulations": {"type": "integer", "minimum": 100, "maximum": 10000,
                                    "description": "Monte-Carlo simulations (default 1000)"},
                },
                "required": ["pi"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_pi_metrics",
            description=(
                "PI confidence & predictability trending. Accumulates per-PI metrics: "
                "planned vs delivered SP (predictability %), average team confidence "
                "votes, objective completion ratio, and average velocity per iteration. "
                "Returns a table of the last N PIs — ideal for Inspect&Adapt. "
                "Also writes .edpa/reports/pi-metrics.json and pi-metrics.md. "
                "Read-only with respect to backlog/iteration data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window": {"type": "integer", "minimum": 1, "maximum": 20,
                               "description": "Number of most-recent PIs to include (default 5)"},
                    "pi": {"type": "string",
                           "description": "Limit to a single PI ID, e.g. PI-2026-1 (optional)"},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_insights",
            description=(
                "Mid-iteration anomaly detection. Reads edpa_results.json + backlog items "
                "+ git history and surfaces: capacity_overload (derived > threshold%), "
                "job_size_creep (JS > threshold), stalled_story (in_progress, no git "
                "activity > N days), critical_path_blocker (blocked by unfinished dep). "
                "Returns JSON anomaly list + writes insights.json and insights-<iter>.md "
                "to the reports directory. Read-only with respect to backlog data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "iteration": {"type": "string",
                                  "description": "Iteration ID, e.g. PI-2026-1.3 (required)"},
                    "overload_threshold": {
                        "type": "number", "minimum": 1.0, "maximum": 2.0,
                        "description": "Capacity overload ratio, default 1.10 (110%)",
                    },
                    "js_threshold": {
                        "type": "integer", "minimum": 1, "maximum": 100,
                        "description": "JS above which job-size creep is flagged, default 8",
                    },
                    "stale_days": {
                        "type": "integer", "minimum": 1, "maximum": 90,
                        "description": "Days of git inactivity to flag as stalled, default 5",
                    },
                },
                "required": ["iteration"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_ai_attribution",
            description=(
                "Human vs AI-agent delivery ratio for an iteration. Scans backlog items "
                "for agent_contribution signals emitted by local_evidence.py when commits "
                "carry Co-Authored-By: Claude … <…@anthropic.com> trailers. Returns a "
                "per-item and per-person breakdown plus an iteration-wide ai_delivery_ratio. "
                "Writes ai_attribution.json and ai-attribution-<iter>.md to the reports dir."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "iteration": {"type": "string",
                                  "description": "Iteration ID, e.g. PI-2026-1.3 (required)"},
                },
                "required": ["iteration"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_payroll_export",
            description=(
                "Generate a billable-hours CSV (and return the data as JSON) from engine "
                "derived hours. Reads edpa_results.json + people.yaml (hourly_rate, currency "
                "fields) + edpa.yaml (project.funding.registration → cost code). "
                "Writes payroll-<iter>.csv to .edpa/reports/iteration-<id>/. "
                "Requires /edpa:engine to have been run for the iteration first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "iteration": {"type": "string",
                                  "description": "Iteration ID, e.g. PI-2026-1.3 (required)"},
                    "currency": {"type": "string",
                                 "description": "Currency code override for rows without per-person currency (e.g. CZK, EUR, USD)"},
                    "output": {"type": "string",
                               "description": "Custom output CSV path (optional, default: reports/iteration-<id>/payroll-<id>.csv)"},
                },
                "required": ["iteration"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="edpa_reconcile",
            description=(
                "Reconcile git delivery evidence against backlog status. Walks the main "
                "branch, extracts item IDs from commit subjects (CC scope; body mentions "
                "and auto-prefixed commits do not count) and reports drift: items with "
                "merged evidence still before Done — suggested transition + closed_at "
                "from the latest evidence commit (release-tag containment or >= "
                "stale_days of quiet => Done, fresh evidence => Implementing) — plus "
                "Done items with zero evidence (phantoms, review-only). Read-only: "
                "apply suggestions via edpa_item_transition, or reconcile.py --apply."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "branch": {"type": "string",
                               "description": "Evidence branch (default: autodetect main/master)"},
                    "stale_days": {"type": "integer", "minimum": 0,
                                   "description": "Quiet days after last evidence before suggesting Done (default 3)"},
                },
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info("call_tool name=%s args=%s", name, arguments)
    edpa_root = find_edpa_root()
    if edpa_root is None:
        logger.warning("call_tool name=%s: .edpa/ not found", name)
        return [TextContent(type="text", text="ERROR: .edpa/ directory not found. Run `/edpa setup` first.")]

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        logger.warning("call_tool: unknown tool %s", name)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return handler(edpa_root, arguments)
    except Exception:
        logger.exception("call_tool name=%s raised", name)
        return [TextContent(type="text",
                            text=f"ERROR: internal error in {name}; "
                                 "see server logs for details.")]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_status(edpa_root: Path) -> list[TextContent]:
    config = load_yaml(edpa_root / "config" / "edpa.yaml") or {}
    people_cfg = load_yaml(edpa_root / "config" / "people.yaml") or {}

    with _sibling_path():
        from _pi_loader import derive_pis, find_active_pi, split_diagnostics  # noqa: E402

    pis, diags = derive_pis(edpa_root)
    _, warnings = split_diagnostics(diags)
    active_pi = find_active_pi(pis)
    iterations = active_pi.get("iterations", [])
    active = next((i for i in iterations if i.get("status") == "active"), None)
    closed_count = sum(1 for i in iterations if i.get("status") == "closed")

    people = people_cfg.get("people", [])
    total_capacity = sum(p.get("capacity_per_iteration") or p.get("capacity", 0) for p in people)

    # Project name lives in edpa.yaml (project.name). Older versions of
    # this server read it from people.yaml, which never had a project
    # section in any shipped template, so edpa_status reported
    # "project: unknown" forever. Fall back to people.yaml only for
    # legacy v0.x configs that still bundled both into one file.
    project = config.get("project") or people_cfg.get("project", {})
    iter_weeks = active_pi.get("iteration_weeks", 1)
    pi_iters = active_pi.get("pi_iterations", len(iterations))

    result = {
        "project": project.get("name", "unknown"),
        "current_pi": active_pi.get("id", "unknown"),
        "iterations_total": len(iterations),
        "iterations_closed": closed_count,
        "active_iteration": active["id"] if active else None,
        "active_iteration_start": active.get("start_date") if active else None,
        "active_iteration_end": active.get("end_date") if active else None,
        "team_size": len(people),
        "total_capacity_per_iteration": total_capacity,
        "cadence": f"{iter_weeks}-week iterations, {pi_iters * iter_weeks}-week PI ({pi_iters} iterations)",
    }
    if warnings:
        result["warnings"] = warnings
    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


def _handle_iterations(edpa_root: Path, status_filter: str | None) -> list[TextContent]:
    with _sibling_path():
        from _pi_loader import derive_pis, find_active_pi, split_diagnostics  # noqa: E402

    pis, diags = derive_pis(edpa_root)
    _, warnings = split_diagnostics(diags)
    active_pi = find_active_pi(pis)
    iterations = active_pi.get("iterations", [])

    if status_filter:
        iterations = [i for i in iterations if i.get("status") == status_filter]

    items = []
    for it in iterations:
        entry = {
            "id": it.get("id"),
            "status": it.get("status"),
            "start_date": it.get("start_date"),
            "end_date": it.get("end_date"),
            "weeks": it.get("weeks"),
        }
        if it.get("type"):
            entry["type"] = it["type"]
        results_path = edpa_root / "reports" / f"iteration-{it.get('id')}" / "edpa_results.json"
        entry["has_results"] = results_path.exists()
        items.append(entry)

    payload: dict = {"iterations": items}
    if warnings:
        payload["warnings"] = warnings
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


def _handle_validate(edpa_root: Path) -> list[TextContent]:
    """Run iteration + people validation, return structured report."""
    # Local import: keeps the optional helpers out of module-load path so the
    # MCP server can still start even if a plugin upgrade is mid-flight.
    with _sibling_path():
        from _pi_loader import derive_pis, split_diagnostics  # noqa: E402
        from _people_loader import validate_people  # noqa: E402

    pis, iter_diags = derive_pis(edpa_root)
    people_diags = validate_people(edpa_root)
    all_diags = list(iter_diags) + list(people_diags)
    errors, warnings = split_diagnostics(all_diags)
    payload = {
        "ok": not errors,
        "pi_count": len(pis),
        "iteration_count": sum(len(p.get("iterations", [])) for p in pis),
        "errors": errors,
        "warnings": warnings,
    }
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


def _handle_people(edpa_root: Path, team_filter: str | None) -> list[TextContent]:
    people_cfg = load_yaml(edpa_root / "config" / "people.yaml") or {}
    people = people_cfg.get("people", [])

    if team_filter:
        people = [p for p in people if p.get("team") == team_filter]

    result = []
    for p in people:
        entry = {
            "id": p.get("id"),
            "name": p.get("name", p.get("id")),
            "role": p.get("role"),
            "team": p.get("team"),
            "fte": p.get("fte"),
            "capacity": p.get("capacity_per_iteration") or p.get("capacity", 0),
            "github": p.get("github") or None,
        }
        result.append(entry)

    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


def _handle_backlog(edpa_root: Path, iteration: str | None, type_filter: str | None, status_filter: str | None) -> list[TextContent]:
    backlog_dir = edpa_root / "backlog"
    if not backlog_dir.exists():
        return [TextContent(type="text", text="[]")]

    type_dirs = {
        "stories": "Story",
        "features": "Feature",
        "epics": "Epic",
        "initiatives": "Initiative",
        "defects": "Defect",
        "tasks": "Task",
        "events": "Event",
        "risks": "Risk",
    }

    items = []
    for dir_name, level in type_dirs.items():
        type_dir = backlog_dir / dir_name
        if not type_dir.exists():
            continue
        if type_filter and level != type_filter:
            continue

        for md_file in sorted(type_dir.glob("*.md")):
            data = load_yaml(md_file)
            if not data or not isinstance(data, dict):
                continue

            if iteration and data.get("iteration") != iteration:
                continue
            if status_filter and (data.get("status", "").lower() != status_filter.lower()):
                continue

            entry = {
                "id": data.get("id", md_file.stem),
                "type": data.get("type", level),
                "title": data.get("title", ""),
                "status": data.get("status", ""),
                "js": data.get("js") or data.get("job_size", 0),
                "iteration": data.get("iteration", ""),
                "assignee": data.get("assignee") or data.get("owner", ""),
                "parent": data.get("parent", ""),
            }
            for ts_field in ("created_at", "closed_at", "updated_at"):
                ts_val = data.get(ts_field)
                if ts_val is not None:
                    entry[ts_field] = str(ts_val)
            items.append(entry)

    return [TextContent(type="text", text=json.dumps(items, indent=2, ensure_ascii=False))]


def _handle_item(edpa_root: Path, item_id: str) -> list[TextContent]:
    backlog_dir = edpa_root / "backlog"
    if not backlog_dir.exists():
        return [TextContent(type="text", text=f"ERROR: Backlog not found.")]

    # Determine type directory from prefix
    prefix_map = {"S": "stories", "F": "features", "E": "epics", "I": "initiatives",
                  "T": "stories", "D": "defects"}
    prefix = item_id.split("-")[0] if "-" in item_id else ""
    dir_name = prefix_map.get(prefix)

    search_dirs = [backlog_dir / dir_name] if dir_name else list(backlog_dir.iterdir())

    for d in search_dirs:
        if not d.is_dir():
            continue
        candidate = d / f"{item_id}.md"
        if candidate.exists():
            data = load_yaml(candidate)
            if data:
                return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False, default=str))]

    return [TextContent(type="text", text=f"ERROR: Item {item_id} not found in backlog.")]


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime.

    Handles ``Z`` suffix (GitHub convention), explicit ``+00:00`` offsets,
    bare ISO strings (treated as UTC), and ``datetime.date`` objects from
    YAML parsing. Returns ``None`` for anything unparseable.
    """
    if value is None:
        return None
    # YAML may parse a bare date (2026-05-01) as a datetime.date object.
    from datetime import date as _date
    if isinstance(value, _date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    s = str(value).strip()
    if not s:
        return None
    # Normalise Z → +00:00 for fromisoformat (Python < 3.11 compat)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _handle_flow_metrics(
    edpa_root: Path,
    iteration: str | None,
    level: str | None,
) -> list[TextContent]:
    """Compute cycle time, open-item age, and throughput from timestamp data."""
    backlog_dir = edpa_root / "backlog"
    if not backlog_dir.exists():
        return [TextContent(type="text", text=json.dumps(
            {"error": "No backlog directory found."}, indent=2))]

    type_dirs = {
        "stories": "Story",
        "features": "Feature",
        "epics": "Epic",
        "initiatives": "Initiative",
    }

    now = datetime.now(timezone.utc)
    cycle_times: list[float] = []
    open_ages: list[float] = []
    done_items: list[dict] = []
    open_items: list[dict] = []
    skipped = 0

    # flow_metrics intentionally covers only delivery-tracked types (Story,
    # Feature, Epic, Initiative) — Task/Event/Risk have no derived hours.
    for dir_name, item_level in type_dirs.items():
        type_dir = backlog_dir / dir_name
        if not type_dir.exists():
            continue
        if level and item_level != level:
            continue

        for md_file in sorted(type_dir.glob("*.md")):
            data = load_yaml(md_file)
            if not data or not isinstance(data, dict):
                continue
            if iteration and data.get("iteration") != iteration:
                continue

            item_id = data.get("id", md_file.stem)
            title = data.get("title", "")
            status = (data.get("status") or "").strip()
            is_done = status.lower() == "done"

            created = _parse_timestamp(data.get("created_at"))
            closed = _parse_timestamp(data.get("closed_at"))

            if is_done:
                if created and closed:
                    ct = max((closed - created).total_seconds() / 86400.0, 0.0)
                    cycle_times.append(ct)
                    done_items.append({
                        "id": item_id, "title": title, "status": status,
                        "cycle_time_days": round(ct, 2),
                    })
                else:
                    skipped += 1
                    done_items.append({
                        "id": item_id, "title": title, "status": status,
                        "cycle_time_days": None,
                    })
            else:
                if created:
                    age = max((now - created).total_seconds() / 86400.0, 0.0)
                    open_ages.append(age)
                    open_items.append({
                        "id": item_id, "title": title, "status": status,
                        "age_days": round(age, 2),
                    })
                else:
                    skipped += 1
                    open_items.append({
                        "id": item_id, "title": title, "status": status,
                        "age_days": None,
                    })

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"min": None, "max": None, "avg": None, "median": None,
                    "p90": None, "count": 0}
        s = sorted(values)
        p90_idx = int(len(s) * 0.9)
        p90_idx = min(p90_idx, len(s) - 1)
        return {
            "min": round(s[0], 2),
            "max": round(s[-1], 2),
            "avg": round(statistics.mean(s), 2),
            "median": round(statistics.median(s), 2),
            "p90": round(s[p90_idx], 2),
            "count": len(s),
        }

    payload = {
        "cycle_time": _stats(cycle_times),
        "open_items_age": _stats(open_ages),
        "throughput": {
            "total_done": len(done_items),
            "total_open": len(open_items),
            "total_items": len(done_items) + len(open_items),
        },
        "items_detail": done_items + open_items,
        "skipped_no_timestamps": skipped,
    }
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Write tool helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"ERROR: {msg}")]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_item_file(edpa_root: Path, item_id: str) -> Path | None:
    """Locate the .md file for item_id by scanning all backlog/{type}/ dirs.

    Returns None if not found. Drops the YAML load cache for the item's
    type dir so concurrent edits across MCP calls are not masked.
    """
    backlog = edpa_root / "backlog"
    for type_dir in TYPE_DIRS.values():
        candidate = backlog / type_dir / f"{item_id}.md"
        if candidate.exists():
            return candidate
    return None


def _save_md_item(file_path: Path, item: dict, body: str) -> None:
    """Wrapper over _md_frontmatter.save_md with sys.path mgmt."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _md_frontmatter import save_md  # noqa: E402
        save_md(file_path, item, body=body)
    finally:
        sys.path.pop(0)


def _load_md_item(file_path: Path) -> dict | None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _md_frontmatter import load_md  # noqa: E402
        return load_md(file_path)
    finally:
        sys.path.pop(0)


def _allocate_id(item_type: str, repo_root: Path) -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from id_counter import next_id  # noqa: E402
        return next_id(item_type, repo_root)
    finally:
        sys.path.pop(0)


def _write_yaml_atomic(path: Path, data: dict) -> None:
    """tmp + rename. yaml.safe_dump with sort_keys=False, allow_unicode=True."""
    import tempfile as _tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = _tempfile.mkstemp(
        suffix=".yaml", prefix=f".{path.stem}_", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data, f, sort_keys=False, default_flow_style=False, allow_unicode=True
            )
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _load_yaml_cache_clear()


def _allowed_statuses(item_type: str) -> tuple[str, ...] | None:
    if item_type in PORTFOLIO_TYPES:
        return PORTFOLIO_STATUSES
    if item_type in DELIVERY_TYPES:
        return DELIVERY_STATUSES
    return None


# ---------------------------------------------------------------------------
# Idempotency (V2 plan.md Layer 3)
# ---------------------------------------------------------------------------

_IDEMPOTENCY_LOG_REL = Path(".edpa/.idempotency.log")
_IDEMPOTENCY_TTL_SEC = 24 * 3600


def _idempotency_path(edpa_root: Path) -> Path:
    return edpa_root.parent / _IDEMPOTENCY_LOG_REL


def _idempotency_lookup(edpa_root: Path, tool: str, key: str) -> str | None:
    """Return the cached response text if (tool, key) was logged within TTL.

    Scans the JSONL log newest-to-oldest; first match wins. Returns None
    if the key is absent, expired, or the log doesn't exist.
    """
    if not key:
        return None
    log = _idempotency_path(edpa_root)
    if not log.exists():
        return None
    try:
        from datetime import datetime as _dt
        now = _dt.now(timezone.utc)
        # Read backwards (small log; OK to read full).
        for raw in reversed(log.read_text(encoding="utf-8").splitlines()):
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("tool") != tool or entry.get("key") != key:
                continue
            ts = entry.get("ts")
            if not ts:
                continue
            try:
                t = _dt.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if (now - t).total_seconds() > _IDEMPOTENCY_TTL_SEC:
                return None
            return entry.get("response")
    except OSError:
        return None
    return None


def _idempotency_record(edpa_root: Path, tool: str, key: str,
                        response_text: str) -> None:
    if not key:
        return
    log = _idempotency_path(edpa_root)
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _utc_now_iso(),
        "tool": tool,
        "key": key,
        "response": response_text,
    }
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("idempotency log append failed: %s", exc)


def _idempotent(tool: str):
    """Decorator: short-circuit on cached idempotency_key, record on success.

    Wraps a handler ``(edpa_root, args) -> list[TextContent]``. Looks up
    ``args['idempotency_key']``; if a non-error cached response exists,
    returns it unchanged. Otherwise runs the handler and records the
    response unless it starts with ``"ERROR"``.
    """
    def decorator(fn):
        def wrapper(edpa_root: Path, args: dict) -> list[TextContent]:
            key = args.get("idempotency_key") if isinstance(args, dict) else None
            if key:
                cached = _idempotency_lookup(edpa_root, tool, key)
                if cached is not None:
                    return [TextContent(type="text", text=cached)]
            result = fn(edpa_root, args)
            if key and result and not result[0].text.startswith("ERROR"):
                _idempotency_record(edpa_root, tool, key, result[0].text)
            return result
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Write tool handlers
# ---------------------------------------------------------------------------

@_idempotent("edpa_item_create")
def _handle_item_create(edpa_root: Path, args: dict) -> list[TextContent]:
    item_type = args.get("type")
    title = args.get("title")
    if item_type not in TYPE_DIRS:
        return _err(f"invalid type {item_type!r}; expected one of {sorted(TYPE_DIRS)}")
    if not isinstance(title, str) or not title.strip():
        return _err("title is required and must be a non-empty string")

    parent = args.get("parent")
    if parent is not None:
        safe_parent = _safe_item_id(parent)
        if safe_parent is None:
            return _err(f"invalid parent id {parent!r}")
        parent_path = _find_item_file(edpa_root, safe_parent)
        if not parent_path:
            return _err(f"parent {safe_parent} not found")
        expected = PARENT_RULES.get(item_type)
        if expected:
            parent_data = _load_md_item(parent_path) or {}
            if parent_data.get("type") != expected:
                return _err(
                    f"parent {safe_parent} is {parent_data.get('type')!r}, "
                    f"expected {expected!r} for {item_type}"
                )
    elif PARENT_RULES.get(item_type):
        return _err(
            f"type {item_type} requires --parent (expected {PARENT_RULES[item_type]})"
        )

    iteration = args.get("iteration")
    if iteration is not None and _safe_iteration_id(iteration) is None:
        return _err(f"invalid iteration id {iteration!r}")
    assignee = args.get("assignee")
    if assignee is not None and _safe_person_id(assignee) is None:
        return _err(f"invalid assignee id {assignee!r}")

    repo_root = edpa_root.parent
    new_id = _allocate_id(item_type, repo_root)

    item: dict = {
        "id": new_id,
        "type": item_type,
        "title": title.strip(),
        "status": args.get("status") or "Funnel",
    }
    if parent:
        item["parent"] = parent
    if iteration:
        item["iteration"] = iteration
    if assignee:
        item["assignee"] = assignee
    # V2.1 strict defaults — WSJF fields always present so engine reads a
    # deterministic value (no implicit-zero coercion) and so the YAML
    # surfaces "this item has not been WSJF-scored yet" visibly to humans.
    for field in ("js", "bv", "tc", "rr_oe"):
        item[field] = args[field] if args.get(field) is not None else 0
    js = item["js"]
    bv = item["bv"]
    tc = item["tc"]
    rr = item["rr_oe"]
    item["wsjf"] = round((bv + tc + rr) / js, 2) if js > 0 else 0.0

    file_path = edpa_root / "backlog" / TYPE_DIRS[item_type] / f"{new_id}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _save_md_item(file_path, item, body=args.get("body") or "")
    _load_yaml_cache_clear()

    logger.info("edpa_item_create: id=%s type=%s", new_id, item_type)
    return _ok({
        "id": new_id,
        "type": item_type,
        "path": str(file_path.relative_to(repo_root)),
    })


_UPDATE_ALLOWED_FIELDS = frozenset({
    "title", "iteration", "iteration_half", "assignee",
    "js", "bv", "tc", "rr_oe",
})


@_idempotent("edpa_item_update")
def _handle_item_update(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        return _err(f"invalid item_id {raw_id!r}")
    fields = args.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        return _err("fields must be a non-empty object")
    invalid = set(fields) - _UPDATE_ALLOWED_FIELDS
    if invalid:
        return _err(
            f"fields {sorted(invalid)!r} not allowed by edpa_item_update "
            f"(use edpa_item_transition for status, edpa_item_link_parent for parent)"
        )

    path = _find_item_file(edpa_root, safe_id)
    if not path:
        return _err(f"item {safe_id} not found")

    if "iteration" in fields and fields["iteration"] is not None:
        if _safe_iteration_id(fields["iteration"]) is None:
            return _err(f"invalid iteration id {fields['iteration']!r}")
    if "assignee" in fields and fields["assignee"] is not None:
        if _safe_person_id(fields["assignee"]) is None:
            return _err(f"invalid assignee id {fields['assignee']!r}")

    item = _load_md_item(path) or {}
    body = item.pop("body", "") if isinstance(item, dict) else ""
    item.update(fields)
    # V2.1 — keep WSJF fields explicit (write 0 if any are still missing
    # after the update; this also handles legacy items that pre-date the
    # strict-defaults rule). wsjf is always recomputed deterministically.
    for f in ("js", "bv", "tc", "rr_oe"):
        if item.get(f) is None:
            item[f] = 0
    js, bv, tc, rr = item["js"], item["bv"], item["tc"], item["rr_oe"]
    item["wsjf"] = round((bv + tc + rr) / js, 2) if js > 0 else 0.0
    _save_md_item(path, item, body=body)
    _load_yaml_cache_clear()

    logger.info("edpa_item_update: id=%s fields=%s", safe_id, list(fields))
    return _ok({"id": safe_id, "updated": list(fields)})


@_idempotent("edpa_item_transition")
def _handle_item_transition(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        return _err(f"invalid item_id {raw_id!r}")
    status = args.get("status")
    if not isinstance(status, str) or not status:
        return _err("status is required")

    path = _find_item_file(edpa_root, safe_id)
    if not path:
        return _err(f"item {safe_id} not found")

    item = _load_md_item(path) or {}
    item_type = item.get("type")
    allowed = _allowed_statuses(item_type)
    if allowed is not None and status not in allowed:
        return _err(
            f"status {status!r} not valid for {item_type}; "
            f"allowed: {list(allowed)}"
        )

    body = item.pop("body", "") if isinstance(item, dict) else ""
    item["status"] = status
    closed_at = item.get("closed_at")
    if status == "Done" and not closed_at:
        closed_at = _utc_now_iso()
        item["closed_at"] = closed_at
    _save_md_item(path, item, body=body)
    _load_yaml_cache_clear()

    logger.info("edpa_item_transition: id=%s status=%s", safe_id, status)
    return _ok({"id": safe_id, "status": status, "closed_at": closed_at})


@_idempotent("edpa_item_link_parent")
def _handle_item_link_parent(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        return _err(f"invalid item_id {raw_id!r}")
    raw_parent = args.get("parent_id", "")
    safe_parent = _safe_item_id(raw_parent)
    if safe_parent is None:
        return _err(f"invalid parent_id {raw_parent!r}")
    if safe_id == safe_parent:
        return _err("item cannot be its own parent")

    path = _find_item_file(edpa_root, safe_id)
    if not path:
        return _err(f"item {safe_id} not found")
    parent_path = _find_item_file(edpa_root, safe_parent)
    if not parent_path:
        return _err(f"parent {safe_parent} not found")

    item = _load_md_item(path) or {}
    parent_data = _load_md_item(parent_path) or {}
    expected = PARENT_RULES.get(item.get("type"))
    if expected and parent_data.get("type") != expected:
        return _err(
            f"parent {safe_parent} is {parent_data.get('type')!r}, "
            f"expected {expected!r} for {item.get('type')}"
        )

    body = item.pop("body", "") if isinstance(item, dict) else ""
    item["parent"] = safe_parent
    _save_md_item(path, item, body=body)
    _load_yaml_cache_clear()

    logger.info("edpa_item_link_parent: id=%s parent=%s", safe_id, safe_parent)
    return _ok({"id": safe_id, "parent": safe_parent})


@_idempotent("edpa_iteration_create")
def _handle_iteration_create(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("id", "")
    safe_id = _safe_iteration_id(raw_id)
    if safe_id is None:
        return _err(f"invalid iteration id {raw_id!r}; expected pattern PI-YYYY-N[.M]")
    start = args.get("start_date")
    end = args.get("end_date")
    if not start or not end:
        return _err("start_date and end_date are required")

    iter_path = edpa_root / "iterations" / f"{safe_id}.yaml"
    if iter_path.exists():
        return _err(f"iteration {safe_id} already exists at {iter_path.name}")

    pi_id = safe_id.rsplit(".", 1)[0] if "." in safe_id else safe_id
    data: dict = {
        "iteration": {
            "id": safe_id,
            "pi": pi_id,
            "start_date": start,
            "end_date": end,
            "status": "planned",
        }
    }
    if args.get("type"):
        data["iteration"]["type"] = args["type"]

    _write_yaml_atomic(iter_path, data)
    logger.info("edpa_iteration_create: id=%s", safe_id)
    return _ok({
        "id": safe_id,
        "path": str(iter_path.relative_to(edpa_root.parent)),
    })


@_idempotent("edpa_iteration_close")
def _handle_iteration_close(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("id", "")
    safe_id = _safe_iteration_id(raw_id)
    if safe_id is None:
        return _err(f"invalid iteration id {raw_id!r}")

    iter_path = edpa_root / "iterations" / f"{safe_id}.yaml"
    if not iter_path.exists():
        return _err(f"iteration {safe_id} not found")

    with open(iter_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    iteration = data.get("iteration") or {}
    if iteration.get("status") == "closed":
        return _ok({"id": safe_id, "status": "closed", "already_closed": True})
    iteration["status"] = "closed"
    data["iteration"] = iteration
    # Lifecycle "closed" is read from two places by different consumers: the
    # nested iteration.status (loader-lifted readers, capacity_override) AND the
    # top-level status (pi_close, reports, board lifecycle view, e2e verifier).
    # Set both so every consumer agrees the iteration is closed.
    data["status"] = "closed"
    _write_yaml_atomic(iter_path, data)

    logger.info("edpa_iteration_close: id=%s", safe_id)
    return _ok({"id": safe_id, "status": "closed"})


@_idempotent("edpa_pi_create")
def _handle_pi_create(edpa_root: Path, args: dict) -> list[TextContent]:
    """Create the PI-level metadata file by delegating to create_pi.py — the
    single source of behavior (also driven by the /edpa:create-pi command).

    Write only; no git commit, consistent with the other MCP write tools (the
    CLI layer is what commits). create_pi() raises ValueError on a bad/
    duplicate id or invalid field, which we surface via _err.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from create_pi import create_pi  # noqa: E402
        result = create_pi(
            edpa_root,
            args.get("id", ""),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            iteration_weeks=args.get("iteration_weeks", 1),
            pi_iterations=args.get("pi_iterations"),
            status=args.get("status", "planning"),
        )
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)

    logger.info("edpa_pi_create: id=%s", result["id"])
    rel_path = str(Path(result["path"]).relative_to(edpa_root.parent))
    return _ok({"id": result["id"], "path": rel_path})


def _handle_pi_close(edpa_root: Path, args: dict) -> list[TextContent]:
    """Close a PI by delegating to pi_close.close_pi — the single source of
    behavior (also driven by the /edpa:close-pi command).

    Verifies every child iteration is closed (unless force), flips the PI-level
    pi.status to 'closed', and writes the rollup report. Write only; no git
    commit, consistent with the other MCP write tools (the CLI layer commits).
    NOT @_idempotent: the rollup must stay re-runnable as iteration data
    changes. close_pi() raises ValueError on a bad id, a PI with no iterations,
    or a still-open iteration — surfaced via _err.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from pi_close import close_pi  # noqa: E402
        result = close_pi(
            edpa_root, args.get("id", ""),
            force=bool(args.get("force", False)))
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)

    logger.info("edpa_pi_close: id=%s status_changed=%s",
                result["pi"], result["status_changed"])
    root = edpa_root.parent
    return _ok({
        "id": result["pi"],
        "status": result["status"],
        "status_changed": result["status_changed"],
        "iteration_count": result["iteration_count"],
        "open_iterations": result["open_iterations"],
        "results_path": str(Path(result["results_path"]).relative_to(root)),
        "summary_path": str(Path(result["summary_path"]).relative_to(root)),
    })


def _load_depends_on_map(edpa_root: Path) -> dict:
    """Map every backlog item id -> its depends_on list (scans all type dirs)."""
    graph: dict[str, list[str]] = {}
    backlog = edpa_root / "backlog"
    for sub in TYPE_DIRS.values():
        dir_path = backlog / sub
        if not dir_path.is_dir():
            continue
        for f in dir_path.glob("*.md"):
            data = _load_md_item(f)
            if not data:
                continue
            iid = data.get("id")
            if not iid:
                continue
            deps = data.get("depends_on")
            graph[str(iid)] = [str(x) for x in deps] if isinstance(deps, list) else []
    return graph


def _dep_would_cycle(edpa_root: Path, src: str, dst: str) -> bool:
    """True if adding the edge src -> dst (src depends_on dst) creates a cycle,
    i.e. src is already reachable from dst via existing depends_on edges."""
    graph = _load_depends_on_map(edpa_root)
    seen: set[str] = set()
    stack = list(graph.get(dst, []))
    while stack:
        node = stack.pop()
        if node == src:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return False


@_idempotent("edpa_item_link_dep")
def _handle_item_link_dep(edpa_root: Path, args: dict) -> list[TextContent]:
    """Add or remove a dependency edge on a backlog item's ``depends_on`` list.

    ``depends_on=[B]`` on item A means "A depends on B" (B must land first) —
    the program board's dependency arrows. Validates both items exist, refuses
    a self-loop, and (on add) refuses an edge that would create a cycle.
    """
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        return _err(f"invalid item_id {raw_id!r}")
    raw_dep = args.get("depends_on_id", "")
    safe_dep = _safe_item_id(raw_dep)
    if safe_dep is None:
        return _err(f"invalid depends_on_id {raw_dep!r}")
    action = args.get("action", "add")
    if action not in ("add", "remove"):
        return _err(f"action must be 'add' or 'remove' (got {action!r})")
    if safe_id == safe_dep:
        return _err("item cannot depend on itself")

    path = _find_item_file(edpa_root, safe_id)
    if not path:
        return _err(f"item {safe_id} not found")

    item = _load_md_item(path) or {}
    deps = item.get("depends_on")
    deps = [str(d) for d in deps] if isinstance(deps, list) else []

    if action == "add":
        if not _find_item_file(edpa_root, safe_dep):
            return _err(f"depends_on target {safe_dep} not found")
        if safe_dep in deps:
            return _ok({"id": safe_id, "depends_on": deps, "action": "add", "noop": True})
        if _dep_would_cycle(edpa_root, safe_id, safe_dep):
            return _err(f"adding {safe_id} -> {safe_dep} would create a dependency cycle")
        deps.append(safe_dep)
    else:  # remove
        if safe_dep not in deps:
            return _ok({"id": safe_id, "depends_on": deps, "action": "remove", "noop": True})
        deps = [d for d in deps if d != safe_dep]

    body = item.pop("body", "") if isinstance(item, dict) else ""
    if deps:
        item["depends_on"] = deps
    else:
        item.pop("depends_on", None)
    _save_md_item(path, item, body=body)
    _load_yaml_cache_clear()

    logger.info("edpa_item_link_dep: id=%s %s %s", safe_id, action, safe_dep)
    return _ok({"id": safe_id, "depends_on": deps, "action": action})


ROAM_STATUSES = frozenset({"resolved", "owned", "accepted", "mitigated"})


@_idempotent("edpa_item_roam")
def _handle_item_roam(edpa_root: Path, args: dict) -> list[TextContent]:
    """Set the ROAM classification (Resolved / Owned / Accepted / Mitigated) on a
    Risk item — the PI planning ROAM board groups risks into these four columns.
    Applies only to items of type Risk.
    """
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        return _err(f"invalid item_id {raw_id!r}")
    roam = args.get("roam_status")
    if roam not in ROAM_STATUSES:
        return _err(f"roam_status must be one of {sorted(ROAM_STATUSES)} (got {roam!r})")

    path = _find_item_file(edpa_root, safe_id)
    if not path:
        return _err(f"item {safe_id} not found")

    item = _load_md_item(path) or {}
    if item.get("type") != "Risk":
        return _err(f"roam_status applies only to Risk items ({safe_id} is {item.get('type')!r})")

    body = item.pop("body", "") if isinstance(item, dict) else ""
    item["roam_status"] = roam
    _save_md_item(path, item, body=body)
    _load_yaml_cache_clear()

    logger.info("edpa_item_roam: id=%s roam_status=%s", safe_id, roam)
    return _ok({"id": safe_id, "roam_status": roam})


@_idempotent("edpa_objective_set")
def _handle_objective_set(edpa_root: Path, args: dict) -> list[TextContent]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from objectives import set_objective  # noqa: E402
        result = set_objective(
            edpa_root, args.get("pi", ""), args.get("team", ""),
            args.get("kind", ""), args.get("title", ""),
            bv=args.get("bv"), status=args.get("status"),
        )
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)
    logger.info("edpa_objective_set: pi=%s team=%s %s",
                result["pi"], result["team"], result["action"])
    return _ok(result)


@_idempotent("edpa_objective_remove")
def _handle_objective_remove(edpa_root: Path, args: dict) -> list[TextContent]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from objectives import remove_objective  # noqa: E402
        result = remove_objective(
            edpa_root, args.get("pi", ""), args.get("team", ""),
            args.get("kind", ""), args.get("title", ""),
        )
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)
    logger.info("edpa_objective_remove: pi=%s team=%s", result["pi"], result["team"])
    return _ok(result)


@_idempotent("edpa_confidence_vote")
def _handle_confidence_vote(edpa_root: Path, args: dict) -> list[TextContent]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from objectives import set_confidence  # noqa: E402
        result = set_confidence(
            edpa_root, args.get("pi", ""), args.get("team", ""), args.get("confidence"),
        )
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)
    logger.info("edpa_confidence_vote: pi=%s team=%s c=%s",
                result["pi"], result["team"], result["confidence"])
    return _ok(result)


def _handle_pi_board(edpa_root: Path, args: dict) -> list[TextContent]:
    """Generate the self-contained PI planning / overview HTML by delegating to
    pi_planning.py — the single source of behavior (also driven by the
    /edpa:pi-planning command). A read-only projection of .edpa/; safe to re-run.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from pi_planning import generate_pi_board  # noqa: E402
        # find_edpa_root() returns the .edpa/ dir; generate_pi_board wants the
        # repo root (it builds root/.edpa/... paths).
        result = generate_pi_board(edpa_root.parent, pi=args.get("pi"))
    except ValueError as exc:
        return _err(str(exc))
    finally:
        sys.path.pop(0)

    logger.info("edpa_pi_board: pi=%s items=%s", result["pi"], result["items"])
    try:
        rel_path = str(Path(result["path"]).relative_to(edpa_root.parent))
    except ValueError:
        rel_path = result["path"]
    return _ok({
        "pi": result["pi"],
        "path": rel_path,
        "items": result["items"],
        "people": result["people"],
        "objectives": result["objectives"],
        "schema_version": result["schema_version"],
    })


_PEOPLE_ALLOWED_FIELDS = frozenset({
    "name", "role", "team", "fte", "capacity",
    "capacity_per_iteration", "github", "availability", "contract",
})


@_idempotent("edpa_people_upsert")
def _handle_people_upsert(edpa_root: Path, args: dict) -> list[TextContent]:
    raw_id = args.get("id", "")
    safe_id = _safe_person_id(raw_id)
    if safe_id is None:
        return _err(f"invalid person id {raw_id!r}")
    fields = {k: v for k, v in args.items()
              if k not in ("id", "idempotency_key") and v is not None}
    invalid = set(fields) - _PEOPLE_ALLOWED_FIELDS
    if invalid:
        return _err(f"fields {sorted(invalid)!r} not allowed for people.yaml")

    people_path = edpa_root / "config" / "people.yaml"
    if not people_path.exists():
        return _err(f"{people_path.name} not found")

    with open(people_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    people = data.get("people") or []
    existing = next((p for p in people if p.get("id") == safe_id), None)
    if existing is not None:
        existing.update(fields)
        action = "updated"
    else:
        if not fields.get("name"):
            return _err(f"creating new person {safe_id!r} requires 'name'")
        people.append({"id": safe_id, **fields})
        action = "created"
    data["people"] = people
    _write_yaml_atomic(people_path, data)

    logger.info("edpa_people_upsert: id=%s action=%s", safe_id, action)
    return _ok({"id": safe_id, "action": action, "fields": sorted(fields)})


def _handle_forecast_pi(edpa_root: Path, args: dict) -> list[TextContent]:
    pi = args.get("pi", "")
    if not pi or not isinstance(pi, str):
        return _err("pi is required (e.g. PI-2026-2)")
    window = args.get("window", 3)
    simulations = args.get("simulations", 1000)

    with _sibling_path():
        try:
            from forecast import forecast_pi  # noqa: E402
            result = forecast_pi(edpa_root, pi, window=window, simulations=simulations)
        except ValueError as exc:
            return _err(str(exc))
        except ImportError as exc:
            return _err(f"forecast module not available: {exc}")

    logger.info("edpa_forecast_pi: pi=%s p50=%s prob=%s%%",
                pi, result.get("p50"), result.get("completion_probability"))
    return _ok(result)


def _handle_pi_metrics(edpa_root: Path, args: dict) -> list[TextContent]:
    window = args.get("window", 5)
    pi = args.get("pi") or None

    with _sibling_path():
        try:
            from pi_metrics import pi_metrics  # noqa: E402
            result = pi_metrics(edpa_root, window=window, pi=pi)
        except ImportError as exc:
            return _err(f"pi_metrics module not available: {exc}")

    logger.info("edpa_pi_metrics: pis=%s", len(result.get("pis", [])))
    return _ok(result)


def _handle_insights(edpa_root: Path, args: dict) -> list[TextContent]:
    iteration = args.get("iteration", "")
    if not iteration:
        return _err("iteration is required (e.g. PI-2026-1.3)")
    overload = float(args.get("overload_threshold", 1.10))
    js_max = int(args.get("js_threshold", 8))
    stale = int(args.get("stale_days", 5))

    with _sibling_path():
        try:
            from insights import insights as run_insights  # noqa: E402
            result = run_insights(
                edpa_root=edpa_root,
                iteration_id=iteration,
                overload_threshold=overload,
                js_threshold=js_max,
                stale_days=stale,
            )
        except FileNotFoundError as exc:
            return _err(str(exc))
        except ImportError as exc:
            return _err(f"insights module not available: {exc}")

    logger.info("edpa_insights: iter=%s anomalies=%s", iteration, result.get("anomaly_count"))
    return _ok(result)


def _handle_ai_attribution(edpa_root: Path, args: dict) -> list[TextContent]:
    iteration = args.get("iteration", "")
    if not iteration:
        return _err("iteration is required (e.g. PI-2026-1.3)")

    with _sibling_path():
        try:
            from ai_attribution import ai_attribution as run_ai_attribution  # noqa: E402
            result = run_ai_attribution(
                edpa_root=edpa_root,
                iteration_id=iteration,
            )
        except FileNotFoundError as exc:
            return _err(str(exc))
        except ImportError as exc:
            return _err(f"ai_attribution module not available: {exc}")

    s = result.get("summary", {})
    logger.info("edpa_ai_attribution: iter=%s ai_ratio=%s",
                iteration, s.get("ai_delivery_ratio"))
    return _ok(result)


def _handle_payroll_export(edpa_root: Path, args: dict) -> list[TextContent]:
    iteration = args.get("iteration", "")
    if not iteration:
        return _err("iteration is required (e.g. PI-2026-1.3)")
    currency = args.get("currency", "")
    raw_output = args.get("output")
    output_path = Path(raw_output) if raw_output else None

    with _sibling_path():
        try:
            from payroll_export import export as run_export  # noqa: E402
            result = run_export(
                edpa_root=edpa_root,
                iteration_id=iteration,
                currency=currency,
                output=output_path,
            )
        except FileNotFoundError as exc:
            return _err(str(exc))
        except ImportError as exc:
            return _err(f"payroll_export module not available: {exc}")

    logger.info("edpa_payroll_export: iter=%s rows=%s hours=%s",
                iteration, result.get("rows"), result.get("total_hours"))
    return _ok(result)


def _handle_reconcile(edpa_root: Path, args: dict) -> list[TextContent]:
    branch = args.get("branch") or None
    stale_days = int(args.get("stale_days", 3))

    with _sibling_path():
        try:
            from reconcile import build_report  # noqa: E402
            report = build_report(edpa_root.parent, edpa_root,
                                  branch=branch, stale_days=stale_days)
        except ImportError as exc:
            return _err(f"reconcile module not available: {exc}")
        except (RuntimeError, SystemExit) as exc:
            return _err(str(exc))

    report["stuck"] = [{k: v for k, v in s.items() if k != "_path"}
                       for s in report["stuck"]]
    logger.info("edpa_reconcile: branch=%s stuck=%s phantoms=%s",
                report["branch"], len(report["stuck"]), len(report["phantoms"]))
    return _ok(report)


def _dispatch_item(edpa_root: Path, args: dict) -> list[TextContent]:
    """edpa_item entry: validates item_id before reaching the handler."""
    raw_id = args.get("item_id", "")
    safe_id = _safe_item_id(raw_id)
    if safe_id is None:
        logger.warning("edpa_item: rejected item_id=%r", raw_id)
        return [TextContent(type="text",
                            text=f"ERROR: invalid item_id {raw_id!r}. "
                                 "Expected pattern: <type-prefix>-<digits>, "
                                 "e.g. S-200, F-12, I-1.")]
    return _handle_item(edpa_root, safe_id)


# ---------------------------------------------------------------------------
# Tool dispatch registry — the single dispatch source for call_tool().
# Every tool advertised by list_tools() must have an entry here and vice
# versa (pinned by test_tool_registry_matches_list_tools). All entries take
# (edpa_root, arguments); thin lambdas adapt the legacy positional handlers.
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    # read tools
    "edpa_status": lambda root, args: _handle_status(root),
    "edpa_iterations": lambda root, args: _handle_iterations(root, args.get("status")),
    "edpa_people": lambda root, args: _handle_people(root, args.get("team")),
    "edpa_backlog": lambda root, args: _handle_backlog(
        root, args.get("iteration"), args.get("type"), args.get("status")),
    "edpa_item": _dispatch_item,
    "edpa_validate": lambda root, args: _handle_validate(root),
    "edpa_flow_metrics": lambda root, args: _handle_flow_metrics(
        root, args.get("iteration"), args.get("level")),
    "edpa_pi_board": _handle_pi_board,
    "edpa_forecast_pi": _handle_forecast_pi,
    "edpa_pi_metrics": _handle_pi_metrics,
    "edpa_insights": _handle_insights,
    "edpa_ai_attribution": _handle_ai_attribution,
    "edpa_payroll_export": _handle_payroll_export,
    "edpa_reconcile": _handle_reconcile,
    # write tools
    "edpa_item_create": _handle_item_create,
    "edpa_item_update": _handle_item_update,
    "edpa_item_transition": _handle_item_transition,
    "edpa_item_link_parent": _handle_item_link_parent,
    "edpa_item_link_dep": _handle_item_link_dep,
    "edpa_item_roam": _handle_item_roam,
    "edpa_objective_set": _handle_objective_set,
    "edpa_objective_remove": _handle_objective_remove,
    "edpa_confidence_vote": _handle_confidence_vote,
    "edpa_iteration_create": _handle_iteration_create,
    "edpa_iteration_close": _handle_iteration_close,
    "edpa_pi_create": _handle_pi_create,
    "edpa_pi_close": _handle_pi_close,
    "edpa_people_upsert": _handle_people_upsert,
}


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@server.list_resources()
async def list_resources() -> list[Resource]:
    edpa_root = find_edpa_root()
    resources = []
    if edpa_root:
        if (edpa_root / "config" / "edpa.yaml").exists():
            resources.append(Resource(uri="edpa://config", name="EDPA Configuration", description="Project config: name, funding, organizations, governance, naming, issue types", mimeType="application/x-yaml"))
        if (edpa_root / "config" / "people.yaml").exists():
            resources.append(Resource(uri="edpa://people", name="EDPA Team Registry", description="Team members, roles, FTE, capacity", mimeType="application/x-yaml"))
        # Add iteration resources for each iteration
        for it_dir in sorted((edpa_root / "reports").glob("iteration-*")) if (edpa_root / "reports").exists() else []:
            results_file = it_dir / "edpa_results.json"
            if results_file.exists():
                it_id = it_dir.name.replace("iteration-", "")
                resources.append(Resource(uri=f"edpa://results/{it_id}", name=f"EDPA Results: {it_id}", description=f"Engine results for iteration {it_id}", mimeType="application/json"))
    return resources


@server.read_resource()
async def read_resource(uri: str) -> str:
    edpa_root = find_edpa_root()
    if not edpa_root:
        return "ERROR: .edpa/ directory not found."

    if uri == "edpa://config":
        path = edpa_root / "config" / "edpa.yaml"
    elif uri == "edpa://people":
        path = edpa_root / "config" / "people.yaml"
    elif uri.startswith("edpa://results/"):
        it_id = uri.replace("edpa://results/", "")
        safe = _safe_iteration_id(it_id)
        if safe is None:
            return f"ERROR: invalid iteration id: {it_id!r}"
        path = edpa_root / "reports" / f"iteration-{safe}" / "edpa_results.json"
    else:
        return f"ERROR: Unknown resource URI: {uri}"

    if not path.exists():
        return f"ERROR: File not found: {path}"

    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
