#!/usr/bin/env python3
"""Semi-automatic resolution of EDPA ID collisions (V2 Layer 7).

Companion to ``validate_ids.py``. When pre-push detects that a local
ID also exists on the remote as a different item, this helper:

1. Fetches the remote to refresh upstream view
2. Finds items added on this branch whose ID the integration target
   already uses for another item (an item of this branch that already
   landed there — e.g. squash-merged — is not a collision)
3. Gives each a new ID: one above the known max under the local ID
   authority, a fresh reservation from the ID ledger under the remote
   one (ADR-014)
4. Renames the file, rewrites its ``id:`` field, and updates the
   references to it: ``parent:`` and ``depends_on:`` in the local
   backlog, story lists in ``.edpa/iterations/``
5. Local authority only: bumps ``.edpa/config/id_counters.yaml``

``--check`` (CI) never modifies anything. Under the remote authority it
additionally verifies that every item the branch adds is backed by a
reservation — on a pull request that is the check that still means
something, because a same-path collision makes the PR conflicting and
GitHub does not run ``pull_request`` workflows on conflicting PRs.

Always interactive: prints the planned rename and waits for ``y``
before applying. Use ``--apply`` to skip the prompt (CI / scripted use).
"""
from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
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
        next_id, resolve_authority,
    )
    try:
        # Shared identity / reservation logic. Optional on purpose: a
        # sandbox that vendors only this script + id_counter.py still
        # renumbers, with the pre-ADR-014 "any shared ID collides" rule.
        import validate_ids as _validate  # noqa: E402
    except ImportError:
        _validate = None
finally:
    sys.path.pop(0)

DIR_TO_TYPE = {v: k for k, v in TYPE_DIRS.items()}
PREFIX_TO_TYPE = {v: k for k, v in TYPE_PREFIX.items()}

