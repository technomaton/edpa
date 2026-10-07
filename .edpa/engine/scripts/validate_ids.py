#!/usr/bin/env python3
"""ID safety validator — pre-commit and pre-push modes.

Runs as a git hook to catch ID problems before they reach upstream.

Modes:
    --staged    Validate staged ``.edpa/backlog/`` files. Always: filename
                ≡ frontmatter id, no duplicate IDs within the staged set,
                no new ID already at HEAD under another path. Then, by ID
                authority (``id_counter.resolve_authority``):

                local   the tracked counter grew with the new items;
                remote  every new item is backed by a reservation in the
                        ID ledger (ADR-014): its number is either at or
                        below the ledger's floor (it predates the ledger)
                        or the ledger holds a record for it whose
                        ``created_at`` matches the item's.

    --pre-push  Validate commits about to be pushed against the remote's
                integration branch. Reads the ``git pre-push`` stdin
                protocol (one line per local→remote ref pair). Blocks when
                an item added by the push already exists upstream *as a
                different item* — including the common case where both
                sit at the same path (two Stories that both got S-5).
                Under the remote authority it also verifies reservations,
                which is what catches items committed with --no-verify or
                minted by an outdated allocator.

Exit codes:
    0   all checks pass (or no relevant files)
    1   one or more checks failed (commit/push blocked)
    2   unexpected internal error (e.g. corrupted YAML)
"""
from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    import id_counter as _id_counter  # noqa: E402
    from id_counter import TYPE_DIRS, TYPE_PREFIX  # noqa: E402
finally:
    sys.path.pop(0)

# Reverse map: directory name → item type (Story, Feature, …).
DIR_TO_TYPE = {v: k for k, v in TYPE_DIRS.items()}
# Reverse map: prefix → item type.
PREFIX_TO_TYPE = {v: k for k, v in TYPE_PREFIX.items()}

_BACKLOG_PATH_RE = re.compile(r"^\.edpa/backlog/([^/]+)/([A-Z]{1,3}-\d{1,9})\.md$")
_ID_FROM_FRONTMATTER_RE = re.compile(r"^id:\s*([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)

# Hooks sit on an interactive path — do not wait the allocator's full
# network timeout to find out the remote is unreachable.
_HOOK_NET_TIMEOUT_SEC = 8


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, check=False, encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _find_repo_root() -> Path | None:
    out = _git(["rev-parse", "--show-toplevel"])
    return Path(out.strip()) if out else None


def _staged_paths(repo_root: Path) -> list[str]:
    """Paths added or modified in the current staged set, repo-relative."""
    out = _git(
        ["diff", "--cached", "--name-only", "--diff-filter=AM"], cwd=repo_root,
    )
    return [p for p in (out or "").splitlines() if p]


def _read_staged_file(repo_root: Path, path: str) -> str | None:
    """Return the staged (index) content of path, or None if not staged."""
    out = _git(["show", f":{path}"], cwd=repo_root)
    return out


def _read_committed_file(repo_root: Path, ref: str, path: str) -> str | None:
    """Return content of path at git ref, or None if file doesn't exist there."""
    out = _git(["show", f"{ref}:{path}"], cwd=repo_root)
    return out


def _list_tree(repo_root: Path, ref: str, prefix: str) -> list[str]:
    """List files under ``prefix`` in ``ref``'s tree. Empty list if ref missing."""
    out = _git(["ls-tree", "-r", "--name-only", ref, prefix], cwd=repo_root)
    return [p for p in (out or "").splitlines() if p]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_backlog_path(path: str) -> tuple[str, str, str] | None:
    """Decompose .edpa/backlog/{dir}/{ID}.md into (dir, id, type) tuple.

    Returns None if path is not a recognized backlog file.
    """
    m = _BACKLOG_PATH_RE.match(path)
    if not m:
        return None
    dir_name, item_id = m.group(1), m.group(2)
    item_type = DIR_TO_TYPE.get(dir_name)
    if item_type is None:
        return None
    return dir_name, item_id, item_type


def _extract_id_from_frontmatter(content: str) -> str | None:
    """Find ``id: X-N`` in YAML frontmatter; return X-N or None."""
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 4)
    if end < 0:
        return None
    fm = content[4:end]
    m = _ID_FROM_FRONTMATTER_RE.search(fm)
    return m.group(1) if m else None


