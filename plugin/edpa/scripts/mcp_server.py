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
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info("call_tool name=%s args=%s", name, arguments)
    edpa_root = find_edpa_root()
    if edpa_root is None:
        logger.warning("call_tool name=%s: .edpa/ not found", name)
        return [TextContent(type="text", text="ERROR: .edpa/ directory not found. Run `/edpa setup` first.")]

    try:
        if name == "edpa_status":
            return _handle_status(edpa_root)
        elif name == "edpa_iterations":
            return _handle_iterations(edpa_root, arguments.get("status"))
        elif name == "edpa_people":
            return _handle_people(edpa_root, arguments.get("team"))
        elif name == "edpa_backlog":
            return _handle_backlog(edpa_root, arguments.get("iteration"),
                                   arguments.get("type"), arguments.get("status"))
        elif name == "edpa_item":
            raw_id = arguments.get("item_id", "")
            safe_id = _safe_item_id(raw_id)
            if safe_id is None:
                logger.warning("edpa_item: rejected item_id=%r", raw_id)
                return [TextContent(type="text",
                                    text=f"ERROR: invalid item_id {raw_id!r}. "
                                         "Expected pattern: <type-prefix>-<digits>, "
                                         "e.g. S-200, F-12, I-1.")]
            return _handle_item(edpa_root, safe_id)
        elif name == "edpa_validate":
            return _handle_validate(edpa_root)
        elif name == "edpa_flow_metrics":
            return _handle_flow_metrics(
                edpa_root,
                arguments.get("iteration"),
                arguments.get("level"),
            )
        elif name == "edpa_item_create":
            return _handle_item_create(edpa_root, arguments)
        elif name == "edpa_item_update":
            return _handle_item_update(edpa_root, arguments)
        elif name == "edpa_item_transition":
            return _handle_item_transition(edpa_root, arguments)
        elif name == "edpa_item_link_parent":
            return _handle_item_link_parent(edpa_root, arguments)
        elif name == "edpa_iteration_create":
            return _handle_iteration_create(edpa_root, arguments)
        elif name == "edpa_iteration_close":
            return _handle_iteration_close(edpa_root, arguments)
        elif name == "edpa_pi_create":
            return _handle_pi_create(edpa_root, arguments)
        elif name == "edpa_people_upsert":
            return _handle_people_upsert(edpa_root, arguments)
        logger.warning("call_tool: unknown tool %s", name)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
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

    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
        path = edpa_root / "reports" / f"iteration-{it_id}" / "edpa_results.json"
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
