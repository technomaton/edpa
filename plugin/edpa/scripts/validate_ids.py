#!/usr/bin/env python3
"""Local-first ID safety validator — pre-commit and pre-push modes.

V2 defense-in-depth Layers 5 (pre-commit) + 6 (pre-push) from
``docs/v2/plan.md``. Runs as a git hook to catch ID collisions before
they reach upstream.

Modes:
    --staged    Validate staged ``.edpa/backlog/`` files against working
                tree state. Checks filename ≡ frontmatter id, no
                duplicate IDs within staged set, counter file monotonic
                with new items, no new ID already exists in HEAD.

    --pre-push  Validate commits about to be pushed against the remote
                tip. Reads ``git pre-push`` stdin protocol (one line per
                local→remote ref pair). Fetches the remote ref, diffs
                local commits, and checks that no new backlog file ID
                exists upstream.

Exit codes:
    0   all checks pass (or no relevant files)
    1   one or more checks failed (commit/push blocked)
    2   unexpected internal error (e.g. corrupted YAML)
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
    from id_counter import TYPE_DIRS, TYPE_PREFIX  # noqa: E402
finally:
    sys.path.pop(0)

# Reverse map: directory name → item type (Story, Feature, …).
DIR_TO_TYPE = {v: k for k, v in TYPE_DIRS.items()}
# Reverse map: prefix → item type.
PREFIX_TO_TYPE = {v: k for k, v in TYPE_PREFIX.items()}

_BACKLOG_PATH_RE = re.compile(r"^\.edpa/backlog/([^/]+)/([A-Z]{1,3}-\d{1,9})\.md$")
_ID_FROM_FRONTMATTER_RE = re.compile(r"^id:\s*([A-Z]{1,3}-\d{1,9})\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, check=False,
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


def _parse_counter(content: str) -> dict[str, int]:
    """Parse id_counters.yaml content into {type: counter_value}."""
    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return {}
    counters = data.get("counters") or {}
    return {k: int(v) for k, v in counters.items() if isinstance(v, (int, float))}


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

    # Check 1: filename ≡ frontmatter id, per file
    seen_ids: dict[str, str] = {}
    for path, _dir, item_id, _type in backlog_staged:
        content = _read_staged_file(repo_root, path)
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
        if path in head_paths:
            continue
        # collision if a different file with same ID exists at HEAD
        for hp in head_paths:
            parsed = _parse_backlog_path(hp)
            if parsed and parsed[1] == item_id and hp != path:
                errors.append(
                    f"{path}: ID {item_id} already exists at HEAD as {hp}"
                )

    # Check 3: counter file monotonic with new items
    if counter_staged or backlog_staged:
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

    errors: list[str] = []
    for raw in sys.stdin:
        parts = raw.strip().split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if local_sha == _ZERO_SHA:
            continue  # branch deletion, not relevant

        # Determine the comparison base: remote tip if it exists, otherwise
        # the merge-base with the default branch on remote.
        if remote_sha != _ZERO_SHA:
            base = remote_sha
        else:
            mb_out = _git(
                ["merge-base", local_sha, f"{remote}/HEAD"], cwd=repo_root,
            )
            base = mb_out.strip() if mb_out else None
        if not base:
            continue  # first push of a brand-new branch with no shared history

        added = _git(
            ["diff", "--name-only", "--diff-filter=A", base, local_sha],
            cwd=repo_root,
        )
        for line in (added or "").splitlines():
            parsed = _parse_backlog_path(line)
            if not parsed:
                continue
            _dir, item_id, _type = parsed
            # Check whether the SAME ID exists upstream under any directory.
            up_files = _list_tree(repo_root, base, ".edpa/backlog")
            for up_path in up_files:
                up_parsed = _parse_backlog_path(up_path)
                if up_parsed and up_parsed[1] == item_id and up_path != line:
                    errors.append(
                        f"{line}: ID {item_id} already exists upstream as "
                        f"{up_path} (at {base[:8]})"
                    )

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
        description="EDPA local-first ID safety validator (pre-commit / pre-push).",
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
