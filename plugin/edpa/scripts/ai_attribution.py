#!/usr/bin/env python3
"""
EDPA AI Attribution — human vs AI-agent delivery ratio.

Scans iteration backlog items for ``agent_contribution`` signals emitted by
``local_evidence.py`` whenever a commit carries a
``Co-Authored-By: Claude … <…@anthropic.com>`` trailer.  Produces:

  - per-item breakdown: which items had AI assistance and which agents
  - per-person breakdown: fraction of each person's items that were AI-assisted
  - iteration-wide ``ai_delivery_ratio`` (AI-assisted items / total items)

Output: ai_attribution.json  +  ai-attribution-<iteration>.md
        written to .edpa/reports/iteration-<id>/

Usage:
    python3 ai_attribution.py --iteration PI-2026-1.3
    python3 ai_attribution.py --iteration PI-2026-1.3 --edpa-root /path/to/.edpa
    python3 ai_attribution.py --iteration PI-2026-1.3 --json
"""
from __future__ import annotations

try:
    import _console  # noqa: F401
except ImportError:
    pass

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


_AGENT_SIGNAL_TYPE = "agent_contribution"
_DONE_STATUSES = {"done", "closed", "accepted", "complete", "completed"}


# ─── data loading ─────────────────────────────────────────────────────────────


def _load_md(path: Path) -> dict:
    """Load a frontmatter .md file; returns {} on failure."""
    parent = Path(__file__).resolve().parent
    sys.path.insert(0, str(parent))
    try:
        from _md_frontmatter import load_md  # noqa: E402
        return load_md(path) or {}
    except ImportError:
        return {}
    finally:
        sys.path.pop(0)


def load_iteration_items(edpa_root: Path, iteration_id: str) -> list[tuple[dict, Path]]:
    """Return (data, path) pairs for backlog items belonging to this iteration.

    Same iteration-scoping logic as ``engine.py::load_backlog_items``:
    Story/Defect → exact match; Feature → PI prefix match; Epic/Initiative → all Done.
    """
    backlog_dir = edpa_root / "backlog"
    if not backlog_dir.exists():
        return []

    type_dirs = {
        "stories": "Story",
        "defects": "Defect",
        "features": "Feature",
        "epics": "Epic",
        "initiatives": "Initiative",
    }
    pi_prefix = iteration_id.rsplit(".", 1)[0] if "." in iteration_id else iteration_id

    results = []
    for dir_name, item_type in type_dirs.items():
        td = backlog_dir / dir_name
        if not td.exists():
            continue
        for md_file in sorted(td.glob("*.md")):
            data = _load_md(md_file)
            if not data or not isinstance(data, dict):
                continue
            status = (data.get("status") or "").lower().replace("-", "_")
            if status not in _DONE_STATUSES:
                continue
            item_iter = data.get("iteration", "")
            if item_type in ("Story", "Defect"):
                if item_iter != iteration_id:
                    continue
            elif item_type == "Feature":
                if item_iter != pi_prefix and item_iter != iteration_id:
                    continue
            results.append((data, md_file))
    return results


# ─── core computation ─────────────────────────────────────────────────────────


def _evidence_list(data: dict) -> list[dict]:
    ev = data.get("evidence") or data.get("ci_signals") or []
    return [s for s in ev if isinstance(s, dict)]


def _ai_signals(evidence: list[dict]) -> list[dict]:
    return [s for s in evidence if s.get("type") == _AGENT_SIGNAL_TYPE]


