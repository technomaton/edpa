#!/usr/bin/env python3
"""
EDPA capacity override — interactive helper for per-iteration `people:`
overrides (v1.9.0+ schema).

Edits .edpa/iterations/<iteration-id>.yaml to add/update/remove a
capacity override for a single person, validates the result, and
auto-commits with an audit message.

Usage:
    # Interactive add (prompts for person, hours, note):
    python3 capacity_override.py PI-2026-1.3 --add

    # Non-interactive add via flags:
    python3 capacity_override.py PI-2026-1.3 --add \\
        --person turyna --hours 44 --note "IP weekend deploy push"

    # List current overrides:
    python3 capacity_override.py PI-2026-1.3 --list

    # Remove an override (rare; audit-warning printed):
    python3 capacity_override.py PI-2026-1.3 --remove --person turyna

Closed iterations (`iteration.status: closed`) reject all mutations
to preserve the audit trail. Re-opening for retro corrections is a
separate workflow not handled here.
"""

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip3 install pyyaml --break-system-packages",
          file=sys.stderr)
    sys.exit(2)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    OK = "\033[32m"
    WARN = "\033[33m"
    ERR = "\033[31m"
    HEAD = "\033[38;5;147m"


def _isatty():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(t, code):
    return f"{code}{t}{C.RESET}" if _isatty() else t


