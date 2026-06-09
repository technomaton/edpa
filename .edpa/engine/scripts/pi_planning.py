#!/usr/bin/env python3
"""
EDPA PI Planning — generate a self-contained PI planning / overview HTML.

Reads the local ``.edpa/`` model, builds the versioned EDPA snapshot (the
``window.__EDPA__`` contract), injects it into the prebuilt single-file React
bundle, and writes a portable, READ-ONLY ``pi-<PI>.html``.

This is the script-first delivery of the PI planning view: it mirrors the
``.edpa → contract`` transform in ``tools/pi-planning/server`` (TypeScript) so
the generated artifact needs only Python — no Node, no server, no build on the
target machine. Mutations happen via MCP write-tools / the LLM editing
``.edpa/`` + git; this script just re-renders the projection.

Usage:
    python pi_planning.py                          # default PI (planning>active>first)
    python pi_planning.py --pi PI-2026-1
    python pi_planning.py --open                   # generate & open in browser
    python pi_planning.py --bundle path/to/pi-bundle.html
    python pi_planning.py --output /tmp/pi.html
"""

from __future__ import annotations

import argparse
import datetime
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _md_frontmatter import load_md as _load_md  # noqa: E402
finally:
    sys.path.pop(0)

# Contract version of the injected ``window.__EDPA__`` blob. Bump when the
# shape changes; the bundle can check it to refuse incompatible snapshots.
SCHEMA_VERSION = 1  # see tools/pi-planning/src/types/snapshot.ts (single source)

BACKLOG_DIRS = ["initiatives", "epics", "features", "stories", "defects", "events", "risks"]

# Injection point in the prebuilt bundle (see tools/pi-planning/index.html).
_INJECT_RE = re.compile(
    r'(<script[^>]*id="__edpa_data__"[^>]*>)\s*__EDPA_DATA__\s*(</script>)',
    re.IGNORECASE,
)


# ── Repo discovery (mirror findEdpaRoot / board.py) ───────────────────────────

def find_repo_root(start: Path | None = None) -> Path | None:
    p = Path(start or Path.cwd()).resolve()
    while p != p.parent:
        if (p / ".edpa" / "config" / "people.yaml").exists():
            return p
        p = p.parent
    return None


# ── Loaders (mirror tools/pi-planning/server/yaml-store.ts) ───────────────────

def load_backlog(root: Path) -> list[dict]:
    """All backlog items as frontmatter + body dicts (mirror loadAllItems)."""
    items: list[dict] = []
    base = root / ".edpa" / "backlog"
    for d in BACKLOG_DIRS:
        dir_path = base / d
        if not dir_path.is_dir():
            continue
        for f in sorted(dir_path.glob("*.md")):
            item = _load_md(f)
            if item and item.get("id"):
                items.append(item)
    return items


def load_people_config(root: Path) -> dict:
    """people.yaml → {people, teams, project} (mirror loadPeopleConfig)."""
    path = root / ".edpa" / "config" / "people.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "people": data.get("people") or [],
        "teams": data.get("teams") or [],
        "project": data.get("project") or {"name": "EDPA"},
    }