def compute_ai_attribution(
    edpa_root: Path,
    iteration_id: str,
) -> dict:
    """Return the full AI attribution report dict."""
    items_raw = load_iteration_items(edpa_root, iteration_id)

    item_rows: list[dict] = []
    person_ai: dict[str, set[str]] = {}   # person_id → set of item IDs with AI
    person_all: dict[str, set[str]] = {}  # person_id → set of all item IDs
    all_agents: set[str] = set()

    for data, path in items_raw:
        item_id = data.get("id", path.stem)
        title = data.get("title", "")
        evidence = _evidence_list(data)
        ai_sigs = _ai_signals(evidence)
        human_sigs = [s for s in evidence if s.get("type") != _AGENT_SIGNAL_TYPE]
        agents = list(dict.fromkeys(
            s.get("agent", s.get("person", "")) for s in ai_sigs
        ))
        all_agents.update(agents)

        # Track per-person
        contributors = data.get("contributors") or []
        for c in contributors:
            if not isinstance(c, dict):
                continue
            pid = c.get("person")
            if not pid or pid.startswith("_"):
                continue
            person_all.setdefault(pid, set()).add(item_id)
            if ai_sigs:
                person_ai.setdefault(pid, set()).add(item_id)

        item_rows.append({
            "id": item_id,
            "title": title,
            "ai_signals": len(ai_sigs),
            "human_signals": len(human_sigs),
            "ai_assisted": len(ai_sigs) > 0,
            "agents": agents,
        })

    total_items = len(item_rows)
    ai_items = sum(1 for r in item_rows if r["ai_assisted"])
    ai_delivery_ratio = round(ai_items / total_items, 4) if total_items else 0.0

    by_person = []
    for pid in sorted(person_all):
        total = len(person_all[pid])
        ai_count = len(person_ai.get(pid, set()))
        by_person.append({
            "person_id": pid,
            "total_items": total,
            "ai_assisted_items": ai_count,
            "ai_ratio": round(ai_count / total, 4) if total else 0.0,
        })

    return {
        "iteration": iteration_id,
        "summary": {
            "total_items": total_items,
            "ai_assisted_items": ai_items,
            "ai_delivery_ratio": ai_delivery_ratio,
            "unique_agents": sorted(all_agents),
        },
        "items": item_rows,
        "by_person": by_person,
    }


def render_md(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# AI Attribution — {report['iteration']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total items | {s['total_items']} |",
        f"| AI-assisted items | {s['ai_assisted_items']} |",
        f"| AI delivery ratio | {s['ai_delivery_ratio']:.1%} |",
        f"| Agents detected | {', '.join(s['unique_agents']) or '—'} |",
        "",
        "## By Person",
        "",
        "| Person | Items | AI-assisted | AI ratio |",
        "|--------|-------|-------------|----------|",
    ]
    for p in report["by_person"]:
        lines.append(
            f"| {p['person_id']} | {p['total_items']} "
            f"| {p['ai_assisted_items']} | {p['ai_ratio']:.1%} |"
        )
    lines += [
        "",
        "## Item Detail",
        "",
        "| ID | Title | AI signals | Human signals | Agents |",
        "|----|-------|-----------|--------------|--------|",
    ]
    for item in report["items"]:
        agents = ", ".join(item["agents"]) or "—"
        lines.append(
            f"| {item['id']} | {item['title']} "
            f"| {item['ai_signals']} | {item['human_signals']} | {agents} |"
        )
    return "\n".join(lines) + "\n"


# ─── public entry point (called by MCP handler) ───────────────────────────────


def ai_attribution(
    edpa_root: Path,
    iteration_id: str,
) -> dict:
    """Compute and persist AI attribution report; return the report dict."""
    report = compute_ai_attribution(edpa_root, iteration_id)

    reports_dir = edpa_root / "reports" / f"iteration-{iteration_id}"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "ai_attribution.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    md_path = reports_dir / f"ai-attribution-{iteration_id}.md"
    md_path.write_text(render_md(report), encoding="utf-8")

    return report


# ─── CLI ──────────────────────────────────────────────────────────────────────


def _find_edpa_root() -> Path | None:
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        candidate = p / ".edpa"
        if candidate.is_dir():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute human vs AI-agent delivery ratio for an iteration."
    )
    parser.add_argument("--iteration", required=True,
                        help="Iteration ID, e.g. PI-2026-1.3")
    parser.add_argument("--edpa-root", default=None,
                        help="Path to .edpa/ directory (default: auto-detect)")
    parser.add_argument("--json", action="store_true",
                        help="Print JSON to stdout instead of a summary table")
    args = parser.parse_args()

    edpa_root_path = Path(args.edpa_root) if args.edpa_root else _find_edpa_root()
    if not edpa_root_path or not edpa_root_path.exists():
        print("ERROR: .edpa/ directory not found. Pass --edpa-root or run from project root.",
              file=sys.stderr)
        return 1

    report = ai_attribution(edpa_root_path, args.iteration)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    s = report["summary"]
    print(f"\nAI Attribution — {args.iteration}")
    print(f"  Items total      : {s['total_items']}")
    print(f"  AI-assisted      : {s['ai_assisted_items']}")
    print(f"  AI delivery ratio: {s['ai_delivery_ratio']:.1%}")
    if s["unique_agents"]:
        print(f"  Agents           : {', '.join(s['unique_agents'])}")
    if report["by_person"]:
        print("\nBy person:")
        for p in report["by_person"]:
            print(f"  {p['person_id']:20s}  {p['ai_assisted_items']}/{p['total_items']} "
                  f"items ({p['ai_ratio']:.0%} AI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
