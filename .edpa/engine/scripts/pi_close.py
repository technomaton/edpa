#!/usr/bin/env python3
"""
EDPA PI Close — aggregate iteration results into PI-level summary.

Reads:
  - .edpa/iterations/PI-YYYY-M.{1,2,3}.yaml (closed iteration plans)
  - .edpa/reports/iteration-PI-YYYY-M.{1,2,3}/edpa_results.json (optional)
  - .edpa/backlog/features/*.yaml (to identify Features completed in PI)

Writes:
  - .edpa/reports/pi-PI-YYYY-M/pi_results.json
  - .edpa/reports/pi-PI-YYYY-M/summary.md

Usage:
    python3 .claude/edpa/scripts/pi_close.py --pi PI-2026-1
    python3 .claude/edpa/scripts/pi_close.py --pi PI-2026-1 --edpa-root .edpa
"""

# NOTE: ``_console`` (UTF-8 stdout reconfigure as an import side effect) is
# imported lazily inside ``main()``, NOT at module top — because ``mcp_server``
# imports :func:`close_pi` and must keep stdout pristine for JSON-RPC framing.
# Only the CLI opts into the UTF-8 reconfigure. (Mirrors create_pi.py.)
import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sp_rollup import iteration_sp  # noqa: E402


from _yaml_io import load_yaml as _shared_load_yaml  # noqa: E402


def load_yaml(path: Path):
    """Returns parsed dict for `.yaml`, or frontmatter+body dict for `.md`.

    Empty file → {}, missing/unparseable → None. (Shared loader, S-242.)
    """
    return _shared_load_yaml(path, empty_as_dict=True)


def load_json(path: Path):
    """Returns parsed content, None if missing/unparseable."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: load_json({path}) failed: {exc}", file=sys.stderr)
        return None


# PI-level id only (no ``.iteration`` suffix). Mirrors create_pi.PI_ID_RE.
PI_ID_RE = re.compile(r"^PI-\d{4}-\d{1,2}$")


def _write_yaml_atomic(path: Path, data: dict) -> None:
    """tmp + rename; ``safe_dump(sort_keys=False, allow_unicode=True)``.

    Local copy (mirrors create_pi._write_yaml_atomic) so this script stays
    runnable without importing the MCP layer.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".yaml", prefix=f".{path.stem}_",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False,
                           default_flow_style=False, allow_unicode=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def open_iterations(iteration_files):
    """Ids of child iterations whose status is not ``closed``.

    Lifecycle ``closed`` may live on the nested ``iteration.status`` or the
    top-level ``status`` (both written by edpa_iteration_close) — accept either.
    """
    open_ids = []
    for f in iteration_files:
        data = load_yaml(f) or {}
        it = data.get("iteration") or {}
        status = it.get("status") or data.get("status")
        if status != "closed":
            open_ids.append(it.get("id") or f.stem)
    return open_ids