def die(msg, code=1):
    print(f"{_c('✗', C.ERR)} {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg):
    print(f"{_c('·', C.DIM)} {msg}")


def ok(msg):
    print(f"{_c('✓', C.OK)} {msg}")


def warn(msg):
    print(f"{_c('⚠', C.WARN)} {msg}")


# -- File / config helpers ----------------------------------------------------


def find_edpa_root() -> Path:
    """Locate .edpa/ from cwd upward. Returns absolute path or dies."""
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / ".edpa"
        if candidate.is_dir():
            return candidate
    die("No .edpa/ directory found from current working directory upward.")


def load_iteration(edpa_root: Path, iteration_id: str) -> tuple[Path, dict]:
    path = edpa_root / "iterations" / f"{iteration_id}.yaml"
    if not path.is_file():
        die(f"Iteration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        die(f"Could not parse {path}: {e}")
    return path, data


def load_people(edpa_root: Path) -> dict:
    path = edpa_root / "config" / "people.yaml"
    if not path.is_file():
        die(f"people.yaml not found: {path}. Run /edpa:setup first.")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        die(f"Could not parse {path}: {e}")


def baseline_capacity(people_data: dict, person_id: str) -> float | None:
    for entry in (people_data.get("people") or []):
        if (entry.get("id") or "").strip() == person_id:
            cap = entry.get("capacity_per_iteration",
                            entry.get("capacity", None))
            return float(cap) if cap is not None else None
    return None


def known_person_ids(people_data: dict) -> list[str]:
    return [
        (e.get("id") or "").strip()
        for e in (people_data.get("people") or [])
        if (e.get("id") or "").strip()
    ]


def is_closed(iter_data: dict) -> bool:
    return (iter_data.get("iteration") or {}).get("status") == "closed"


def get_overrides(iter_data: dict) -> list[dict]:
    return iter_data.get("people") or []


# -- Mutations ----------------------------------------------------------------


def write_iteration(path: Path, data: dict):
    """Write iteration YAML. Comments at top of file will be lost — that's
    a known limitation of safe_load + safe_dump. The audit trail lives in
    git, not in YAML comments."""
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f,
            default_flow_style=False, allow_unicode=True,
            sort_keys=False, width=120,
        )


def upsert_override(iter_data: dict, person: str, hours: float, note: str):
    overrides = iter_data.setdefault("people", [])
    for entry in overrides:
        if (entry.get("id") or "").strip() == person:
            entry["capacity_per_iteration"] = hours
            if note:
                entry["note"] = note
            elif "note" in entry and not note:
                # Allow explicit clearing of note via --note ""
                entry["note"] = ""
            return "updated"
    new_entry = {"id": person, "capacity_per_iteration": hours}
    if note:
        new_entry["note"] = note
    overrides.append(new_entry)
    return "added"


def remove_override(iter_data: dict, person: str) -> bool:
    overrides = iter_data.get("people")
    if not overrides:
        return False
    before = len(overrides)
    iter_data["people"] = [
        e for e in overrides if (e.get("id") or "").strip() != person
    ]
    if not iter_data["people"]:
        iter_data.pop("people")
    return len(iter_data.get("people", [])) < before


def run_validator(iteration_path: Path) -> bool:
    """Run validate_syntax.py on the iteration file. Returns True on PASS."""
    script = Path(__file__).parent / "validate_syntax.py"
    if not script.is_file():
        warn("validate_syntax.py not found alongside this script — skipping post-write validation")
        return True
    rc = subprocess.run(
        [sys.executable, str(script), str(iteration_path)],
        capture_output=True, text=True,
    )
    if rc.returncode != 0:
        print(rc.stdout)
        print(rc.stderr, file=sys.stderr)
        return False
    return True


def git_commit(iteration_path: Path, msg: str, no_commit: bool):
    if no_commit:
        info(f"--no-commit: leaving {iteration_path} dirty in working tree")
        return
    rc = subprocess.run(
        ["git", "add", str(iteration_path)],
        capture_output=True, text=True,
    )
    if rc.returncode != 0:
        warn(f"git add failed: {rc.stderr.strip()}")
        return
    rc = subprocess.run(
        ["git", "commit", "-m", msg],
        capture_output=True, text=True,
    )
    if rc.returncode != 0:
        warn(f"git commit failed: {rc.stderr.strip()}")
        warn("File modified but not committed; commit manually.")
        return
    ok(f"Committed: {msg}")


# -- Interactive prompts ------------------------------------------------------


def _prompt(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{_c('?', C.HEAD)} {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        die("Aborted.")
    return ans or default


def prompt_person(known: list[str]) -> str:
    print(f"  Known person ids: {', '.join(known)}")
    while True:
        pid = _prompt("Person id")
        if not pid:
            print("  (empty input — try again or Ctrl-C to abort)")
            continue
        if pid in known:
            return pid
        print(f"  '{pid}' not in people.yaml. Pick from the list above.")


def parse_hours(raw: str, baseline: float | None) -> float:
    raw = raw.strip()
    if raw.startswith(("+", "-")) and baseline is None:
        die("Cannot use delta (+N / -N) — no baseline capacity in people.yaml")
    if raw.startswith("+"):
        return baseline + float(raw[1:])
    if raw.startswith("-"):
        return baseline - float(raw[1:])
    return float(raw)


# -- Sub-commands -------------------------------------------------------------


def cmd_list(iteration_id: str, iter_data: dict, people_data: dict):
    overrides = get_overrides(iter_data)
    if not overrides:
        info(f"{iteration_id} has no capacity overrides.")
        return
    print(f"{_c('Capacity overrides for ' + iteration_id, C.BOLD)}")
    for entry in overrides:
        pid = entry.get("id", "?")
        cap = entry.get("capacity_per_iteration", entry.get("capacity"))
        note = entry.get("note", "")
        baseline = baseline_capacity(people_data, pid)
        if baseline is not None and cap is not None:
            delta = cap - baseline
            sign = "+" if delta > 0 else ""
            diff = f"  (baseline {baseline:g}h, {sign}{delta:g}h)"
        else:
            diff = ""
        cap_str = f"{cap:g}h" if cap is not None else "(no capacity override)"
        line = f"  {_c(pid, C.BOLD)}: {cap_str}{diff}"
        if note:
            line += f"  — {_c(note, C.DIM)}"
        print(line)


def cmd_add(iteration_id: str, iteration_path: Path, iter_data: dict,
            people_data: dict, *, person: str | None, hours: str | None,
            note: str | None, no_commit: bool, non_interactive: bool):
    if is_closed(iter_data):
        die(f"{iteration_id} is closed (status: closed). Capacity overrides "
            f"on closed iterations are forbidden to preserve the audit trail.")

    known = known_person_ids(people_data)
    if not known:
        die("people.yaml has no people declared. Run /edpa:setup first.")

    # Resolve person
    if person is None:
        if non_interactive:
            die("--non-interactive requires --person")
        person = prompt_person(known)
    elif person not in known:
        die(f"--person '{person}' not in people.yaml "
            f"(known: {', '.join(known)})")

    baseline = baseline_capacity(people_data, person)
    if baseline is None:
        warn(f"{person} has no baseline capacity_per_iteration in "
             f"people.yaml — override will be the absolute value")

    # Resolve hours
    if hours is None:
        if non_interactive:
            die("--non-interactive requires --hours")
        if baseline is not None:
            print(f"  Baseline for {person}: {_c(f'{baseline:g}h', C.BOLD)}")
        hours = _prompt("Override hours (absolute, or +N / -N delta)")
    if not hours:
        die("hours is required")
    try:
        new_hours = parse_hours(hours, baseline)
    except ValueError:
        die(f"Could not parse hours: {hours!r}")
    if new_hours < 0:
        die(f"Hours must be >= 0 (got {new_hours:g})")

    if baseline is not None:
        delta = new_hours - baseline
        sign = "+" if delta >= 0 else ""
        diff_str = f"baseline {baseline:g}h → {new_hours:g}h ({sign}{delta:g}h)"
    else:
        diff_str = f"absolute {new_hours:g}h (no baseline)"
    print(f"  {_c('diff:', C.HEAD)} {diff_str}")

    # Resolve note
    if note is None:
        if non_interactive:
            note = ""  # explicit empty waiver in CI
        else:
            print("  Audit note (PTO / sick / overtime / onboarding ramp). "
                  "Empty = explicit waiver.")
            note = _prompt("Note", default="")

    # Mutate + write
    action = upsert_override(iter_data, person, new_hours, note)
    write_iteration(iteration_path, iter_data)
    ok(f"{action} override: {person} → {new_hours:g}h")

    # Validate
    if not run_validator(iteration_path):
        die("validate_syntax.py rejected the result. Edit "
            f"{iteration_path} manually to fix, or revert.")

    # Commit
    if note:
        msg = f"{iteration_id}: capacity override {person} -> {new_hours:g}h ({note})"
    else:
        msg = f"{iteration_id}: capacity override {person} -> {new_hours:g}h"
    git_commit(iteration_path, msg, no_commit)


def cmd_remove(iteration_id: str, iteration_path: Path, iter_data: dict,
               person: str, no_commit: bool):
    if is_closed(iter_data):
        die(f"{iteration_id} is closed. Cannot remove overrides.")
    if not person:
        die("--remove requires --person")
    if not remove_override(iter_data, person):
        die(f"No override found for {person} in {iteration_id}")
    warn(f"Removing override for {person} — auditor will see the deletion "
         f"in git history but no reason annotation. Confirm?")
    write_iteration(iteration_path, iter_data)
    ok(f"Removed override: {person}")
    if not run_validator(iteration_path):
        die("validate_syntax.py rejected result; revert manually.")
    git_commit(iteration_path,
               f"{iteration_id}: remove capacity override for {person}",
               no_commit)


# -- Main ---------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="EDPA capacity override — manage per-iteration `people:` overrides"
    )
    parser.add_argument("iteration", help="Iteration id (e.g., PI-2026-1.3)")

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true",
                         help="Show current overrides and exit")
    actions.add_argument("--add", action="store_true",
                         help="Add or update an override (interactive unless "
                              "--person + --hours given)")
    actions.add_argument("--remove", action="store_true",
                         help="Remove an override (requires --person)")

    parser.add_argument("--person", help="Person id from people.yaml")
    parser.add_argument("--hours",
                        help="Absolute (e.g., 28) or delta (e.g., +4, -12)")
    parser.add_argument("--note",
                        help="Audit note. Empty string is allowed as "
                             "explicit waiver.")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Never prompt; require all values via flags")
    parser.add_argument("--no-commit", action="store_true",
                        help="Skip git add/commit (file mutations only)")
    args = parser.parse_args()

    edpa_root = find_edpa_root()
    iteration_path, iter_data = load_iteration(edpa_root, args.iteration)
    people_data = load_people(edpa_root)

    if args.list:
        cmd_list(args.iteration, iter_data, people_data)
        return
    if args.add:
        cmd_add(args.iteration, iteration_path, iter_data, people_data,
                person=args.person, hours=args.hours, note=args.note,
                no_commit=args.no_commit, non_interactive=args.non_interactive)
        return
    if args.remove:
        cmd_remove(args.iteration, iteration_path, iter_data,
                   person=args.person or "", no_commit=args.no_commit)
        return


if __name__ == "__main__":
    main()
