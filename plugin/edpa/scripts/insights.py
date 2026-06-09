#!/usr/bin/env python3
"""
EDPA Insights — mid-iteration anomaly detection.

Reads edpa_results.json + backlog items + git history and surfaces four
classes of signal:

  capacity_overload   — person's derived_hours / capacity > threshold (default 110%)
  job_size_creep      — Story with js > threshold (default 8) in current iteration
  stalled_story       — Story in_progress with no commit touching its file for > N days
  critical_path_blocker — in-progress Story blocked by an unfinished dependency

Output: insights.json  +  insights-<iteration>.md  (written to the reports dir).

Usage:
    python3 insights.py --iteration PI-2026-1.3
    python3 insights.py --iteration PI-2026-1.3 --edpa-root /path/to/.edpa
    python3 insights.py --iteration PI-2026-1.3 --json
    python3 insights.py --iteration PI-2026-1.3 --overload-threshold 1.05 --stale-days 3
"""
from __future__ import annotations

try:
    import _console  # noqa: F401
except ImportError:
    pass

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OVERLOAD_THRESHOLD = 1.10  # 110% of capacity
DEFAULT_JS_THRESHOLD = 8
DEFAULT_STALE_DAYS = 5

_IN_PROGRESS_STATUSES = {"in_progress", "in progress", "active", "started"}
_DONE_STATUSES = {"done", "closed", "accepted", "complete", "completed"}