def find_iterations(edpa_root: Path, pi_id: str):
    """Return sorted list of iteration YAMLs for given PI."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return []
    return sorted(iter_dir.glob(f"{pi_id}.*.yaml"))


def aggregate_iterations(iteration_files):
    """Aggregate planning + delivery metrics across iterations."""
    iterations = []
    total_planned = 0
    total_delivered = 0
    total_capacity = 0
    spillover_ids = []
    unplanned_ids = []

    # SP rollup derived from backlog item `js` (fallback when iteration YAMLs
    # carry no explicit planning.planned_sp / delivery.delivered_sp).
    sp = iteration_sp(iteration_files[0].resolve().parent.parent) if iteration_files else {}

    for f in iteration_files:
        data = load_yaml(f)
        if not data:
            continue
        it = data.get("iteration", {})
        planning = data.get("planning", {})
        delivery = data.get("delivery", {})

        derived = sp.get(it.get("id"), {})
        planned = planning.get("planned_sp") or derived.get("planned_sp", 0)
        delivered = delivery.get("delivered_sp") or derived.get("delivered_sp", 0)
        capacity = planning.get("capacity", 0) or 0
        predictability = (
            round(100 * delivered / planned, 1) if planned else None
        )

        total_planned += planned
        total_delivered += delivered
        total_capacity += capacity
        spillover_ids.extend(delivery.get("spillover", []) or [])
        unplanned_ids.extend(delivery.get("unplanned", []) or [])

        iterations.append({
            "id": it.get("id"),
            "status": it.get("status"),
            # PyYAML parses ISO dates into date objects; coerce to string
            # so the report serializes cleanly to JSON.
            "start_date": str(it["start_date"]) if it.get("start_date") else None,
            "end_date": str(it["end_date"]) if it.get("end_date") else None,
            "planned_sp": planned,
            "delivered_sp": delivered,
            "velocity": delivery.get("velocity", delivered),
            "predictability_pct": predictability,
            "spillover_count": len(delivery.get("spillover", []) or []),
            "unplanned_count": len(delivery.get("unplanned", []) or []),
        })

    avg_predictability = (
        round(100 * total_delivered / total_planned, 1) if total_planned else None
    )

    return {
        "iterations": iterations,
        "total_planned_sp": total_planned,
        "total_delivered_sp": total_delivered,
        "total_capacity_hours": total_capacity,
        "avg_predictability_pct": avg_predictability,
        "spillover_ids": spillover_ids,
        "unplanned_ids": unplanned_ids,
    }


def aggregate_engine_results(edpa_root: Path, pi_id: str, iteration_ids):
    """Sum per-person DerivedHours across iterations if engine results exist."""
    per_person = defaultdict(lambda: {"hours": 0.0, "iterations": []})
    any_results = False
    for it_id in iteration_ids:
        if not it_id:
            continue
        results_path = (
            edpa_root / "reports" / f"iteration-{it_id}" / "edpa_results.json"
        )
        data = load_json(results_path)
        if not data:
            continue
        any_results = True
        # edpa_results.json schema (engine.py:1587-1595): top-level `people`,
        # each entry keyed `id` + `total_derived` (D-32 — was reading the
        # non-existent `allocations`/`person`/`derived_hours`, summing zero).
        for entry in data.get("people", []) or []:
            person = entry.get("id")
            hours = entry.get("total_derived", 0) or 0
            if person:
                per_person[person]["hours"] += hours
                per_person[person]["iterations"].append(it_id)
    if not any_results:
        return None
    return [
        {"person": p, "derived_hours": round(v["hours"], 2),
         "iterations": v["iterations"]}
        for p, v in sorted(per_person.items())
    ]


def features_completed(edpa_root: Path, pi_id: str):
    """Features with iteration in this PI and status=Done."""
    feat_dir = edpa_root / "backlog" / "features"
    if not feat_dir.is_dir():
        return []
    done = []
    for f in sorted(feat_dir.glob("*.md")):
        data = load_yaml(f)
        if not data:
            continue
        it = data.get("iteration", "")
        if not it.startswith(pi_id):
            continue
        if data.get("status") == "Done":
            done.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", ""),
                "wsjf": data.get("wsjf"),
                "js": data.get("js"),
            })
    return done


def build_pi_results(edpa_root: Path, pi_id: str):
    iteration_files = find_iterations(edpa_root, pi_id)
    if not iteration_files:
        return None, f"No iterations found for {pi_id} in {edpa_root}/iterations/"

    agg = aggregate_iterations(iteration_files)
    iteration_ids = [it["id"] for it in agg["iterations"]]
    engine = aggregate_engine_results(edpa_root, pi_id, iteration_ids)
    done_features = features_completed(edpa_root, pi_id)

    return {
        "pi": pi_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "iterations": agg["iterations"],
        "summary": {
            "iteration_count": len(agg["iterations"]),
            "total_planned_sp": agg["total_planned_sp"],
            "total_delivered_sp": agg["total_delivered_sp"],
            "total_capacity_hours": agg["total_capacity_hours"],
            "avg_predictability_pct": agg["avg_predictability_pct"],
            "total_spillover": len(agg["spillover_ids"]),
            "total_unplanned": len(agg["unplanned_ids"]),
        },
        "spillover_ids": agg["spillover_ids"],
        "unplanned_ids": agg["unplanned_ids"],
        "features_completed": done_features,
        "per_person_hours": engine,
    }, None


def render_summary_md(result: dict) -> str:
    pi = result["pi"]
    s = result["summary"]
    lines = [
        f"# PI Summary — {pi}",
        "",
        f"_Generated: {result['generated_at']}_",
        "",
        "## Delivery",
        "",
        f"- Iterations closed: **{s['iteration_count']}**",
        f"- Planned SP: **{s['total_planned_sp']}**",
        f"- Delivered SP: **{s['total_delivered_sp']}**",
        f"- Average predictability: **{s['avg_predictability_pct']}%**",
        f"- Capacity hours: **{s['total_capacity_hours']}**",
        f"- Spillover: **{s['total_spillover']}**, Unplanned: **{s['total_unplanned']}**",
        "",
        "## Iterations",
        "",
        "| ID | Dates | Planned | Delivered | Predictability | Velocity |",
        "|---|---|---:|---:|---:|---:|",
    ]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _pi_loader import format_iteration_dates  # noqa: E402

    for it in result["iterations"]:
        lines.append(
            f"| {it['id']} | {format_iteration_dates(it)} | {it['planned_sp']} | "
            f"{it['delivered_sp']} | {it['predictability_pct']}% | {it['velocity']} |"
        )

    if result["features_completed"]:
        lines += ["", "## Features Completed", ""]
        for f in result["features_completed"]:
            lines.append(
                f"- **{f['id']}** — {f['title']} (JS={f.get('js')}, WSJF={f.get('wsjf')})"
            )

    if result["per_person_hours"]:
        lines += ["", "## Derived Hours by Person", "", "| Person | Hours |", "|---|---:|"]
        for p in result["per_person_hours"]:
            lines.append(f"| {p['person']} | {p['derived_hours']} |")

    lines.append("")
    return "\n".join(lines)


def close_pi(edpa_root, pi_id, *, force=False) -> dict:
    """Close a PI: require all child iterations closed, flip the PI-level
    ``pi.status`` to ``closed``, then (re)write the rollup report.

    ``edpa_root`` is the ``.edpa/`` directory; ``pi_id`` must be PI-level
    (``PI-YYYY-N``). Raises ``ValueError`` on a bad id, a PI with no child
    iterations, or a still-open iteration (unless ``force``) — callers map that
    to their own channel (MCP -> ``_err``, CLI -> stderr). Does NOT commit; the
    CLI/command layer owns the git commit, like create_pi. Returns a result
    dict carrying the rollup summary and what changed.
    """
    edpa_root = Path(edpa_root)
    if not isinstance(pi_id, str) or not PI_ID_RE.match(pi_id):
        raise ValueError(
            f"invalid PI id {pi_id!r}; expected PI-YYYY-N (e.g. PI-2026-1) "
            f"with no .iteration suffix")

    iteration_files = find_iterations(edpa_root, pi_id)
    if not iteration_files:
        raise ValueError(
            f"No iterations found for {pi_id} in {edpa_root}/iterations/")

    still_open = open_iterations(iteration_files)
    if still_open and not force:
        raise ValueError(
            f"{len(still_open)} iteration(s) still open: "
            f"{', '.join(still_open)}. Close them first "
            f"(/edpa:close-iteration) or pass force to roll up anyway.")

    # Flip the PI-level status. The PI metadata file is optional — without it
    # the PI list is derived from child iterations (_pi_loader), so the rollup
    # still works; there is simply no explicit status to set.
    pi_path = edpa_root / "iterations" / f"{pi_id}.yaml"
    pi_file_present = pi_path.is_file()
    status_changed = False
    if pi_file_present:
        pi_data = load_yaml(pi_path) or {}
        pi_block = pi_data.get("pi")
        if not isinstance(pi_block, dict):
            pi_block = {"id": pi_id}
        if pi_block.get("status") != "closed":
            pi_block["status"] = "closed"
            pi_data["pi"] = pi_block
            _write_yaml_atomic(pi_path, pi_data)
            status_changed = True

    result, err = build_pi_results(edpa_root, pi_id)
    if err:  # unreachable given the find_iterations guard, but stay defensive
        raise ValueError(err)
    out_dir = edpa_root / "reports" / f"pi-{pi_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "pi_results.json"
    summary_path = out_dir / "summary.md"
    results_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(render_summary_md(result), encoding="utf-8")

    return {
        "pi": pi_id,
        "status": "closed",
        "status_changed": status_changed,
        "pi_file_present": pi_file_present,
        "forced": bool(still_open),
        "open_iterations": still_open,
        "iteration_count": result["summary"]["iteration_count"],
        "results_path": str(results_path),
        "summary_path": str(summary_path),
        "summary": result["summary"],
    }


def main():
    try:  # best-effort UTF-8 stdio on legacy Windows consoles — CLI only
        import _console  # noqa: F401
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description="EDPA PI Close — aggregate PI metrics")
    parser.add_argument("--pi", required=True, help="PI ID (e.g., PI-2026-1)")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: <edpa-root>/reports/pi-<PI>). "
                             "Ignored with --close (canonical location is used).")
    parser.add_argument("--close", action="store_true",
                        help="Full close: require all child iterations closed, "
                             "flip pi.status to closed, roll up, then commit.")
    parser.add_argument("--force", action="store_true",
                        help="With --close, roll up even if some iterations are "
                             "still open (skips the guard).")
    parser.add_argument("--no-commit", action="store_true",
                        help="With --close, skip the git add/commit.")
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    if args.close:
        try:
            res = close_pi(args.edpa_root, args.pi, force=args.force)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        s = res["summary"]
        flip = ("status -> closed" if res["status_changed"]
                else "status already closed" if res["pi_file_present"]
                else "no PI metadata file")
        print(f"PI {args.pi} closed: {res['iteration_count']} iterations, "
              f"{s['total_delivered_sp']}/{s['total_planned_sp']} SP, "
              f"{s['avg_predictability_pct']}% predictability ({flip})")
        print(f"  -> {res['results_path']}")
        print(f"  -> {res['summary_path']}")
        if res["forced"]:
            print(f"WARNING: rolled up with {len(res['open_iterations'])} open "
                  f"iteration(s): {', '.join(res['open_iterations'])}",
                  file=sys.stderr)
        if not args.no_commit:
            paths = [res["results_path"], res["summary_path"]]
            if res["status_changed"]:
                paths.append(str(args.edpa_root / "iterations" / f"{args.pi}.yaml"))
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            try:
                from _auto_commit import maybe_commit
                if maybe_commit(paths, f"chore(pi): close {args.pi}",
                                root=str(args.edpa_root.parent)) == "skipped":
                    print("WARNING: auto-commit skipped (no git, or git "
                          "user.name/email unset) — commit manually.",
                          file=sys.stderr)
            except ImportError:
                print("WARNING: _auto_commit unavailable — commit manually.",
                      file=sys.stderr)
        return 0

    # default: rollup-only (no status flip, no guard) — back-compat path
    result, err = build_pi_results(args.edpa_root, args.pi)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    out_dir = args.output_dir or (args.edpa_root / "reports" / f"pi-{args.pi}")
    out_dir.mkdir(parents=True, exist_ok=True)

    results_path = out_dir / "pi_results.json"
    summary_path = out_dir / "summary.md"
    results_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(render_summary_md(result), encoding="utf-8")

    print(f"PI {args.pi}: {result['summary']['iteration_count']} iterations, "
          f"{result['summary']['total_delivered_sp']}/{result['summary']['total_planned_sp']} SP, "
          f"{result['summary']['avg_predictability_pct']}% predictability")
    print(f"  -> {results_path}")
    print(f"  -> {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
