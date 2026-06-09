#!/usr/bin/env python3
"""
EDPA Payroll Export — generate billable hours CSV from edpa_results.json.

Columns: iteration, person, name, role, team, hours, rate, currency, cost, code

Usage:
    python3 payroll_export.py --iteration PI-2026-1.1
    python3 payroll_export.py --iteration PI-2026-1.1 --currency EUR
    python3 payroll_export.py --iteration PI-2026-1.1 --output payroll.csv
"""
try:
    import _console  # noqa: F401
except ImportError:
    pass

import argparse
import csv
import io
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_results(edpa_root: Path, iteration_id: str) -> dict:
    path = edpa_root / "reports" / f"iteration-{iteration_id}" / "edpa_results.json"
    if not path.exists():
        raise FileNotFoundError(
            f"edpa_results.json not found at {path}\n"
            f"Run /edpa:engine {iteration_id} first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_people_config(edpa_root: Path) -> dict:
    """Return {person_id: {hourly_rate, team, currency}} from people.yaml."""
    path = edpa_root / "config" / "people.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("people") or []
    if isinstance(entries, dict):
        entries = list(entries.values())
    result = {}
    for p in entries:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if not pid:
            continue
        result[str(pid)] = {
            "hourly_rate": p.get("hourly_rate"),
            "team": p.get("team", ""),
            "currency": p.get("currency", ""),
        }
    return result


def load_project_code(edpa_root: Path) -> str:
    """Return registration/code from edpa.yaml (project.funding.registration or project.registration)."""
    path = edpa_root / "config" / "edpa.yaml"
    if not path.exists():
        return ""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    project = raw.get("project") or {}
    # Accept both project.registration (legacy) and project.funding.registration (v2.5+)
    reg = project.get("registration") or ""
    if not reg:
        reg = (project.get("funding") or {}).get("registration") or ""
    return str(reg)


def build_rows(results: dict, people_cfg: dict, project_code: str, currency: str) -> list[dict]:
    """Build one row per person from derived_reports + people config."""
    # Build team lookup from capacity_config (also present in edpa_results.json)
    cap_people = (results.get("capacity_config") or {}).get("people") or []
    team_by_id = {p["id"]: p.get("team", "") for p in cap_people if isinstance(p, dict)}

    iteration_id = results.get("iteration", "")
    rows = []
    for dr in results.get("derived_reports") or []:
        pid = dr.get("person", "")
        pcfg = people_cfg.get(pid, {})
        team = pcfg.get("team") or team_by_id.get(pid, "")
        rate = pcfg.get("hourly_rate")
        # Currency: per-person override → CLI flag → empty
        cur = pcfg.get("currency") or currency or ""
        hours = round(dr.get("total_derived", 0), 2)
        cost = round(hours * rate, 2) if rate is not None else ""
        rows.append({
            "iteration": iteration_id,
            "person": pid,
            "name": dr.get("name", ""),
            "role": dr.get("role", ""),
            "team": team,
            "hours": hours,
            "rate": rate if rate is not None else "",
            "currency": cur,
            "cost": cost,
            "code": project_code,
        })
    rows.sort(key=lambda r: (r["team"], r["person"]))
    return rows


COLUMNS = ["iteration", "person", "name", "role", "team", "hours", "rate", "currency", "cost", "code"]


def render_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def export(
    edpa_root: Path,
    iteration_id: str,
    currency: str = "",
    output: Path | None = None,
) -> dict:
    """Generate payroll CSV. Returns {"path": str, "rows": int, "total_hours": float}."""
    results = load_results(edpa_root, iteration_id)
    people_cfg = load_people_config(edpa_root)
    code = load_project_code(edpa_root)

    rows = build_rows(results, people_cfg, code, currency)
    csv_text = render_csv(rows)

    if output is None:
        out_dir = edpa_root / "reports" / f"iteration-{iteration_id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / f"payroll-{iteration_id}.csv"

    output.write_text(csv_text, encoding="utf-8")
    total_hours = round(sum(r["hours"] for r in rows), 2)
    return {"path": str(output), "rows": len(rows), "total_hours": total_hours}


def main() -> int:
    parser = argparse.ArgumentParser(description="EDPA Payroll Export")
    parser.add_argument("--iteration", required=True, help="Iteration ID (e.g. PI-2026-1.1)")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--currency", default="", help="Currency code (e.g. CZK, EUR, USD)")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path")
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    try:
        result = export(args.edpa_root, args.iteration, args.currency, args.output)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Payroll export: {result['rows']} people, {result['total_hours']}h total")
    print(f"  -> {result['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
