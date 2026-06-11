#!/usr/bin/env python3
"""
EDPA PI Completion Forecast — Monte-Carlo velocity forecast.

Fits a velocity distribution from the last N closed iterations and
simulates remaining-iteration delivery 1000×, returning p20/p50/p80
delivery bands and PI completion probability.

Usage:
    python3 forecast.py --pi PI-2026-2
    python3 forecast.py --pi PI-2026-2 --window 5 --simulations 2000
"""
try:
    import _console  # noqa: F401
except ImportError:
    pass

import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _iter_sort_key(it_id: str):
    try:
        rest = it_id.replace("PI-", "")
        year_part, tail = rest.split("-", 1)
        pi_num, it_num = tail.split(".", 1)
        return (int(year_part), int(pi_num), int(it_num))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def load_velocity_history(edpa_root: Path, window: int) -> list[float]:
    """Return the last `window` closed-iteration velocities (global history)."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return []
    records = []
    for f in iter_dir.glob("*.yaml"):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        it = data.get("iteration", {})
        if it.get("status") != "closed":
            continue
        # Skip PI-level files (no .N suffix)
        it_id = it.get("id", f.stem)
        if "." not in it_id:
            continue
        delivery = data.get("delivery", {})
        vel = delivery.get("velocity")
        if vel is None:
            vel = delivery.get("delivered_sp", 0)
        records.append((it_id, float(vel)))
    records.sort(key=lambda r: _iter_sort_key(r[0]))
    return [v for _, v in records[-window:]]


def load_pi_state(edpa_root: Path, pi_id: str) -> dict:
    """Return remaining_sp and remaining_iterations for the target PI."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return {"remaining_iterations": 0, "remaining_sp": 0, "total_iterations": 0,
                "closed_iterations": 0, "pi_exists": False}

    # Collect iterations belonging to this PI
    pi_iters = []
    for f in iter_dir.glob("*.yaml"):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        it = data.get("iteration") or data.get("pi", {})
        if not it:
            continue
        parent = it.get("pi") or it.get("id", "")
        it_id = it.get("id", f.stem)
        # Skip the PI-level file itself
        if "." not in it_id:
            continue
        if parent != pi_id:
            continue
        pi_iters.append({"id": it_id, "status": it.get("status", "planned")})

    if not pi_iters:
        return {"remaining_iterations": 0, "remaining_sp": 0, "total_iterations": 0,
                "closed_iterations": 0, "pi_exists": False}

    pi_iters.sort(key=lambda x: _iter_sort_key(x["id"]))
    closed = [i for i in pi_iters if i["status"] == "closed"]
    remaining = [i for i in pi_iters if i["status"] != "closed"]
    remaining_ids = {i["id"] for i in remaining}

    # Compute remaining SP from backlog items
    remaining_sp = _sum_remaining_sp(edpa_root, pi_id, remaining_ids)

    return {
        "pi_exists": True,
        "total_iterations": len(pi_iters),
        "closed_iterations": len(closed),
        "remaining_iterations": len(remaining),
        "remaining_sp": remaining_sp,
    }


def _sum_remaining_sp(edpa_root: Path, pi_id: str, remaining_iter_ids: set[str]) -> int:
    """Sum JS of items assigned to remaining iterations that are not Done."""
    backlog_dir = edpa_root / "backlog"
    if not backlog_dir.is_dir():
        return 0

    # PI prefix for iteration matching (e.g., "PI-2026-2")
    total = 0
    for type_dir in backlog_dir.iterdir():
        if not type_dir.is_dir():
            continue
        for f in type_dir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    continue
                end = content.find("---", 3)
                if end == -1:
                    continue
                fm = yaml.safe_load(content[3:end]) or {}
            except Exception:
                continue
            if fm.get("status") == "Done":
                continue
            item_iter = fm.get("iteration", "")
            js = fm.get("js", 0) or 0
            if not js:
                continue
            # Include if assigned to a remaining iteration or to the PI itself
            if item_iter in remaining_iter_ids or item_iter == pi_id:
                total += int(js)
    return total


# ---------------------------------------------------------------------------
# Monte-Carlo simulation
# ---------------------------------------------------------------------------

