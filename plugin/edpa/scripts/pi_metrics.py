#!/usr/bin/env python3
"""
EDPA PI Metrics — confidence & predictability trending.

Accumulates per-PI metrics:
  - planned vs delivered SP (predictability %)
  - average team confidence vote
  - objective completion ratio
  - average velocity per iteration

Reads:
  .edpa/iterations/PI-YYYY-M.yaml          — PI metadata (status, dates)
  .edpa/iterations/PI-YYYY-M.N.yaml        — per-iteration planned/delivered SP
  .edpa/pi-objectives/PI-YYYY-M.yaml       — team confidence votes + objectives
  .edpa/backlog/{stories,defects}/*.md     — via _sp_rollup for derived SP

Writes:
  .edpa/reports/pi-metrics.json
  .edpa/reports/pi-metrics.md

Usage:
    python3 pi_metrics.py
    python3 pi_metrics.py --window 5
    python3 pi_metrics.py --pi PI-2026-1
    python3 pi_metrics.py --json
"""

try:
    import _console  # noqa: F401  best-effort UTF-8 stdio on legacy Windows
except ImportError:
    pass

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sp_rollup import iteration_sp  # noqa: E402


# ---------------------------------------------------------------------------
# Sort helpers
# ---------------------------------------------------------------------------

def _pi_sort_key(pi_id: str):
    """Natural sort for PI-YYYY-M ids."""
    try:
        rest = pi_id.replace("PI-", "")
        year_part, pi_num = rest.split("-", 1)
        return (int(year_part), int(pi_num))
    except (ValueError, AttributeError):
        return (0, 0)


def _iter_sort_key(it_id: str):
    """Natural sort for PI-YYYY-M.N ids."""
    try:
        rest = it_id.replace("PI-", "")
        year_part, tail = rest.split("-", 1)
        pi_num, it_num = tail.split(".", 1)
        return (int(year_part), int(pi_num), int(it_num))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _is_iteration_file(stem: str) -> bool:
    """Return True if the filename looks like PI-YYYY-M.N (has a '.' part)."""
    return "." in stem.replace("PI-", "", 1)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_pi_list(edpa_root: Path) -> list[dict]:
    """Return sorted list of PI dicts from .edpa/iterations/PI-YYYY-M.yaml files."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return []
    pis = []
    for f in iter_dir.glob("*.yaml"):
        if _is_iteration_file(f.stem):
            continue  # skip per-iteration files
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        pi_block = data.get("pi", {})
        if not pi_block:
            continue
        pis.append(pi_block)
    return sorted(pis, key=lambda p: _pi_sort_key(p.get("id", "")))


def load_pi_iterations(edpa_root: Path, pi_id: str) -> list[dict]:
    """Return sorted list of iteration dicts belonging to a given PI."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return []
    iters = []
    for f in iter_dir.glob("*.yaml"):
        if not _is_iteration_file(f.stem):
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        it = data.get("iteration", {})
        if it.get("pi") != pi_id:
            continue
        it["_planning"] = data.get("planning", {})
        it["_delivery"] = data.get("delivery", {})
        iters.append(it)
    return sorted(iters, key=lambda it: _iter_sort_key(it.get("id", "")))


