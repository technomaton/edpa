#!/usr/bin/env python3
"""
EDPA Reports — batch generator for per-person timesheets and PI summaries.

Reads engine output from .edpa/reports/iteration-<ID>/edpa_results.json
and writes:
  - timesheet-<person_id>.md per person with derived hours > 0
  - timesheet-team.md aggregated team rollup
  - (optional) pi-summary-<PI-ID>.md when --pi <PI-ID> aggregates multiple
    iterations under the same PI prefix

Designed to be invoked directly (no LLM in the loop) so the
/edpa:reports skill can shell out to it instead of having Claude
hand-render each timesheet on every iteration close. The Markdown is
also stable enough to diff-check across reruns.

Usage:
    python3 .claude/edpa/scripts/reports.py PI-2026-1.1
    python3 .claude/edpa/scripts/reports.py --pi PI-2026-1
    python3 .claude/edpa/scripts/reports.py PI-2026-1.1 --edpa-root .edpa --out .edpa/reports
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# v1.11: role labels are derived at display time from signal types.
# The data store no longer carries `as: owner/key/...` per contributor;
# this mapping is the single canonical projection from signal type to
# role label, used only for human-readable rendering (timesheets, team
# rollup). Engine math doesn't see roles — only cw values.
SIGNAL_TO_ROLE = {
    "assignee": "owner",
    "pr_author": "key",
    "commit_author": "reviewer",
    "pr_reviewer": "reviewer",
    "issue_comment": "consulted",
}

# Manual /contribute directives default to "key" — they're explicit
# attributions written by the operator, typically to credit a person
# who isn't otherwise visible in commits/reviews.
_MANUAL_DEFAULT_ROLE = "key"

# Priority order for breaking ties when multiple signal types fire.
# Highest priority on the left: assignee dominates pr_author dominates
# commit_author etc. This matches the v1.10 role hierarchy that audit
# auditors are familiar with.
_ROLE_PRIORITY = ["owner", "key", "reviewer", "consulted"]


def _derive_role_from_signals(signal_types: list[str]) -> str:
    """Pick the highest-priority role implied by a list of signal types.

    Returns "—" when signal_types is empty (no contribution detected).
    Used in timesheet rendering to give each person a single role
    label per item, even when they fired multiple signals.
    """
    if not signal_types:
        return "—"
    roles_present = set()
    for s in signal_types:
        if s.startswith("manual:"):
            roles_present.add(_MANUAL_DEFAULT_ROLE)
        elif s in SIGNAL_TO_ROLE:
            roles_present.add(SIGNAL_TO_ROLE[s])
    for role in _ROLE_PRIORITY:
        if role in roles_present:
            return role
    return "—"


def _load_results(results_path: Path) -> dict:
    if not results_path.is_file():
        print(
            f"ERROR: engine results not found at {results_path}. "
            f"Run engine.py --iteration <ID> first.",
            file=sys.stderr,
        )
        sys.exit(2)
    with results_path.open(encoding="utf-8") as f:
        return json.load(f)


def _format_override_summary(override: dict | None, baseline) -> str:
    """Return a one-line human description of an iteration capacity
    override, or empty string when no override was applied. Used in
    both per-person timesheets and the team rollup column.

    `override` shape (from engine._resolve_capacity):
        {"capacity": <number>, "note": "<audit annotation>"}
    """
    if not override:
        return ""
    cap = override.get("capacity")
    note = (override.get("note") or "").strip()
    if cap is None:
        body = "no-op"
    else:
        try:
            base_n = float(baseline) if baseline is not None else None
            cap_n = float(cap)
        except (TypeError, ValueError):
            base_n = None
            cap_n = cap
        if base_n is not None:
            diff = cap_n - base_n
            if diff == 0:
                body = f"abs {cap_n:g}h ≡ baseline"
            else:
                sign = "+" if diff > 0 else ""
                body = f"abs {cap_n:g}h ({sign}{diff:g}h vs baseline {base_n:g}h)"
        else:
            body = f"abs {cap_n:g}h"
    return body + (f' ("{note}")' if note else "")


def _format_person_md(person: dict, results: dict) -> str:
    iteration = results.get("iteration", "?")
    methodology = results.get("methodology", "EDPA")
    capacity = person.get("capacity", 0)
    derived = person.get("total_derived", 0)
    items = person.get("items", []) or []
    invariant_ok = person.get("invariant_ok", True)
    baseline = person.get("capacity_baseline")
    override = person.get("capacity_override")

    if override:
        capacity_line = (
            f"- Capacity: **{capacity}h** "
            f"(baseline {baseline}h, override "
            f"{_format_override_summary(override, baseline)})"
        )
    else:
        capacity_line = f"- Capacity: **{capacity}h**"

    # `mode` field was retired in v1.14 (single calculation path). The
    # template no longer prints it — emitting `Mode: ?` on every timesheet
    # confused auditors who reasonably asked "what mode are we in?".
    lines = [
        f"# Timesheet — {person.get('name', person.get('id', '?'))} "
        f"({person.get('role', '?')})",
        "",
        f"- Iteration: **{iteration}**",
        f"- Methodology: **{methodology}**",
        capacity_line,
        f"- Derived: **{derived}h**",
        f"- Invariant: **{'OK' if invariant_ok else 'FAIL'}**",
        "",
    ]
    if items:
        # v1.11: include a derived "Role" column so timesheets remain
        # readable to auditors used to the Owner/Key/Reviewer/Consulted
        # hierarchy. The role is computed from signal types in the
        # `evidence` field — pure display-layer projection, no impact
        # on engine math.
        lines += [
            "| Item | Level | Role | JS | CW | Score | Ratio | Hours |",
            "|------|-------|------|----|----|-------|-------|-------|",
        ]
        for it in items:
            evidence = it.get("evidence") or []
            role = _derive_role_from_signals(evidence)
            lines.append(
                f"| {it.get('id','?')} | {it.get('level','?')} | "
                f"{role} | "
                f"{it.get('js',0)} | {float(it.get('cw',0)):.2f} | "
                f"{float(it.get('score',0)):.2f} | "
                f"{float(it.get('ratio',0))*100:.1f}% | "
                f"{float(it.get('hours',0)):.2f} |"
            )
    else:
        lines.append("_No items credited this iteration._")
    lines.append("")
    lines.append(f"**Total: {derived}h / {capacity}h capacity**")
    return "\n".join(lines) + "\n"


def _format_team_md(results: dict) -> str:
    iteration = results.get("iteration", "?")
    methodology = results.get("methodology", "EDPA")
    pf = results.get("planning_factor", 0.8)
    people = results.get("people", []) or []
    team_total = results.get("team_total", 0)
    capacity_total = sum(p.get("capacity", 0) for p in people)
    # Show the Override column only when at least one person had an
    # override applied — keeps reports clean for the common case where
    # everyone runs at baseline.
    has_overrides = any(p.get("capacity_override") for p in people)

    # See _format_person_md — `mode` retired in v1.14, no longer emitted.
    lines = [
        f"# Team Rollup — {iteration}",
        "",
        f"- Methodology: **{methodology}**",
        f"- Planning factor: **{pf}**",
        f"- Team capacity: **{capacity_total}h**",
        f"- Team derived: **{team_total}h**",
        "",
    ]
    if has_overrides:
        lines += [
            "| Person | Role | Capacity | Override | Derived | Items | Invariant |",
            "|--------|------|----------|----------|---------|-------|-----------|",
        ]
    else:
        lines += [
            "| Person | Role | Capacity | Derived | Items | Invariant |",
            "|--------|------|----------|---------|-------|-----------|",
        ]
    for p in people:
        invariant = "OK" if p.get("invariant_ok", True) else "FAIL"
        if has_overrides:
            override_cell = _format_override_summary(
                p.get("capacity_override"),
                p.get("capacity_baseline", p.get("capacity", 0))) or "—"
            lines.append(
                f"| {p.get('name', p.get('id', '?'))} | {p.get('role', '?')} | "
                f"{p.get('capacity', 0)}h | {override_cell} | "
                f"{p.get('total_derived', 0)}h | "
                f"{len(p.get('items', []) or [])} | {invariant} |"
            )
        else:
            lines.append(
                f"| {p.get('name', p.get('id', '?'))} | {p.get('role', '?')} | "
                f"{p.get('capacity', 0)}h | {p.get('total_derived', 0)}h | "
                f"{len(p.get('items', []) or [])} | {invariant} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_iteration_reports(edpa_root: Path, iteration_id: str,
                             out_dir: Path | None = None) -> dict:
    """Materialise per-person + team rollup MD for one iteration.

    Returns a summary dict suitable for printing and for PI aggregation.
    """
    results_path = edpa_root / "reports" / f"iteration-{iteration_id}" / "edpa_results.json"
    results = _load_results(results_path)

    if out_dir is None:
        out_dir = results_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for p in results.get("people", []) or []:
        pid = p.get("id") or p.get("name", "person").lower().replace(" ", "-")
        path = out_dir / f"timesheet-{pid}.md"
        path.write_text(_format_person_md(p, results), encoding="utf-8")
        written.append((pid, p.get("total_derived", 0), path))

    team_path = out_dir / "timesheet-team.md"
    team_path.write_text(_format_team_md(results), encoding="utf-8")

    return {
        "iteration": iteration_id,
        "people": written,
        "team": team_path,
        "results": results,
        "out_dir": out_dir,
    }


def write_pi_summary(edpa_root: Path, pi_id: str,
                     out_dir: Path | None = None) -> dict:
    """Aggregate all iteration-PI-X.Y/ results that share the PI prefix."""
    base = edpa_root / "reports"
    if not base.is_dir():
        print(f"ERROR: {base} not found", file=sys.stderr)
        sys.exit(2)

    pi_iterations = []
    for d in sorted(base.glob(f"iteration-{pi_id}.*")):
        if d.is_dir() and (d / "edpa_results.json").is_file():
            pi_iterations.append(d.name.replace("iteration-", ""))

    if not pi_iterations:
        print(
            f"ERROR: no iterations under {pi_id}.* found in {base}",
            file=sys.stderr,
        )
        sys.exit(2)

    if out_dir is None:
        out_dir = base / f"pi-{pi_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    person_totals: dict[str, dict] = {}  # pid → {name, role, capacity_sum, derived_sum, iters: [...]}
    iteration_results = []
    for iter_id in pi_iterations:
        results_path = base / f"iteration-{iter_id}" / "edpa_results.json"
        results = _load_results(results_path)
        iteration_results.append(results)
        for p in results.get("people", []) or []:
            pid = p.get("id") or p.get("name", "?")
            agg = person_totals.setdefault(pid, {
                "id": pid,
                "name": p.get("name", pid),
                "role": p.get("role", "?"),
                "capacity_sum": 0,
                "derived_sum": 0,
                "iters": [],
            })
            agg["capacity_sum"] += p.get("capacity", 0)
            agg["derived_sum"] += p.get("total_derived", 0)
            agg["iters"].append({
                "iteration": iter_id,
                "capacity": p.get("capacity", 0),
                "derived": p.get("total_derived", 0),
                "items": len(p.get("items", []) or []),
            })

    lines = [
        f"# PI Summary — {pi_id}",
        "",
        f"- Iterations: {', '.join(pi_iterations)}",
        f"- Methodology: **{iteration_results[0].get('methodology', 'EDPA')}**",
        "",
        "## Per-person totals",
        "",
        "| Person | Role | Capacity Σ | Derived Σ | Iterations |",
        "|--------|------|------------|-----------|------------|",
    ]
    for pid, agg in sorted(person_totals.items()):
        lines.append(
            f"| {agg['name']} | {agg['role']} | "
            f"{agg['capacity_sum']}h | {agg['derived_sum']}h | "
            f"{len(agg['iters'])} |"
        )

    lines += ["", "## Per-iteration breakdown", ""]
    for r in iteration_results:
        # `mode` retired in v1.14 — was producing "(None)" in every
        # bullet for the post-v1.14 single-path engine output.
        lines.append(
            f"- **{r.get('iteration')}**: "
            f"team_total={r.get('team_total', 0)}h, "
            f"invariants_passed={r.get('all_invariants_passed', '?')}"
        )

    summary_path = out_dir / f"pi-summary-{pi_id}.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "pi_id": pi_id,
        "iterations": pi_iterations,
        "summary": summary_path,
        "out_dir": out_dir,
    }


def main():
    parser = argparse.ArgumentParser(
        description="EDPA reports — generate per-person timesheets + PI summaries"
    )
    parser.add_argument(
        "iteration",
        nargs="?",
        help="Iteration ID (e.g. PI-2026-1.1). Required unless --pi is given.",
    )
    parser.add_argument(
        "--pi",
        help="PI ID (e.g. PI-2026-1). Aggregates all iterations under this PI.",
    )
    parser.add_argument(
        "--edpa-root",
        default=".edpa",
        help="Path to .edpa/ directory (default: .edpa)",
    )
    parser.add_argument(
        "--out",
        help="Override output directory (default: <edpa-root>/reports/iteration-<ID>/)",
    )
    args = parser.parse_args()

    edpa_root = Path(args.edpa_root)
    out_dir = Path(args.out) if args.out else None

    if args.pi:
        info = write_pi_summary(edpa_root, args.pi, out_dir=out_dir)
        print(
            f"✓ PI summary {args.pi} → {info['summary']} "
            f"({len(info['iterations'])} iteration(s) aggregated)"
        )
        return

    if not args.iteration:
        parser.error("either an iteration ID or --pi <PI-ID> is required")

    info = write_iteration_reports(edpa_root, args.iteration, out_dir=out_dir)
    iteration = info["iteration"]
    people = info["people"]
    print(f"✓ Reports for {iteration} → {info['out_dir']}")
    for pid, derived, path in people:
        print(f"  - {path.name:<32} {derived:6.1f}h")
    print(f"  - {info['team'].name:<32} (team rollup)")


if __name__ == "__main__":
    main()