_BACKLOG_PATH_RE = re.compile(r"\.edpa/backlog/([^/]+)/([A-Z]{1,3}-\d{1,9})\.md$")
_PARENT_FIELD_RE = re.compile(r"^(parent:\s*)([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)
_ID_FIELD_RE = re.compile(r"^(id:\s*)([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)
# A YAML list entry that is exactly one item ID, optionally commented:
# `- S-5` under depends_on:, `    - S-5  # Upload tests` in an iteration.
_LIST_ENTRY_RE = re.compile(
    r"^(\s*-\s*[\"']?)([A-Z]{1,3}-\d{1,9})([\"']?\s*(?:#.*)?)$", re.MULTILINE)


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd),
            capture_output=True, text=True, check=False, encoding="utf-8",
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


def _resolve_target_branch(repo_root: Path, remote: str) -> str:
    """Resolve the integration target branch name (remote's default branch).

    Reads ``refs/remotes/<remote>/HEAD`` symbolic ref; falls back to "main".
    """
    head_ref = _git(
        ["symbolic-ref", f"refs/remotes/{remote}/HEAD"], cwd=repo_root,
    )
    if head_ref:
        return head_ref.strip().rsplit("/", 1)[-1]
    return "main"


def find_collisions(
    repo_root: Path,
    remote: str = "origin",
    target_branch: str | None = None,
) -> list[dict]:
    """Return collisions: files ADDED on the local branch whose IDs already exist on the integration target branch.

    The collision check ALWAYS compares against the integration target (typically
    ``origin/main``), NOT against the matching remote branch. This is the correct
    semantic for feature-branch + PR workflow: when you're on ``feature/foo`` and
    open a PR against main, collisions are with what's already on main.

    Local-only files (added since merge-base with the target) are the only
    renumber candidates — modifications of existing items must be resolved
    via merge, not renumbering. An added file that is the *same item* as
    the one on the target (this branch's work, already landed there under
    another commit) is not a collision either.

    ``new_id`` is ``None`` under the remote ID authority: the replacement
    is reserved from the ledger when the renumber is applied, never during
    detection (``--check`` must not consume numbers).

    Args:
        repo_root: Path to the git repo root.
        remote: Remote name (default ``"origin"``).
        target_branch: Branch to compare against. ``None`` (default) auto-detects
            the remote's default branch via ``refs/remotes/<remote>/HEAD``.
            Pass an explicit name (e.g. ``"develop"``) for Git Flow projects.

    Returns ``[{old_id, new_id, file, type, upstream_path}]``.
    """
    _git(["fetch", "--quiet", remote], cwd=repo_root)
    remote_authority = _remote_authority(repo_root)

    if target_branch is None:
        target_branch = _resolve_target_branch(repo_root, remote)
    ref = f"{remote}/{target_branch}"

    if not _git(["rev-parse", "--verify", ref], cwd=repo_root):
        return []  # target branch doesn't exist on remote — nothing to collide with

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
        upstream_path = next(
            (p for p, i in remote_files if i == item_id), None,
        )
        if (_validate is not None and upstream_path == path
                and _validate.same_item(repo_root, ref, path, "HEAD")):
            continue  # this branch's own item, already on the target
        new_id = None
        if not remote_authority:
            working_max[item_type] += 1
            new_id = f"{TYPE_PREFIX[item_type]}-{working_max[item_type]}"
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


def _remote_authority(repo_root: Path) -> bool:
    try:
        return resolve_authority(repo_root).mode == "remote"
    except Exception:  # noqa: BLE001 — unreadable config: keep local rules
        return False


def _front(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _reserve_replacement(repo_root: Path, collision: dict) -> str:
    """A fresh ledger reservation for a renumbered item, recorded with the
    item's own ``created_at`` so the hooks accept the renamed file."""
    text = collision["file"].read_text(encoding="utf-8")
    front = _front(text)
    created = front.get("created_at")
    if _validate is not None:
        # Same normalisation the hooks apply (an unquoted YAML timestamp
        # parses to a datetime whose str() would never match again).
        created = _validate._created_at(text)
    return next_id(collision["type"], repo_root, meta={
        "title": front.get("title"),
        "parent": front.get("parent"),
        "created_at": str(created) if created is not None else None,
    })


def _rewrite_parent_refs(repo_root: Path, old_id: str, new_id: str) -> list[Path]:
    """Replace references old_id → new_id in every local backlog file:
    the ``parent:`` field and ``depends_on:`` list entries."""
    updated = []
    for f in _all_local_files(repo_root):
        text = f.read_text(encoding="utf-8")
        if old_id not in text:
            continue
        new_text = _PARENT_FIELD_RE.sub(
            lambda m: (f"{m.group(1)}{new_id}"
                       if m.group(2) == old_id else m.group(0)),
            text,
        )
        new_text = _rewrite_depends_on(new_text, old_id, new_id)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            updated.append(f)
    return updated


def _rewrite_depends_on(text: str, old_id: str, new_id: str) -> str:
    """Rewrite list entries under a frontmatter ``depends_on:`` key only —
    evidence refs and body prose keep the ID they were written with."""
    out, inside = [], False
    for line in text.split("\n"):
        if re.match(r"^depends_on:\s*$", line):
            inside = True
        elif inside and not re.match(r"^\s*-\s", line):
            inside = False
        if inside:
            line = _LIST_ENTRY_RE.sub(
                lambda m: (f"{m.group(1)}{new_id}{m.group(3)}"
                           if m.group(2) == old_id else m.group(0)), line)
        out.append(line)
    return "\n".join(out)


def _rewrite_iteration_refs(repo_root: Path, old_id: str, new_id: str) -> list[Path]:
    """Replace old_id → new_id in the item lists of .edpa/iterations/*.yaml
    (an item planned into an iteration on this branch)."""
    updated = []
    iterations = repo_root / ".edpa" / "iterations"
    if not iterations.is_dir():
        return updated
    for f in sorted(iterations.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        if old_id not in text:
            continue
        new_text = _LIST_ENTRY_RE.sub(
            lambda m: (f"{m.group(1)}{new_id}{m.group(3)}"
                       if m.group(2) == old_id else m.group(0)), text)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            updated.append(f)
    return updated


def apply_collisions(repo_root: Path, collisions: list[dict]) -> dict:
    """Apply each collision: rename file, rewrite id, update references,
    and (local ID authority) bump the counter."""
    remote_authority = _remote_authority(repo_root)
    parent_updates_total = 0
    counter_bumps: dict[str, int] = {}
    for c in collisions:
        if c.get("new_id") is None:
            c["new_id"] = _reserve_replacement(repo_root, c)
        old_file = c["file"]
        new_file = old_file.with_name(f"{c['new_id']}.md")
        old_file.rename(new_file)
        _rewrite_id(new_file, c["new_id"])
        updated = _rewrite_parent_refs(repo_root, c["old_id"], c["new_id"])
        updated += _rewrite_iteration_refs(repo_root, c["old_id"], c["new_id"])
        parent_updates_total += len(updated)
        # Track highest new number per type for counter bump
        num = int(c["new_id"].split("-", 1)[1])
        if num > counter_bumps.get(c["type"], 0):
            counter_bumps[c["type"]] = num

    if remote_authority:
        # The ledger is the record; the allocator already mirrored the
        # number wherever an old vendored hook still needs it.
        counter_bumps = {}
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


def find_unreserved(repo_root: Path, remote: str = "origin",
                    target_branch: str | None = None) -> tuple[list[str], list[str]]:
    """Remote ID authority: items added on this branch that the ID ledger
    does not back. Returns ``(errors, warnings)``; both empty under the
    local authority."""
    if _validate is None or not _remote_authority(repo_root):
        return [], []
    if target_branch is None:
        target_branch = _resolve_target_branch(repo_root, remote)
    ref = f"{remote}/{target_branch}"
    base = (_git(["merge-base", "HEAD", ref], cwd=repo_root) or "").strip()
    if not base:
        return [], []
    target_paths = {p for p, _i in _list_remote_backlog(repo_root, ref)}
    added = _git(["diff", "--name-only", "--diff-filter=A", base, "HEAD"],
                 cwd=repo_root)
    new_items = []
    for path in (added or "").splitlines():
        m = _BACKLOG_PATH_RE.search(path)
        item_type = DIR_TO_TYPE.get(m.group(1)) if m else None
        if not item_type or path in target_paths:
            continue
        new_items.append((path, m.group(2), item_type,
                          _git(["show", f"HEAD:{path}"], cwd=repo_root)))
    return _validate.reservation_problems(
        repo_root, resolve_authority(repo_root), new_items)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="renumber_collisions",
        description="Resolve EDPA ID collisions between local and remote.",
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--target", default=None,
                        help="Integration target branch (default: remote's default branch, typically main). "
                             "Override for Git Flow projects, e.g. --target develop.")
    parser.add_argument("--apply", action="store_true",
                        help="Skip the interactive prompt and apply changes.")
    parser.add_argument("--check", action="store_true",
                        help="CI mode — detect + report only, never modify. "
                             "Exit 0 if no collisions, 1 if collisions found. No prompt.")
    args = parser.parse_args()

    repo_root = _find_repo_root()
    if not repo_root:
        print("ERROR: not in a git repo", file=sys.stderr)
        return 2

    target = args.target or _resolve_target_branch(repo_root, args.remote)
    print(f"Fetching {args.remote} (target: {target})...")
    collisions = find_collisions(repo_root, args.remote, args.target)

    unreserved: list[str] = []
    if args.check:
        unreserved, warnings = find_unreserved(repo_root, args.remote, args.target)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)

    if not collisions and not unreserved:
        print("No collisions detected.")
        return 0

    if collisions:
        print(f"\nDetected {len(collisions)} collision(s):\n")
    for c in collisions:
        new = c["new_id"] or "(next free ID, reserved from the ledger on apply)"
        print(f"  {c['old_id']} → {new}")
        print(f"    Local:    {c['file'].relative_to(repo_root)}")
        print(f"    Upstream: {c['upstream_path']}")
    if unreserved:
        print(f"\nDetected {len(unreserved)} item(s) without an ID reservation:\n")
        for e in unreserved:
            print(f"  {e}")
    print()

    if args.check:
        # CI mode — detected, exit non-zero, do nothing
        return 1

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