def load_pi_objectives(edpa_root: Path, pi_id: str) -> dict:
    """Return objectives dict from .edpa/pi-objectives/<pi_id>.yaml, or {}."""
    obj_file = edpa_root / "pi-objectives" / f"{pi_id}.yaml"
    if not obj_file.is_file():
        return {}
    return yaml.safe_load(obj_file.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _confidence_avg(objectives: dict) -> float | None:
    """Average confidence vote across all teams. Returns None if no votes."""
    teams = objectives.get("teams", {})
    votes = [
        v["confidence"]
        for v in teams.values()
        if isinstance(v, dict) and isinstance(v.get("confidence"), (int, float))
    ]
    return round(sum(votes) / len(votes), 2) if votes else None


def _confidence_votes(objectives: dict) -> dict:
    """Return {team: confidence_vote} mapping."""
    teams = objectives.get("teams", {})
    return {
        team: data["confidence"]
        for team, data in teams.items()
        if isinstance(data, dict) and isinstance(data.get("confidence"), (int, float))
    }


def _objective_counts(objectives: dict) -> tuple[int, int]:
    """Return (committed_total, committed_done) counting all teams."""
    teams = objectives.get("teams", {})
    total = done = 0
    for data in teams.values():
        if not isinstance(data, dict):
            continue
        for obj in data.get("committed", []):
            total += 1
            if str(obj.get("status", "")).lower() == "done":
                done += 1
    return total, done


def compute_pi_metrics(edpa_root: Path, pi_block: dict) -> dict:
    """Compute metrics for a single PI."""
    pi_id = pi_block["id"]
    iterations = load_pi_iterations(edpa_root, pi_id)
    objectives = load_pi_objectives(edpa_root, pi_id)
    sp_rollup = iteration_sp(edpa_root)

    total_iters = len(iterations)
    closed_iters = [it for it in iterations if it.get("status") == "closed"]
    active_iters = [it for it in iterations if it.get("status") == "active"]

    # Planned SP: sum planning.planned_sp; fall back to rollup
    planned_sp = 0
    for it in iterations:
        yaml_planned = it.get("_planning", {}).get("planned_sp") or 0
        rollup_planned = sp_rollup.get(it.get("id", ""), {}).get("planned_sp", 0)
        planned_sp += int(yaml_planned) or int(rollup_planned)

    # Delivered SP: sum delivery.delivered_sp from closed iterations; fall back to rollup
    delivered_sp = 0
    for it in closed_iters:
        yaml_delivered = it.get("_delivery", {}).get("delivered_sp") or 0
        rollup_delivered = sp_rollup.get(it.get("id", ""), {}).get("delivered_sp", 0)
        delivered_sp += int(yaml_delivered) or int(rollup_delivered)

    predictability = (
        round(delivered_sp / planned_sp * 100, 1) if planned_sp > 0 else None
    )
    avg_velocity = (
        round(delivered_sp / len(closed_iters), 1) if closed_iters else None
    )

    objectives_total, objectives_done = _objective_counts(objectives)
    confidence_avg = _confidence_avg(objectives)
    confidence_votes = _confidence_votes(objectives)

    return {
        "pi": pi_id,
        "status": pi_block.get("status", "unknown"),
        "start_date": str(pi_block.get("start_date", "")),
        "end_date": str(pi_block.get("end_date", "")),
        "iterations_total": total_iters,
        "iterations_closed": len(closed_iters),
        "iterations_active": len(active_iters),
        "planned_sp": planned_sp,
        "delivered_sp": delivered_sp,
        "predictability_pct": predictability,
        "avg_velocity": avg_velocity,
        "confidence_avg": confidence_avg,
        "confidence_votes": confidence_votes,
        "objectives_committed": objectives_total,
        "objectives_done": objectives_done,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(edpa_root: Path, window: int | None = None, pi_filter: str | None = None) -> dict:
    """Build the full pi-metrics report."""
    all_pis = load_pi_list(edpa_root)
    if pi_filter:
        all_pis = [p for p in all_pis if p.get("id") == pi_filter]
    if window and not pi_filter:
        all_pis = all_pis[-window:]

    metrics = [compute_pi_metrics(edpa_root, pi) for pi in all_pis]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": len(metrics),
        "pis": metrics,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_md(report: dict) -> str:
    pis = report.get("pis", [])
    if not pis:
        return "No PI data found.\n"

    lines = ["## PI Predictability & Confidence Trending\n"]
    lines.append(
        "| PI | Status | Planned SP | Delivered SP | Predictability | Avg Velocity "
        "| Confidence | Objectives |\n"
        "|---|---|---:|---:|---:|---:|---:|---|\n"
    )
    for m in pis:
        pred = f"{m['predictability_pct']:.1f}%" if m["predictability_pct"] is not None else "—"
        vel = f"{m['avg_velocity']:.1f}" if m["avg_velocity"] is not None else "—"
        conf_avg = f"{m['confidence_avg']:.1f}/5" if m["confidence_avg"] is not None else "—"
        obj = (
            f"{m['objectives_done']}/{m['objectives_committed']}"
            if m["objectives_committed"] > 0
            else "—"
        )
        lines.append(
            f"| {m['pi']} | {m['status']} | {m['planned_sp']} | {m['delivered_sp']} "
            f"| {pred} | {vel} | {conf_avg} | {obj} |\n"
        )

    # Confidence votes detail if present
    has_votes = any(m["confidence_votes"] for m in pis)
    if has_votes:
        lines.append("\n### Team Confidence Votes\n\n")
        all_teams: set[str] = set()
        for m in pis:
            all_teams.update(m["confidence_votes"].keys())
        sorted_teams = sorted(all_teams)
        header = "| PI | " + " | ".join(sorted_teams) + " |"
        sep = "|---|" + "---|" * len(sorted_teams)
        lines.append(header + "\n" + sep + "\n")
        for m in pis:
            row = f"| {m['pi']} |"
            for team in sorted_teams:
                v = m["confidence_votes"].get(team)
                row += f" {v}/5 |" if v is not None else " — |"
            lines.append(row + "\n")

    gen = report.get("generated_at", "")
    lines.append(f"\n*Generated: {gen}*\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def pi_metrics(edpa_root: Path, window: int | None = None, pi: str | None = None) -> dict:
    """Build and persist PI metrics report. Returns the report dict."""
    report = build_report(edpa_root, window=window, pi_filter=pi)
    out_dir = edpa_root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pi-metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "pi-metrics.md").write_text(render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="EDPA PI confidence & predictability trending")
    parser.add_argument("--edpa-root", default=".edpa", help="Path to .edpa directory")
    parser.add_argument("--window", type=int, default=5, help="Number of most-recent PIs to include")
    parser.add_argument("--pi", help="Limit to a single PI (e.g. PI-2026-1)")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args()

    edpa_root = Path(args.edpa_root)
    if not edpa_root.is_dir():
        print(f"ERROR: {edpa_root} not found", file=sys.stderr)
        return 1

    report = pi_metrics(edpa_root, window=args.window, pi=args.pi)

    if args.json_out:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_md(report))
        print(
            f"Written: {edpa_root}/reports/pi-metrics.json  "
            f"and  {edpa_root}/reports/pi-metrics.md",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