def _frontmatter(content: str | None) -> dict:
    if not content or not content.startswith("---"):
        return {}
    end = content.find("\n---", 4)
    if end < 0:
        return {}
    try:
        data = yaml.safe_load(content[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _created_at(content: str | None) -> str | None:
    """The item's ``created_at`` as the string the allocator recorded.

    The write layer stores it quoted; a hand-edited unquoted value parses
    as a timestamp and is normalised back to the same shape.
    """
    value = _frontmatter(content).get("created_at")
    if isinstance(value, _dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if value is None:
        return None
    return str(value).strip() or None


def _title(content: str | None) -> str:
    return str(_frontmatter(content).get("title") or "").strip()


def _parse_counter(content: str) -> dict[str, int]:
    """Parse id_counters.yaml content into {type: counter_value}."""
    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return {}
    counters = data.get("counters") or {}
    return {k: int(v) for k, v in counters.items() if isinstance(v, (int, float))}


# ---------------------------------------------------------------------------
# Identity + reservations (ADR-014) — shared with renumber_collisions.py
# ---------------------------------------------------------------------------

def authority(repo_root: Path):
    """The project's ID authority, or ``None`` when it cannot be resolved
    (then the caller keeps the legacy, local rules)."""
    try:
        return _id_counter.resolve_authority(repo_root)
    except Exception:  # noqa: BLE001 — a hook must not die on a bad config
        return None


def integration_target(repo_root: Path, remote: str) -> str | None:
    """The remote branch new work lands on: ``<remote>/HEAD``, else
    ``<remote>/main``, else ``<remote>/master``."""
    head_ref = _git(["symbolic-ref", f"refs/remotes/{remote}/HEAD"], cwd=repo_root)
    if head_ref and head_ref.strip():
        return head_ref.strip()
    for name in ("main", "master"):
        ref = f"refs/remotes/{remote}/{name}"
        if _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root):
            return ref
    return None


def same_item(repo_root: Path, target_ref: str, path: str,
              local_ref: str, local_content: str | None = None) -> bool:
    """Is ``path`` on ``local_ref`` the same item as ``path`` on the target?

    The same ID at the same path is the ordinary shape of both "my item,
    already merged (e.g. squashed)" and "someone else's item that got my
    number". ``created_at`` tells them apart; for items older than that
    stamp, lineage does: the version that entered the target must be one
    this branch has had.
    """
    theirs = _read_committed_file(repo_root, target_ref, path)
    if theirs is None:
        return True
    if local_content is None:
        local_content = _read_committed_file(repo_root, local_ref, path)
    mine_at, theirs_at = _created_at(local_content), _created_at(theirs)
    if mine_at and theirs_at:
        return mine_at == theirs_at

    added = _git(["log", "--diff-filter=A", "--format=%H", "-1", target_ref,
                  "--", path], cwd=repo_root)
    if not added or not added.strip():
        return False
    entered = _git(["rev-parse", f"{added.strip()}:{path}"], cwd=repo_root)
    if not entered:
        return False
    history = _git(["log", "--format=%H", "-100", local_ref, "--", path],
                   cwd=repo_root)
    for sha in (history or "").split():
        blob = _git(["rev-parse", f"{sha}:{path}"], cwd=repo_root)
        if blob and blob.strip() == entered.strip():
            return True
    return False


def reservation_problems(repo_root: Path, auth,
                         new_items: list[tuple[str, str, str, str | None]],
                         ) -> tuple[list[str], list[str]]:
    """Check new items against the ID ledger. Returns ``(errors, warnings)``.

    ``new_items`` is ``[(path, item_id, item_type, content)]``.

    * a ledger record exists → the item's ``created_at`` must match it
      (records of pre-reserved blocks carry none and accept any item);
    * no record, number ≤ the type's floor → the item predates the ledger;
    * no record above the floor → not reserved: blocked.

    The local cache is consulted first; one refresh is attempted when a
    record is missing (the cache may simply be stale). If the ledger
    cannot be consulted at all the item is reported as a warning — the
    push-time check is the one that must be online.
    """
    errors: list[str] = []
    warnings: list[str] = []
    ledger = _id_counter._ledger()
    if ledger is None or not new_items:
        return errors, warnings

    tried = {"refresh": False, "ok": False}

    def refresh() -> bool:
        if not tried["refresh"]:
            tried["refresh"] = True
            try:
                tried["ok"] = bool(ledger.refresh(
                    repo_root, remote=auth.remote, ref=auth.ref,
                    timeout=_HOOK_NET_TIMEOUT_SEC))
            except ledger.LedgerError:
                tried["ok"] = False
        return tried["ok"]

    def state():
        try:
            return ledger.cached_state(repo_root)
        except ledger.LedgerError:
            return None

    known = state()
    if known is None and refresh():
        known = state()
    if known is None:
        warnings.append(
            f"ID ledger ({auth.ref} on {auth.remote}) is not available — "
            f"reservations of {len(new_items)} new item(s) not verified")
        return errors, warnings
    _counters, floors = known

    for path, item_id, item_type, content in new_items:
        number = int(item_id.rsplit("-", 1)[1])
        record = ledger.find_record(repo_root, item_id)
        if record is None and number > floors.get(item_type, 0):
            if not tried["refresh"] and refresh():
                _counters, floors = state() or known
                record = ledger.find_record(repo_root, item_id)
        if record is not None:
            want, have = record.get("created_at"), _created_at(content)
            if want and have != want:
                what = f' "{record["title"]}"' if record.get("title") else ""
                errors.append(
                    f"{path}: {item_id} is reserved in the ID ledger for a "
                    f"different item{what} (by {record.get('by') or '?'}, "
                    f"{record.get('at') or '?'}). This file was not created "
                    f"by the allocator — create the item with /edpa:add."
                )
            continue
        floor = floors.get(item_type, 0)
        if number <= floor:
            continue                      # predates the ledger
        if tried["refresh"] and not tried["ok"]:
            warnings.append(
                f"{path}: cannot reach the ID ledger to verify the "
                f"reservation of {item_id}")
            continue
        errors.append(
            f"{path}: {item_id} has no reservation in the ID ledger "
            f"(numbers up to {TYPE_PREFIX[item_type]}-{floor} predate it). "
            f"IDs come from /edpa:add (backlog.py add); if an outdated EDPA "
            f"plugin minted this one, update the plugin and re-create the "
            f"item."
        )
    return errors, warnings


def _history_edit_in_progress(repo_root: Path) -> bool:
    """Merge / cherry-pick / revert in flight: the staged additions are
    other people's commits being replayed, not new allocations here."""
    return any(
        _git(["rev-parse", "--verify", "--quiet", name], cwd=repo_root)
        for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
    )


# ---------------------------------------------------------------------------
# --staged
# ---------------------------------------------------------------------------

_COUNTER_PATH = ".edpa/config/id_counters.yaml"


def cmd_staged(args: argparse.Namespace) -> int:
    repo_root = _find_repo_root()
    if not repo_root:
        return 0  # not a git repo — defer to other checks

    staged = _staged_paths(repo_root)
    backlog_staged: list[tuple[str, str, str, str]] = []  # (path, dir, id, type)
    counter_staged = False
    for p in staged:
        if p == _COUNTER_PATH:
            counter_staged = True
            continue
        parsed = _parse_backlog_path(p)
        if parsed:
            backlog_staged.append((p, *parsed))

    if not backlog_staged and not counter_staged:
        return 0  # nothing to check

    errors: list[str] = []
    warnings: list[str] = []

    # Check 1: filename ≡ frontmatter id, per file
    seen_ids: dict[str, str] = {}
    contents: dict[str, str | None] = {}
    for path, _dir, item_id, _type in backlog_staged:
        content = _read_staged_file(repo_root, path)
        contents[path] = content
        if content is None:
            errors.append(f"{path}: cannot read staged content")
            continue
        fm_id = _extract_id_from_frontmatter(content)
        if fm_id is None:
            errors.append(f"{path}: no `id:` field in frontmatter")
        elif fm_id != item_id:
            errors.append(
                f"{path}: filename ID {item_id!r} ≠ frontmatter id {fm_id!r}"
            )
        if item_id in seen_ids:
            errors.append(
                f"duplicate ID {item_id} in staged set: "
                f"{seen_ids[item_id]} and {path}"
            )
        else:
            seen_ids[item_id] = path

    # Check 2: no new ID already exists at HEAD
    head_paths = set(_list_tree(repo_root, "HEAD", ".edpa/backlog"))
    for path, _dir, item_id, _type in backlog_staged:
        if path in head_paths:
            continue  # modification, not addition
        # collision if a different file with same ID exists at HEAD
        for hp in head_paths:
            parsed = _parse_backlog_path(hp)
            if parsed and parsed[1] == item_id and hp != path:
                errors.append(
                    f"{path}: ID {item_id} already exists at HEAD as {hp}"
                )

    # Check 3: every new item was really allocated
    auth = authority(repo_root)
    if auth is not None and auth.mode == "remote":
        new_items = [(path, item_id, item_type, contents.get(path))
                     for path, _dir, item_id, item_type in backlog_staged
                     if path not in head_paths]
        if new_items and not _history_edit_in_progress(repo_root):
            errs, warns = reservation_problems(repo_root, auth, new_items)
            errors.extend(errs)
            warnings.extend(warns)
    elif counter_staged or backlog_staged:
        # Local authority: the tracked counter is the allocator's record.
        old_content = _read_committed_file(repo_root, "HEAD", _COUNTER_PATH) or ""
        new_content = (
            _read_staged_file(repo_root, _COUNTER_PATH) or old_content
        )
        old_counters = _parse_counter(old_content)
        new_counters = _parse_counter(new_content)

        # Count of *new* items per type in this staged set
        new_per_type: dict[str, int] = {}
        for path, _dir, _item_id, item_type in backlog_staged:
            if path not in head_paths:
                new_per_type[item_type] = new_per_type.get(item_type, 0) + 1

        for item_type, added in new_per_type.items():
            old_v = old_counters.get(item_type, 0)
            new_v = new_counters.get(item_type, 0)
            if new_v < old_v + added:
                errors.append(
                    f"counter[{item_type}]={new_v} but adding {added} new "
                    f"item(s) requires ≥ {old_v + added} (old was {old_v}). "
                    f"Run id_counter.next_id to allocate properly."
                )

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        print("✗ ID safety check failed (pre-commit):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nTo bypass (NOT recommended), use `git commit --no-verify`.",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# --pre-push
# ---------------------------------------------------------------------------

_ZERO_SHA = "0" * 40


def cmd_pre_push(args: argparse.Namespace) -> int:
    repo_root = _find_repo_root()
    if not repo_root:
        return 0
    remote = args.remote

    refresh = _git(["fetch", "--quiet", remote], cwd=repo_root)
    if refresh is None:
        # Network/auth issue — emit warning but don't block.
        print(
            f"warning: could not fetch {remote}; pre-push ID check skipped.",
            file=sys.stderr,
        )
        return 0

    # Compare added IDs against the integration target (remote default
    # branch tip), NOT against the pushed branch's own remote tip or the
    # merge-base — both are older than main and miss items merged since.
    target_ref = integration_target(repo_root, remote)
    if target_ref is None:
        print(
            f"warning: cannot tell which branch of {remote} work lands on "
            f"(run `git remote set-head {remote} --auto`); pre-push ID "
            f"check skipped.",
            file=sys.stderr,
        )
        return 0
    up_files = _list_tree(repo_root, target_ref, ".edpa/backlog")
    up_set = set(up_files)

    errors: list[str] = []
    new_items: list[tuple[str, str, str, str | None]] = []
    seen: set[str] = set()
    for raw in sys.stdin:
        parts = raw.strip().split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if local_sha == _ZERO_SHA or set(local_sha) == {"0"}:
            continue  # branch deletion, not relevant

        # What this push adds: relative to the remote tip of this branch if
        # it exists, otherwise to where the branch left the target.
        base: str | None = None
        if set(remote_sha) != {"0"}:
            base = remote_sha
        else:
            mb_out = _git(["merge-base", local_sha, target_ref], cwd=repo_root)
            base = mb_out.strip() if mb_out else None
        if not base:
            continue  # first push of a brand-new branch with no shared history

        added = _git(
            ["diff", "--name-only", "--diff-filter=A", base, local_sha],
            cwd=repo_root,
        )
        for line in (added or "").splitlines():
            parsed = _parse_backlog_path(line)
            if not parsed or line in seen:
                continue
            seen.add(line)
            _dir, item_id, item_type = parsed
            content = _read_committed_file(repo_root, local_sha, line)

            # The same ID upstream under another directory (misplaced file).
            for up_path in up_files:
                up_parsed = _parse_backlog_path(up_path)
                if up_parsed and up_parsed[1] == item_id and up_path != line:
                    errors.append(
                        f"{line}: ID {item_id} already exists on {target_ref} as "
                        f"{up_path}"
                    )

            if line not in up_set:
                new_items.append((line, item_id, item_type, content))
                continue
            # Same ID at the same path — the ordinary collision (two
            # Stories that both got S-5), or simply this branch's own item
            # that already landed.
            if not same_item(repo_root, target_ref, line, local_sha, content):
                theirs = _read_committed_file(repo_root, target_ref, line)
                errors.append(
                    f"{line}: ID {item_id} already exists on {target_ref} as a "
                    f"different item\n"
                    f"      yours:    \"{_title(content)}\"\n"
                    f"      upstream: \"{_title(theirs)}\""
                )

    warnings: list[str] = []
    auth = authority(repo_root)
    if auth is not None and auth.mode == "remote" and new_items:
        errs, warnings = reservation_problems(repo_root, auth, new_items)
        errors.extend(errs)

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        print("✗ ID collision check failed (pre-push):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nTo fix, run:\n"
            "  python3 .edpa/engine/scripts/renumber_collisions.py\n"
            "Then amend or re-commit and re-push.\n"
            "To bypass (NOT recommended), use `git push --no-verify`.",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="validate_ids",
        description="EDPA ID safety validator (pre-commit / pre-push).",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("--staged", help=argparse.SUPPRESS)
    p_push = sub.add_parser("--pre-push", help=argparse.SUPPRESS)
    p_push.add_argument("--remote", default="origin")
    # Allow flag-style invocation too: validate_ids.py --staged
    # (re-parsed below if the first arg looks like a flag).
    raw = sys.argv[1:]
    if raw and raw[0] in ("--staged", "--pre-push"):
        mode = raw[0][2:]  # "staged" or "pre-push"
        rest = raw[1:]
        if mode == "staged":
            ns = argparse.Namespace(mode="staged")
            return cmd_staged(ns)
        ns = argparse.Namespace(mode="pre-push", remote="origin")
        if "--remote" in rest:
            i = rest.index("--remote")
            ns.remote = rest[i + 1] if i + 1 < len(rest) else "origin"
        return cmd_pre_push(ns)
    args = parser.parse_args()
    if args.mode == "--staged":
        return cmd_staged(args)
    if args.mode == "--pre-push":
        return cmd_pre_push(args)
    parser.error("unknown mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