def _natkey(s) -> list:
    """Numeric-aware sort key (mirror localeCompare(..., {numeric:true}))."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s or ""))]


def _fmt_date(v) -> str:
    if isinstance(v, (datetime.datetime, datetime.date)):
        return f"{v.day}.{v.month}."
    if isinstance(v, str):
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            return f"{int(m.group(3))}.{int(m.group(2))}."
        return v
    return str(v)


def format_iteration_dates(start, end) -> str:
    """`D.M.–D.M.` (mirror formatIterationDates)."""
    if not start or not end:
        return ""
    return f"{_fmt_date(start)}–{_fmt_date(end)}"


def load_pis(root: Path) -> list[dict]:
    """iterations/*.yaml → PIConfig[] (mirror loadPisFromIterationsDir)."""
    iter_dir = root / ".edpa" / "iterations"
    if not iter_dir.is_dir():
        return []

    pi_blocks: dict[str, dict] = {}
    iter_blocks: list[dict] = []
    for f in sorted(iter_dir.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("pi"), dict):
            pid = data["pi"].get("id")
            if pid:
                pi_blocks[pid] = data["pi"]
        elif isinstance(data.get("iteration"), dict):
            iter_blocks.append(data["iteration"])

    iter_by_pi: dict[str, list[dict]] = {}
    for it in iter_blocks:
        pid = it.get("pi")
        if not pid:
            continue
        iter_by_pi.setdefault(pid, []).append({
            "id": it.get("id"),
            "dates": format_iteration_dates(it.get("start_date"), it.get("end_date")),
            "status": it.get("status") or "planned",
            "type": it.get("type"),
        })
    for arr in iter_by_pi.values():
        arr.sort(key=lambda x: _natkey(x.get("id")))

    pis: list[dict] = []
    for pid, pdata in pi_blocks.items():
        iters = iter_by_pi.get(pid, [])
        pis.append({
            "id": pid,
            "status": pdata.get("status") or "planning",
            "pi_iterations": pdata.get("pi_iterations") or len(iters),
            "iteration_weeks": pdata.get("iteration_weeks") or 2,
            "iterations": iters,
            "shared_services": pdata.get("shared_services"),
            "events": pdata.get("events"),
        })
    # PIs that only have iteration files (no PI metadata file).
    for pid, iters in iter_by_pi.items():
        if pid in pi_blocks:
            continue
        all_closed = all(i["status"] == "closed" for i in iters)
        has_active = any(i["status"] == "active" for i in iters)
        pis.append({
            "id": pid,
            "status": "closed" if all_closed else ("active" if has_active else "planning"),
            "pi_iterations": len(iters),
            "iteration_weeks": 2,
            "iterations": iters,
        })

    pis.sort(key=lambda p: _natkey(p.get("id")))
    return pis


def load_objectives(root: Path) -> dict:
    """pi-objectives/<PI>.yaml → {pi_id: ObjectivesData} (mirror objectivesRoutes)."""
    obj_dir = root / ".edpa" / "pi-objectives"
    out: dict[str, dict] = {}
    if not obj_dir.is_dir():
        return out
    for f in sorted(obj_dir.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out[f.stem] = data
    return out


# ── PI selection (mirror config-store default) ────────────────────────────────

def select_pi(pis: list[dict], requested: str | None) -> str | None:
    if requested:
        return requested
    for status in ("planning", "active"):
        for p in pis:
            if p.get("status") == status:
                return p["id"]
    return pis[0]["id"] if pis else None


# ── Snapshot assembly + injection ─────────────────────────────────────────────

def _json_default(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    return str(o)


def build_snapshot(root: Path, pi: str, pis: list[dict]) -> dict:
    people_cfg = load_people_config(root)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "pi": pi,
        "project": people_cfg["project"],
        "people": people_cfg["people"],
        "teams": people_cfg["teams"],
        "pis": pis,
        "backlog": load_backlog(root),
        "objectives": load_objectives(root),
        "git": {"branch": "(snapshot)", "dirty": [], "ahead": 0},
    }


def to_embed_json(snapshot: dict) -> str:
    """JSON safe to embed as <script> textContent."""
    raw = json.dumps(snapshot, default=_json_default, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def inject(bundle_html: str, embed_json: str) -> str:
    if not _INJECT_RE.search(bundle_html):
        raise ValueError(
            "injection point not found in bundle — rebuild it "
            "(cd tools/pi-planning && npm run build)."
        )
    return _INJECT_RE.sub(lambda m: m.group(1) + embed_json + m.group(2), bundle_html, count=1)


def find_bundle(explicit: str | None, script_dir: Path, repo_root: Path) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(script_dir.parent / "assets" / "pi-bundle.html")   # vendored
    candidates.append(repo_root / "tools" / "pi-planning" / "dist" / "index.html")  # dev
    for c in candidates:
        if c and c.is_file():
            return c
    raise ValueError(
        "PI planning bundle not found. Build it with "
        "`cd tools/pi-planning && npm run build` (or pass --bundle <path>)."
    )


def generate_pi_board(
    root: Path,
    pi: str | None = None,
    bundle: str | None = None,
    output: str | None = None,
) -> dict:
    """Render the self-contained PI planning HTML and return a result dict.

    Single source of behavior for both the CLI (``main``) and the
    ``edpa_pi_board`` MCP tool. ``root`` is the repo root (the dir holding
    ``.edpa/``). Raises ``ValueError`` on a missing bundle / no PIs / missing
    injection point — never ``SystemExit``, since it runs in-process inside the
    MCP server.
    """
    script_dir = Path(__file__).resolve().parent
    bundle_path = find_bundle(bundle, script_dir, root)

    pis = load_pis(root)
    selected = select_pi(pis, pi)
    if not selected:
        raise ValueError("no PIs found in .edpa/iterations/.")

    snapshot = build_snapshot(root, selected, pis)
    html = inject(bundle_path.read_text(encoding="utf-8"), to_embed_json(snapshot))

    out = (
        Path(output)
        if output
        else root / ".edpa" / "reports" / f"pi-{selected}" / f"pi-{selected}.html"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    return {
        "path": str(out),
        "pi": selected,
        "items": len(snapshot["backlog"]),
        "people": len(snapshot["people"]),
        "pis": len(pis),
        "objectives": len(snapshot["objectives"]),
        "bundle": bundle_path.name,
        "bundle_kb": bundle_path.stat().st_size // 1024,
        "schema_version": SCHEMA_VERSION,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="EDPA PI Planning — self-contained overview HTML")
    ap.add_argument("--pi", help="PI id (default: planning > active > first)")
    ap.add_argument("--bundle", help="Path to the prebuilt single-file bundle")
    ap.add_argument("--output", "-o", help="Output HTML path")
    ap.add_argument("--open", action="store_true", help="Open in the default browser")
    args = ap.parse_args()

    root = find_repo_root()
    if not root:
        raise SystemExit("ERROR: .edpa/ not found (need .edpa/config/people.yaml).")

    try:
        result = generate_pi_board(root, pi=args.pi, bundle=args.bundle, output=args.output)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}")

    print(f"✓ PI planning board: {result['path']}")
    print(
        f"  PI={result['pi']}  items={result['items']}  people={result['people']}"
        f"  PIs={result['pis']}  objectives={result['objectives']}"
        f"  bundle={result['bundle']} ({result['bundle_kb']} kB)"
    )

    if args.open:
        opener = {"Darwin": "open", "Windows": "start"}.get(platform.system(), "xdg-open")
        try:
            subprocess.run([opener, str(result["path"])], check=False)
        except Exception:  # pragma: no cover
            pass


if __name__ == "__main__":
    main()
