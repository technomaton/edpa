#!/usr/bin/env python3
"""
EDPA Velocity Tracker — compute velocity trend across closed iterations.

Reads:
  - .edpa/iterations/*.yaml with status=closed

Writes:
  - .edpa/reports/velocity/velocity.json
  - .edpa/reports/velocity/velocity.md

Usage:
    python3 .claude/edpa/scripts/velocity.py
    python3 .claude/edpa/scripts/velocity.py --edpa-root .edpa
    python3 .claude/edpa/scripts/velocity.py --window 3
"""

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
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
from _sp_rollup import iteration_sp, predictability_pct  # noqa: E402


def iteration_sort_key(it_id: str):
    """Natural sort for PI-YYYY-M.N ids."""
    try:
        rest = it_id.replace("PI-", "")
        year_part, tail = rest.split("-", 1)
        pi_num, it_num = tail.split(".", 1)
        return (int(year_part), int(pi_num), int(it_num))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def load_closed_iterations(edpa_root: Path):
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return []
    sp = iteration_sp(edpa_root)  # SP rollup derived from backlog item `js`
    records = []
    for f in iter_dir.glob("*.yaml"):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        it = data.get("iteration", {})
        if it.get("status") != "closed":
            continue
        it_id = it.get("id", f.stem)
        planning = data.get("planning", {})
        delivery = data.get("delivery", {})
        derived = sp.get(it_id, {})
        # delivered_sp: explicit stamp wins, else the item-derived rollup.
        # planned_sp (D-60): ONLY the planning-time stamp counts — deriving it
        # from the current item→iteration assignment tracks scope as delivered
        # (incl. unplanned mid-iteration items), which made predictability
        # vacuously 100%. Missing stamp → null planned, n/a predictability.
        planned = planning.get("planned_sp")
        delivered = delivery.get("delivered_sp") or derived.get("delivered_sp", 0)
        records.append({
            "id": it_id,
            "pi": it.get("pi"),
            "start_date": str(it["start_date"]) if it.get("start_date") else None,
            "end_date": str(it["end_date"]) if it.get("end_date") else None,
            "planned_sp": planned,
            "delivered_sp": delivered,
            "velocity": delivery.get("velocity", delivered),
            "predictability_pct": predictability_pct(planned, delivered),
        })
    records.sort(key=lambda r: iteration_sort_key(r["id"]))
    return records


def compute_rolling_avg(velocities, window: int):
    if len(velocities) < window:
        return None
    return round(sum(velocities[-window:]) / window, 2)


def compute_trend(velocities, window: int):
    """Compare last window to previous window. Returns 'up', 'down', 'stable', or None."""
    if len(velocities) < window * 2:
        return None
    recent = sum(velocities[-window:]) / window
    prior = sum(velocities[-2 * window:-window]) / window
    if prior == 0:
        return None
    delta_pct = (recent - prior) / prior * 100
    if delta_pct > 10:
        return "up"
    if delta_pct < -10:
        return "down"
    return "stable"


def build_report(edpa_root: Path, window: int):
    records = load_closed_iterations(edpa_root)
    velocities = [r["velocity"] for r in records]
    avg = round(sum(velocities) / len(velocities), 2) if velocities else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "iteration_count": len(records),
        "average_velocity": avg,
        "rolling_avg": compute_rolling_avg(velocities, window),
        "trend": compute_trend(velocities, window),
        "iterations": records,
    }


def render_md(report: dict) -> str:
    lines = [
        "# EDPA Velocity Report",
        "",
        f"_Generated: {report['generated_at']}_",
        "",
        f"- Iterations analyzed: **{report['iteration_count']}**",
        f"- Average velocity: **{report['average_velocity']}** SP",
    ]
    if report["rolling_avg"] is not None:
        lines.append(f"- Rolling {report['window']}-iteration average: **{report['rolling_avg']}** SP")
    if report["trend"]:
        arrow = {"up": "↑", "down": "↓", "stable": "→"}[report["trend"]]
        lines.append(f"- Trend: **{arrow} {report['trend']}**")
    lines += [
        "",
        "## History",
        "",
        "| ID | Dates | Planned | Delivered | Predictability |",
        "|---|---|---:|---:|---:|",
    ]
    for r in report["iterations"]:
        planned = r["planned_sp"] if r["planned_sp"] is not None else "n/a"
        pred = (f"{r['predictability_pct']}%"
                if r["predictability_pct"] is not None else "n/a")
        lines.append(
            f"| {r['id']} | {r.get('dates','')} | {planned} | "
            f"{r['delivered_sp']} | {pred} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="EDPA Velocity Tracker")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--window", type=int, default=3,
                        help="Rolling average window (default: 3)")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    report = build_report(args.edpa_root, args.window)

    if report["iteration_count"] == 0:
        print("No closed iterations found.", file=sys.stderr)
        return 1

    out_dir = args.output_dir or (args.edpa_root / "reports" / "velocity")
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "velocity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "velocity.md").write_text(render_md(report), encoding="utf-8")

    print(f"Velocity: {report['iteration_count']} iterations, "
          f"avg={report['average_velocity']}, trend={report['trend'] or 'n/a'}")
    print(f"  -> {out_dir}/velocity.json")
    print(f"  -> {out_dir}/velocity.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