def run_monte_carlo(
    mean_v: float,
    std_v: float,
    remaining_iterations: int,
    simulations: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Simulate `simulations` PI completions. Returns sorted list of total delivery SP."""
    rng = random.Random(seed)
    totals = []
    for _ in range(simulations):
        total = 0.0
        for _ in range(remaining_iterations):
            # Velocity can't be negative
            v = max(0.0, rng.gauss(mean_v, std_v))
            total += v
        totals.append(total)
    totals.sort()
    return totals


def percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile (0–100) from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = (p / 100) * (len(sorted_values) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_values) - 1)
    frac = idx - lo
    return round(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac, 1)


# ---------------------------------------------------------------------------
# Main forecast entry point
# ---------------------------------------------------------------------------

def forecast_pi(
    edpa_root: Path,
    pi_id: str,
    window: int = 3,
    simulations: int = 1000,
    seed: int | None = None,
) -> dict:
    """Run a Monte-Carlo PI completion forecast. Returns a result dict."""
    velocities = load_velocity_history(edpa_root, window)
    if len(velocities) < 2:
        raise ValueError(
            f"Need at least 2 closed iterations for a forecast "
            f"(found {len(velocities)}). Close more iterations first."
        )

    mean_v = sum(velocities) / len(velocities)
    variance = sum((v - mean_v) ** 2 for v in velocities) / len(velocities)
    std_v = math.sqrt(variance)

    pi_state = load_pi_state(edpa_root, pi_id)
    if not pi_state["pi_exists"]:
        raise ValueError(f"PI {pi_id!r} has no iterations in .edpa/iterations/")

    remaining_iter = pi_state["remaining_iterations"]
    remaining_sp = pi_state["remaining_sp"]

    if remaining_iter == 0:
        return {
            "pi": pi_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "velocity_window": len(velocities),
            "velocity_mean": round(mean_v, 1),
            "velocity_std": round(std_v, 1),
            "remaining_iterations": 0,
            "remaining_sp": remaining_sp,
            "simulations": 0,
            "p20": 0, "p50": 0, "p80": 0,
            "completion_probability": 100.0 if remaining_sp == 0 else 0.0,
            "recommendation": "All iterations closed." if remaining_sp == 0
                              else "PI closed but undelivered work remains.",
        }

    totals = run_monte_carlo(mean_v, std_v, remaining_iter, simulations, seed)
    p20 = percentile(totals, 20)
    p50 = percentile(totals, 50)
    p80 = percentile(totals, 80)

    completed = sum(1 for t in totals if t >= remaining_sp)
    completion_prob = round(100 * completed / len(totals), 1)

    # Recommendation
    if remaining_sp == 0:
        rec = "No remaining work — PI is on track for a clean close."
    elif completion_prob >= 75:
        rec = f"On track. {completion_prob}% of simulations complete all remaining work."
    elif completion_prob >= 40:
        shortfall = round(remaining_sp - p50, 0)
        rec = (
            f"At risk. Suggest reducing scope by ~{shortfall:.0f} SP "
            f"(p50 shortfall) to reach ≥50% confidence."
        )
    else:
        shortfall = round(remaining_sp - p80, 0)
        rec = (
            f"High risk. Even p80 falls short by ~{max(0, shortfall):.0f} SP. "
            f"Consider significant scope cuts or adding capacity."
        )

    return {
        "pi": pi_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "velocity_window": len(velocities),
        "velocity_samples": velocities,
        "velocity_mean": round(mean_v, 1),
        "velocity_std": round(std_v, 1),
        "remaining_iterations": remaining_iter,
        "remaining_sp": remaining_sp,
        "simulations": simulations,
        "p20": p20,
        "p50": p50,
        "p80": p80,
        "completion_probability": completion_prob,
        "recommendation": rec,
    }


def render_md(result: dict) -> str:
    pi = result["pi"]
    lines = [
        f"# PI Completion Forecast: {pi}",
        "",
        f"_Generated: {result['generated_at']}_",
        "",
        f"**Velocity baseline** (last {result['velocity_window']} iterations): "
        f"avg={result['velocity_mean']} SP, σ={result['velocity_std']} SP",
        "",
        f"**Remaining:** {result['remaining_iterations']} iterations, "
        f"{result['remaining_sp']} SP not yet Done",
        "",
        "## Delivery bands ({:,} simulations)".format(result["simulations"]),
        "",
        "| Percentile | Projected SP | vs Remaining |",
        "|---|---:|---|",
    ]
    for label, key in [("p80 (likely)", "p80"), ("p50 (median)", "p50"), ("p20 (conservative)", "p20")]:
        sp = result[key]
        diff = sp - result["remaining_sp"]
        status = f"✓ +{diff:.0f}" if diff >= 0 else f"✗ {diff:.0f}"
        lines.append(f"| {label} | {sp} | {status} |")
    lines += [
        "",
        f"**Completion probability:** {result['completion_probability']}%",
        "",
        f"**Recommendation:** {result['recommendation']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="EDPA PI Completion Forecast")
    parser.add_argument("--pi", required=True, help="PI ID (e.g. PI-2026-2)")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--window", type=int, default=3,
                        help="Velocity history window (default: 3 iterations)")
    parser.add_argument("--simulations", type=int, default=1000,
                        help="Monte-Carlo simulations (default: 1000)")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON result to stdout")
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    try:
        result = forecast_pi(args.edpa_root, args.pi, args.window, args.simulations)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    md = render_md(result)
    print(md)

    out_dir = args.output_dir or (args.edpa_root / "reports" / "forecast")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"forecast-{args.pi}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / f"forecast-{args.pi}.md").write_text(md, encoding="utf-8")
    print(f"  -> {out_dir}/forecast-{args.pi}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
