#!/usr/bin/env python3
"""Semi-automatic resolution of EDPA ID collisions (V2 Layer 7).

Companion to ``validate_ids.py``. When pre-push detects that a local
ID also exists on the remote, this helper:

1. Fetches the remote to refresh upstream view
2. Computes ``max_remote_id_per_type`` from ``origin/<branch>``
3. For each local collision: renumbers the new ID to one above the max
4. Renames the file, rewrites its ``id:`` field, and updates every
   ``parent:`` reference in the rest of the local backlog
5. Bumps ``.edpa/config/id_counters.yaml`` to the new max

Always interactive: prints the planned rename and waits for ``y``
before applying. Use ``--apply`` to skip the prompt (CI / scripted use).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from id_counter import (  # noqa: E402
        TYPE_DIRS, TYPE_PREFIX,
        _read_counter, _scan_fs_max, _write_counter_atomic,
    )
finally:
    sys.path.pop(0)

DIR_TO_TYPE = {v: k for k, v in TYPE_DIRS.items()}
PREFIX_TO_TYPE = {v: k for k, v in TYPE_PREFIX.items()}

_BACKLOG_PATH_RE = re.compile(r"\.edpa/backlog/([^/]+)/([A-Z]{1,3}-\d{1,9})\.md$")
_PARENT_FIELD_RE = re.compile(r"^(parent:\s*)([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)
_ID_FIELD_RE = re.compile(r"^(id:\s*)([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd),
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _find_repo_root() -> Path | None:
    out = _git(["rev-parse", "--show-toplevel"], cwd=Path.cwd())
    return Path(out.strip()) if out else None


def _list_remote_backlog(repo_root: Path, ref: str) -> list[tuple[str, str]]:
    """List (path, id) tuples for files under .edpa/backlog at ref."""
    out = _git(
        ["ls-tree", "-r", "--name-only", ref, ".edpa/backlog"], cwd=repo_root,
    )
    result = []
    for line in (out or "").splitlines():
        m = _BACKLOG_PATH_RE.search(line)
        if m:
            result.append((line, m.group(2)))
    return result


def _all_local_files(repo_root: Path) -> list[Path]:
    backlog = repo_root / ".edpa" / "backlog"
    if not backlog.exists():
        return []
    return list(backlog.glob("*/*.md"))


def _max_per_type(items: list[tuple[str, str]]) -> dict[str, int]:
    """For a list of (path, id), return max numeric suffix per type."""
    max_by_type: dict[str, int] = {}
    for _path, item_id in items:
        prefix, num_str = item_id.split("-", 1)
        try:
            num = int(num_str)
        except ValueError:
            continue
        item_type = PREFIX_TO_TYPE.get(prefix)
        if not item_type:
            continue
        if num > max_by_type.get(item_type, 0):
            max_by_type[item_type] = num
    return max_by_type


def _local_items(repo_root: Path) -> list[tuple[Path, str, str]]:
    """Return (file_path, id, type) for every local backlog file."""
    result = []
    for f in _all_local_files(repo_root):
        m = _BACKLOG_PATH_RE.search(str(f.relative_to(repo_root)))
        if not m:
            continue
        dir_name, item_id = m.group(1), m.group(2)
        item_type = DIR_TO_TYPE.get(dir_name)
        if item_type:
            result.append((f, item_id, item_type))
    return result


def find_collisions(repo_root: Path, remote: str = "origin") -> list[dict]:
    """Return collisions: files ADDED on the local branch whose IDs already exist upstream.

    Local-only files (added since merge-base with upstream) are the only
    renumber candidates — modifications of existing items must be resolved
    via merge, not renumbering.

    Returns ``[{old_id, new_id, file, type, upstream_path}]``.
    """
    branch_out = _git(["symbolic-ref", "--short", "HEAD"], cwd=repo_root)
    branch = (branch_out or "main").strip() or "main"

    _git(["fetch", "--quiet", remote], cwd=repo_root)
    ref = f"{remote}/{branch}"
    # If branch isn't on remote yet, fall back to remote default ref.
    if not _git(["rev-parse", "--verify", ref], cwd=repo_root):
        ref = f"{remote}/HEAD"

    base_out = _git(["merge-base", "HEAD", ref], cwd=repo_root)
    base = (base_out or "").strip()
    if not base:
        return []  # no shared history, can't compute additions

    # Files added on local since merge-base
    added_out = _git(
        ["diff", "--name-only", "--diff-filter=A", base, "HEAD"],
        cwd=repo_root,
    )
    added_paths = [p for p in (added_out or "").splitlines() if p]

    # Upstream IDs (any path under .edpa/backlog)
    remote_files = _list_remote_backlog(repo_root, ref)
    remote_ids = {item_id for _path, item_id in remote_files}
    remote_max = _max_per_type(remote_files)

    # Local max — covers files added in earlier commits the user has
    # already locally numbered.
    local = _local_items(repo_root)
    local_max = _max_per_type([
        (str(p.relative_to(repo_root)), i) for p, i, _t in local
    ])
    working_max = {
        t: max(remote_max.get(t, 0), local_max.get(t, 0))
        for t in TYPE_PREFIX
    }

    collisions = []
    for path in added_paths:
        m = _BACKLOG_PATH_RE.search(path)
        if not m:
            continue
        dir_name, item_id = m.group(1), m.group(2)
        item_type = DIR_TO_TYPE.get(dir_name)
        if not item_type:
            continue
        if item_id not in remote_ids:
            continue
        prefix = TYPE_PREFIX[item_type]
        working_max[item_type] += 1
        new_id = f"{prefix}-{working_max[item_type]}"
        upstream_path = next(
            (p for p, i in remote_files if i == item_id), None,
        )
        collisions.append({
            "type": item_type,
            "old_id": item_id,
            "new_id": new_id,
            "file": repo_root / path,
            "upstream_path": upstream_path,
        })
    return collisions


def _rewrite_id(file_path: Path, new_id: str) -> None:
    content = file_path.read_text(encoding="utf-8")
    new_content, n = _ID_FIELD_RE.subn(
        lambda m: f"{m.group(1)}{new_id}", content, count=1,
    )
    if n == 0:
        raise RuntimeError(f"{file_path}: no `id:` field to rewrite")
    file_path.write_text(new_content, encoding="utf-8")


def _rewrite_parent_refs(repo_root: Path, old_id: str, new_id: str) -> list[Path]:
    """Replace parent: old_id → new_id in every local backlog file."""
    updated = []
    for f in _all_local_files(repo_root):
        text = f.read_text(encoding="utf-8")
        if old_id not in text:
            continue
        new_text, n = _PARENT_FIELD_RE.subn(
            lambda m: (f"{m.group(1)}{new_id}"
                       if m.group(2) == old_id else m.group(0)),
            text,
        )
        if n > 0 and new_text != text:
            f.write_text(new_text, encoding="utf-8")
            updated.append(f)
    return updated


def apply_collisions(repo_root: Path, collisions: list[dict]) -> dict:
    """Apply each collision: rename file, rewrite id, update parents, bump counter."""
    parent_updates_total = 0
    counter_bumps: dict[str, int] = {}
    for c in collisions:
        old_file = c["file"]
        new_file = old_file.with_name(f"{c['new_id']}.md")
        old_file.rename(new_file)
        _rewrite_id(new_file, c["new_id"])
        updated = _rewrite_parent_refs(repo_root, c["old_id"], c["new_id"])
        parent_updates_total += len(updated)
        # Track highest new number per type for counter bump
        num = int(c["new_id"].split("-", 1)[1])
        if num > counter_bumps.get(c["type"], 0):
            counter_bumps[c["type"]] = num

    counter_path = repo_root / ".edpa" / "config" / "id_counters.yaml"
    for item_type, value in counter_bumps.items():
        old = _read_counter(counter_path, item_type)
        if value > old:
            _write_counter_atomic(counter_path, item_type, value)

    return {
        "renamed": len(collisions),
        "parent_refs_updated": parent_updates_total,
        "counter_bumps": counter_bumps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="renumber_collisions",
        description="Resolve EDPA ID collisions between local and remote.",
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--apply", action="store_true",
                        help="Skip the interactive prompt and apply changes.")
    args = parser.parse_args()

    repo_root = _find_repo_root()
    if not repo_root:
        print("ERROR: not in a git repo", file=sys.stderr)
        return 2

    print(f"Fetching {args.remote}...")
    collisions = find_collisions(repo_root, args.remote)
    if not collisions:
        print("No collisions detected.")
        return 0

    print(f"\nDetected {len(collisions)} collision(s):\n")
    for c in collisions:
        print(f"  {c['old_id']} → {c['new_id']}")
        print(f"    Local:    {c['file'].relative_to(repo_root)}")
        print(f"    Upstream: {c['upstream_path']}")
    print()

    if not args.apply:
        try:
            answer = input("Apply? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "y":
            print("Aborted.")
            return 1

    summary = apply_collisions(repo_root, collisions)
    print(f"\nDone.")
    print(f"  Files renamed:    {summary['renamed']}")
    print(f"  parent: refs:     {summary['parent_refs_updated']}")
    print(f"  Counters bumped:  {summary['counter_bumps']}")
    print("\nStage and amend last commit (or create new commit), then re-push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
