#!/usr/bin/env python3
"""
EDPA Transition Detector — extract status transitions from git history.

Walks `git log -p` over .edpa/backlog/{features,epics,initiatives}/*.yaml,
identifies commits that changed a top-level `status:` field, and returns
structured transition events. Used by engine `--mode gates` to credit
work per status gate instead of only at final Done.

Usage:
    python3 .claude/edpa/scripts/transitions.py
    python3 .claude/edpa/scripts/transitions.py --since 2026-04-01 --until 2026-04-15
    python3 .claude/edpa/scripts/transitions.py --iteration PI-2026-1.1
    python3 .claude/edpa/scripts/transitions.py --format json
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


TRACKED_DIRS = {
    "features": "Feature",
    "epics": "Epic",
    "initiatives": "Initiative",
}

CZECH_MONTHS_DAYS = re.compile(r"(\d{1,2})\.(\d{1,2})\.")
DATES_FIELD = re.compile(
    r"^\s*(\d{1,2})\.(\d{1,2})\.[\s\u2013\u2014\-]+(\d{1,2})\.(\d{1,2})\.(\d{4})"
)
STATUS_LINE = re.compile(r"^([+-])status:\s*(\S+)")


def run_git(args, cwd: Path):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        # Treat "no commits yet" / "not a git repository" as empty history,
        # not as a hard error. Lets engine --mode gates run on freshly
        # initialized projects without crashing.
        benign = ("does not have any commits yet", "not a git repository",
                  "ambiguous argument 'HEAD'")
        if any(phrase in err for phrase in benign):
            return ""
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return result.stdout


def parse_iteration_dates(iter_yaml: Path):
    """Return (start_dt, end_dt) for an iteration YAML, both UTC.

    Prefers explicit ISO `start_date`/`end_date` fields if present.
    Falls back to parsing the Czech `dates: "D.M.-D.M.YYYY"` string.
    """
    data = yaml.safe_load(iter_yaml.read_text(encoding="utf-8")) or {}
    it = data.get("iteration", {})

    iso_start = it.get("start_date")
    iso_end = it.get("end_date")
    if iso_start and iso_end:
        return (
            datetime.fromisoformat(str(iso_start)).replace(tzinfo=timezone.utc),
            datetime.fromisoformat(str(iso_end)).replace(tzinfo=timezone.utc),
        )

    raw = it.get("dates", "")
    m = DATES_FIELD.search(raw)
    if not m:
        raise ValueError(f"{iter_yaml.name}: cannot parse dates '{raw}'")
    d1, m1, d2, m2, year = (int(x) for x in m.groups())
    start = datetime(year, m1, d1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year, m2, d2, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def find_iteration_for_timestamp(edpa_root: Path, ts: datetime):
    """Return iteration ID whose [start, end] window contains ts, or None."""
    iter_dir = edpa_root / "iterations"
    if not iter_dir.is_dir():
        return None
    for f in sorted(iter_dir.glob("*.yaml")):
        try:
            start, end = parse_iteration_dates(f)
        except (ValueError, KeyError):
            continue
        if start <= ts <= end:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            return data.get("iteration", {}).get("id", f.stem)
    return None


def detect_transitions(edpa_root: Path, since: datetime = None, until: datetime = None):
    """Walk git log over backlog YAMLs and yield status transitions.

    Returns list of dicts:
      {item_id, item_type, from_status, to_status,
       changed_at, changed_by, commit_hash, iteration_id (optional)}
    """
    repo_root = edpa_root.parent
    backlog_paths = []
    for sub in TRACKED_DIRS:
        p = edpa_root / "backlog" / sub
        if p.is_dir():
            backlog_paths.append(str(p.relative_to(repo_root)))

    if not backlog_paths:
        return []

    args = ["log", "--pretty=format:__COMMIT__|%H|%aI|%ae", "-p", "--unified=0", "--"]
    args.extend(backlog_paths)
    log = run_git(args, repo_root)

    transitions = []
    cur_commit = cur_ts = cur_author = None
    cur_file = None
    pending_minus = None

    for line in log.splitlines():
        if line.startswith("__COMMIT__|"):
            _, sha, ts, author = line.split("|", 3)
            cur_commit = sha
            cur_ts = datetime.fromisoformat(ts)
            cur_author = author
            cur_file = None
            pending_minus = None
            continue

        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            cur_file = parts[1] if len(parts) == 2 else None
            pending_minus = None
            continue

        if line.startswith("@@"):
            pending_minus = None
            continue

        m = STATUS_LINE.match(line)
        if not m or not cur_file:
            continue

        sign, value = m.group(1), m.group(2).strip().rstrip(",")
        if sign == "-":
            pending_minus = value
            continue

        # sign == "+": pair with previous minus (or treat as initial set)
        from_status = pending_minus
        to_status = value
        pending_minus = None

        if from_status == to_status:
            continue

        item_type = None
        for sub, type_name in TRACKED_DIRS.items():
            if f"backlog/{sub}/" in cur_file:
                item_type = type_name
                break
        if item_type is None:
            continue

        item_id = Path(cur_file).stem

        if since and cur_ts < since:
            continue
        if until and cur_ts > until:
            continue

        transitions.append({
            "item_id": item_id,
            "item_type": item_type,
            "from_status": from_status,
            "to_status": to_status,
            "changed_at": cur_ts.isoformat(),
            "changed_by": cur_author,
            "commit_hash": cur_commit,
        })

    transitions.sort(key=lambda t: t["changed_at"])
    return transitions


def annotate_with_iterations(edpa_root: Path, transitions):
    for t in transitions:
        ts = datetime.fromisoformat(t["changed_at"])
        t["iteration_id"] = find_iteration_for_timestamp(edpa_root, ts)
    return transitions


def main():
    parser = argparse.ArgumentParser(description="EDPA Transition Detector")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--since", help="ISO date YYYY-MM-DD (start of window)")
    parser.add_argument("--until", help="ISO date YYYY-MM-DD (end of window)")
    parser.add_argument("--iteration", help="Iteration ID — derive window from .edpa/iterations/<id>.yaml")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    since = until = None
    if args.iteration:
        iter_file = args.edpa_root / "iterations" / f"{args.iteration}.yaml"
        if not iter_file.is_file():
            print(f"ERROR: {iter_file} not found", file=sys.stderr)
            return 2
        since, until = parse_iteration_dates(iter_file)
    else:
        if args.since:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        if args.until:
            until = datetime.fromisoformat(args.until).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )

    transitions = detect_transitions(args.edpa_root, since=since, until=until)
    annotate_with_iterations(args.edpa_root, transitions)

    if args.format == "json":
        print(json.dumps({
            "window": {
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
            },
            "count": len(transitions),
            "transitions": transitions,
        }, indent=2, ensure_ascii=False))
    else:
        if not transitions:
            print("No transitions in window.")
            return 0
        print(f"Detected {len(transitions)} transition(s):")
        for t in transitions:
            iter_tag = f" [{t['iteration_id']}]" if t.get("iteration_id") else ""
            print(f"  {t['changed_at'][:19]}  {t['item_type']:<11} {t['item_id']:<10} "
                  f"{t['from_status'] or '∅':<14} -> {t['to_status']:<14} "
                  f"by {t['changed_by']}{iter_tag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