SEVERITY_LEVELS = ("critical", "warning", "info")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(edpa_root: Path, iteration_id: str) -> dict:
    path = edpa_root / "reports" / f"iteration-{iteration_id}" / "edpa_results.json"
    if not path.exists():
        raise FileNotFoundError(
            f"edpa_results.json not found at {path}\n"
            f"Run the engine for {iteration_id} first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def load_backlog_item(edpa_root: Path, item_id: str) -> tuple[dict, Path | None]:
    """Return (frontmatter_dict, file_path) for a backlog item by ID."""
    backlog = edpa_root / "backlog"
    if not backlog.is_dir():
        return {}, None
    for type_dir in backlog.iterdir():
        if not type_dir.is_dir():
            continue
        candidate = type_dir / f"{item_id}.md"
        if candidate.exists():
            return _parse_frontmatter(candidate.read_text(encoding="utf-8")), candidate
    return {}, None


def load_iteration_items(edpa_root: Path, iteration_id: str) -> list[tuple[dict, Path]]:
    """Return all backlog items assigned to the given iteration."""
    results = []
    backlog = edpa_root / "backlog"
    if not backlog.is_dir():
        return results
    for type_dir in backlog.iterdir():
        if not type_dir.is_dir():
            continue
        for md_file in type_dir.glob("*.md"):
            fm = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
            if fm.get("iteration") == iteration_id:
                results.append((fm, md_file))
    return results


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_last_commit_epoch(file_path: Path) -> int | None:
    """Return Unix timestamp of last git commit touching file_path, or None."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(file_path)],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        return int(out) if out else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _days_since(epoch: int, now_epoch: float) -> float:
    return (now_epoch - epoch) / 86400.0


# ---------------------------------------------------------------------------
# Anomaly detectors
# ---------------------------------------------------------------------------

def detect_capacity_overload(
    derived_reports: list[dict],
    threshold: float = DEFAULT_OVERLOAD_THRESHOLD,
) -> list[dict]:
    """Persons whose derived_hours / capacity > threshold."""
    anomalies = []
    for r in derived_reports:
        capacity = r.get("capacity") or 0
        derived = r.get("total_derived") or 0
        if capacity <= 0:
            continue
        ratio = derived / capacity
        if ratio > threshold:
            anomalies.append({
                "type": "capacity_overload",
                "severity": "critical" if ratio > 1.20 else "warning",
                "person": r["person"],
                "name": r.get("name", r["person"]),
                "derived_hours": round(derived, 2),
                "capacity": round(capacity, 2),
                "overload_pct": round((ratio - 1.0) * 100, 1),
                "message": (
                    f"{r.get('name', r['person'])} is overloaded: "
                    f"{round(derived, 1)}h derived / {round(capacity, 1)}h capacity "
                    f"= {round(ratio * 100, 1)}%"
                ),
            })
    return anomalies


def detect_job_size_creep(
    iteration_items: list[tuple[dict, Path]],
    js_threshold: int = DEFAULT_JS_THRESHOLD,
) -> list[dict]:
    """Stories in the iteration with js > threshold."""
    anomalies = []
    for fm, path in iteration_items:
        if fm.get("type", "").lower() != "story":
            continue
        js = fm.get("js") or fm.get("job_size") or 0
        if js > js_threshold:
            anomalies.append({
                "type": "job_size_creep",
                "severity": "warning",
                "item": fm.get("id", path.stem),
                "title": fm.get("title", ""),
                "js": js,
                "threshold": js_threshold,
                "message": (
                    f"{fm.get('id', path.stem)} \"{fm.get('title', '')}\" "
                    f"has JS={js} (> {js_threshold}) — consider splitting"
                ),
            })
    return anomalies


def detect_stalled_stories(
    iteration_items: list[tuple[dict, Path]],
    stale_days: int = DEFAULT_STALE_DAYS,
    now_epoch: float | None = None,
) -> list[dict]:
    """Stories in_progress with no git activity for > stale_days."""
    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()
    anomalies = []
    for fm, file_path in iteration_items:
        if fm.get("type", "").lower() != "story":
            continue
        status = (fm.get("status") or "").lower().replace("-", "_").replace(" ", "_")
        if status not in _IN_PROGRESS_STATUSES:
            continue
        last_commit = _git_last_commit_epoch(file_path)
        if last_commit is None:
            continue
        days_idle = _days_since(last_commit, now_epoch)
        if days_idle > stale_days:
            anomalies.append({
                "type": "stalled_story",
                "severity": "warning",
                "item": fm.get("id", file_path.stem),
                "title": fm.get("title", ""),
                "days_idle": round(days_idle, 1),
                "stale_days": stale_days,
                "last_commit_epoch": last_commit,
                "message": (
                    f"{fm.get('id', file_path.stem)} \"{fm.get('title', '')}\" "
                    f"in_progress but no commit for {round(days_idle, 1)} days "
                    f"(threshold: {stale_days}d)"
                ),
            })
    return anomalies


def detect_critical_path_blockers(
    iteration_items: list[tuple[dict, Path]],
    edpa_root: Path,
) -> list[dict]:
    """In-progress Stories blocked by an unfinished dependency."""
    anomalies = []
    for fm, file_path in iteration_items:
        if fm.get("type", "").lower() != "story":
            continue
        status = (fm.get("status") or "").lower().replace("-", "_").replace(" ", "_")
        if status in _DONE_STATUSES:
            continue
        deps = fm.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        for dep_id in deps:
            dep_fm, _ = load_backlog_item(edpa_root, dep_id)
            dep_status = (dep_fm.get("status") or "").lower().replace("-", "_").replace(" ", "_")
            if dep_status not in _DONE_STATUSES:
                anomalies.append({
                    "type": "critical_path_blocker",
                    "severity": "critical",
                    "item": fm.get("id", file_path.stem),
                    "title": fm.get("title", ""),
                    "blocked_by": dep_id,
                    "blocked_by_status": dep_fm.get("status", "unknown"),
                    "message": (
                        f"{fm.get('id', file_path.stem)} \"{fm.get('title', '')}\" "
                        f"is blocked by {dep_id} (status: {dep_fm.get('status', 'unknown')})"
                    ),
                })
    return anomalies


# ---------------------------------------------------------------------------
# Aggregate + render
# ---------------------------------------------------------------------------

def compute_insights(
    edpa_root: Path,
    iteration_id: str,
    overload_threshold: float = DEFAULT_OVERLOAD_THRESHOLD,
    js_threshold: int = DEFAULT_JS_THRESHOLD,
    stale_days: int = DEFAULT_STALE_DAYS,
    now_epoch: float | None = None,
) -> dict:
    results = load_results(edpa_root, iteration_id)
    iteration_items = load_iteration_items(edpa_root, iteration_id)

    anomalies: list[dict] = []
    anomalies += detect_capacity_overload(
        results.get("derived_reports", []), overload_threshold,
    )
    anomalies += detect_job_size_creep(iteration_items, js_threshold)
    anomalies += detect_stalled_stories(iteration_items, stale_days, now_epoch)
    anomalies += detect_critical_path_blockers(iteration_items, edpa_root)

    by_severity = {s: [a for a in anomalies if a["severity"] == s] for s in SEVERITY_LEVELS}

    return {
        "iteration": iteration_id,
        "anomaly_count": len(anomalies),
        "critical": len(by_severity["critical"]),
        "warnings": len(by_severity["warning"]),
        "anomalies": anomalies,
        "thresholds": {
            "overload_pct": round((overload_threshold - 1.0) * 100),
            "js_max": js_threshold,
            "stale_days": stale_days,
        },
    }


_SEVERITY_BADGE = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


def render_md(report: dict) -> str:
    lines = [
        f"# EDPA Insights — {report['iteration']}",
        "",
        f"**{report['anomaly_count']} anomalies** "
        f"({report['critical']} critical, {report['warnings']} warnings)",
        "",
    ]

    thresholds = report.get("thresholds", {})
    lines += [
        "| Threshold | Value |",
        "|-----------|-------|",
        f"| Capacity overload | > {thresholds.get('overload_pct', 10)}% |",
        f"| Job size creep | JS > {thresholds.get('js_max', 8)} |",
        f"| Stalled story | > {thresholds.get('stale_days', 5)} days idle |",
        "",
    ]

    if not report["anomalies"]:
        lines.append("_No anomalies detected._")
        return "\n".join(lines)

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for a in report["anomalies"]:
        by_type.setdefault(a["type"], []).append(a)

    section_titles = {
        "capacity_overload": "Capacity Overload",
        "job_size_creep": "Job Size Creep",
        "stalled_story": "Stalled Stories",
        "critical_path_blocker": "Critical Path Blockers",
    }

    for atype, title in section_titles.items():
        items = by_type.get(atype, [])
        if not items:
            continue
        lines += [f"## {title}", ""]
        for a in items:
            badge = _SEVERITY_BADGE.get(a["severity"], "")
            lines.append(f"- {badge} {a['message']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def insights(
    edpa_root: Path,
    iteration_id: str,
    overload_threshold: float = DEFAULT_OVERLOAD_THRESHOLD,
    js_threshold: int = DEFAULT_JS_THRESHOLD,
    stale_days: int = DEFAULT_STALE_DAYS,
    now_epoch: float | None = None,
) -> dict:
    report = compute_insights(
        edpa_root, iteration_id,
        overload_threshold=overload_threshold,
        js_threshold=js_threshold,
        stale_days=stale_days,
        now_epoch=now_epoch,
    )

    out_dir = edpa_root / "reports" / f"iteration-{iteration_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "insights.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / f"insights-{iteration_id}.md").write_text(
        render_md(report) + "\n",
        encoding="utf-8",
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EDPA Insights — mid-iteration anomaly detection",
    )
    parser.add_argument("--iteration", required=True, help="Iteration ID, e.g. PI-2026-1.3")
    parser.add_argument("--edpa-root", default=".edpa", help="Path to .edpa directory")
    parser.add_argument(
        "--overload-threshold", type=float, default=DEFAULT_OVERLOAD_THRESHOLD,
        help=f"Capacity overload ratio (default {DEFAULT_OVERLOAD_THRESHOLD})",
    )
    parser.add_argument(
        "--js-threshold", type=int, default=DEFAULT_JS_THRESHOLD,
        help=f"Job size above which creep is flagged (default {DEFAULT_JS_THRESHOLD})",
    )
    parser.add_argument(
        "--stale-days", type=int, default=DEFAULT_STALE_DAYS,
        help=f"Days of git inactivity to flag as stalled (default {DEFAULT_STALE_DAYS})",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args()

    edpa_root = Path(args.edpa_root)

    try:
        report = insights(
            edpa_root=edpa_root,
            iteration_id=args.iteration,
            overload_threshold=args.overload_threshold,
            js_threshold=args.js_threshold,
            stale_days=args.stale_days,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        out_dir = edpa_root / "reports" / f"iteration-{args.iteration}"
        print(render_md(report))
        print(f"\nWritten: {out_dir}/insights.json + insights-{args.iteration}.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
