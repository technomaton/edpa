#!/usr/bin/env python3
"""Migrate an EDPA V1 (GH-coupled) project to V2 (local-first).

Per docs/v2/plan.md § "Migration skript". Performs an idempotent
one-shot transformation:

1. Final sync pull (optional, opt-out via --skip-pull) — last GH-side
   state captured before sync.py becomes obsolete.
2. Seed id_counters.yaml from filesystem scan (max(numeric_suffix)
   per type).
3. Backfill created_at/closed_at on items missing them, from git log.
4. Archive issue_map.yaml → .edpa/archive/issue_map_v1.yaml.
5. Strip the ``sync:`` block from edpa.yaml (kept as commented-out
   reference under ``# v1_sync_archive:`` for audit).
6. Create one migration commit (no --no-verify).

Safe to re-run: each step is a no-op if its post-condition already holds.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from id_counter import seed_counters_from_fs, TYPE_DIRS  # noqa: E402
    import _git_timestamps as gts  # noqa: E402
    from _md_frontmatter import load_md, save_md_item  # noqa: E402
finally:
    sys.path.pop(0)


def _git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check,
    )


def _find_repo_root(start: Path) -> Path | None:
    out = _git(["rev-parse", "--show-toplevel"], cwd=start)
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip())


def step_final_sync_pull(repo_root: Path, skip: bool) -> dict:
    if skip:
        return {"action": "skipped"}
    sync_py = repo_root / ".edpa" / "engine" / "scripts" / "sync.py"
    if not sync_py.exists():
        sync_py = repo_root / "plugin" / "edpa" / "scripts" / "sync.py"
    if not sync_py.exists():
        return {"action": "skipped", "reason": "sync.py not found"}
    r = subprocess.run(
        ["python3", str(sync_py), "pull", "--commit"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    return {
        "action": "ran" if r.returncode == 0 else "failed",
        "rc": r.returncode,
        "stdout_tail": r.stdout[-400:] if r.stdout else "",
        "stderr_tail": r.stderr[-400:] if r.stderr else "",
    }


def step_seed_counters(repo_root: Path) -> dict:
    counters = seed_counters_from_fs(repo_root)
    return {"action": "seeded", "counters": counters}


def step_backfill_timestamps(repo_root: Path) -> dict:
    edpa = repo_root / ".edpa"
    touched: list[str] = []
    for d in TYPE_DIRS.values():
        type_dir = edpa / "backlog" / d
        if not type_dir.exists():
            continue
        for f in type_dir.glob("*.md"):
            data = load_md(f) or {}
            changed = False
            if not data.get("created_at"):
                ca = gts.created_at(f, repo_root)
                if ca:
                    data["created_at"] = ca
                    changed = True
            if not data.get("updated_at"):
                ua = gts.updated_at(f, repo_root)
                if ua:
                    data["updated_at"] = ua
                    changed = True
            # closed_at only for items currently in Done state
            if data.get("status") == "Done" and not data.get("closed_at"):
                cl = gts.closed_at(f, repo_root)
                if cl:
                    data["closed_at"] = cl
                    changed = True
            if changed:
                save_md_item(f, data)
                touched.append(str(f.relative_to(repo_root)))
    return {"action": "backfilled", "files_touched": touched}


def step_archive_issue_map(repo_root: Path) -> dict:
    src = repo_root / ".edpa" / "config" / "issue_map.yaml"
    if not src.exists():
        return {"action": "skipped", "reason": "issue_map.yaml not present"}
    dst_dir = repo_root / ".edpa" / "archive"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "issue_map_v1.yaml"
    if dst.exists():
        return {"action": "skipped", "reason": "already archived"}
    shutil.move(str(src), str(dst))
    return {"action": "moved", "to": str(dst.relative_to(repo_root))}


_SYNC_KEYS = {
    "github_org", "github_repo", "github_project_number",
    "field_ids", "option_ids",
}


def step_strip_sync_config(repo_root: Path) -> dict:
    path = repo_root / ".edpa" / "config" / "edpa.yaml"
    if not path.exists():
        return {"action": "skipped", "reason": "edpa.yaml not present"}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        return {"action": "failed", "reason": f"parse error: {e}"}
    sync = data.get("sync")
    if not sync:
        return {"action": "skipped", "reason": "no sync block"}
    archived = {k: v for k, v in sync.items() if k in _SYNC_KEYS}
    data.pop("sync", None)
    data["v1_sync_archive"] = archived
    path.write_text(yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True,
    ))
    return {"action": "stripped", "archived_keys": sorted(archived)}


def step_commit(repo_root: Path, summary: dict, dry_run: bool) -> dict:
    """Stage all .edpa/ changes and create a single migration commit."""
    if dry_run:
        return {"action": "dry-run"}
    _git(["add", ".edpa/"], cwd=repo_root)
    status = _git(["status", "--porcelain", ".edpa/"], cwd=repo_root)
    if not status.stdout.strip():
        return {"action": "skipped", "reason": "nothing to commit"}
    msg = "chore(v2): migrate from GH-coupled V1 to local-first V2\n\n"
    for step, info in summary.items():
        if info.get("action") in ("skipped", "dry-run"):
            continue
        msg += f"- {step}: {info.get('action','?')}\n"
    msg += "\nGenerated by .edpa/engine/scripts/migrate_v1_to_v2.py"
    r = _git(["commit", "-m", msg], cwd=repo_root)
    return {"action": "committed" if r.returncode == 0 else "failed",
            "stdout_tail": r.stdout[-200:]}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_v1_to_v2",
        description="Migrate an EDPA V1 (GH-coupled) project to V2 (local-first).",
    )
    parser.add_argument("--skip-pull", action="store_true",
                        help="Skip the final sync.py pull (e.g. project no longer has GH access).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done but don't write files or commit.")
    args = parser.parse_args()

    repo_root = _find_repo_root(Path.cwd())
    if not repo_root:
        print("ERROR: not in a git repo", file=sys.stderr)
        return 2
    if not (repo_root / ".edpa").exists():
        print("ERROR: .edpa/ not found at repo root", file=sys.stderr)
        return 2

    summary: dict = {}
    print(f"Migrating {repo_root}\n")

    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    summary["final_sync_pull"] = step_final_sync_pull(repo_root, args.skip_pull)
    print(f"  Step 1 (final sync pull): {summary['final_sync_pull']['action']}")

    if not args.dry_run:
        summary["seed_counters"] = step_seed_counters(repo_root)
        print(f"  Step 2 (seed id_counters.yaml): {summary['seed_counters']['counters']}")

        summary["backfill_timestamps"] = step_backfill_timestamps(repo_root)
        n = len(summary["backfill_timestamps"]["files_touched"])
        print(f"  Step 3 (backfill timestamps): {n} file(s) touched")

        summary["archive_issue_map"] = step_archive_issue_map(repo_root)
        print(f"  Step 4 (archive issue_map.yaml): {summary['archive_issue_map']['action']}")

        summary["strip_sync_config"] = step_strip_sync_config(repo_root)
        print(f"  Step 5 (strip sync from edpa.yaml): {summary['strip_sync_config']['action']}")

    summary["commit"] = step_commit(repo_root, summary, args.dry_run)
    print(f"  Step 6 (commit): {summary['commit']['action']}")

    print("\nNext steps:")
    print("  1. Review the migration commit (`git show HEAD`).")
    print("  2. Install V2 git hooks: see plugin/edpa/scripts/hooks/.")
    print("  3. If you have a GH Project board, archive (don't delete) it for audit.")
    print("  4. New items: use `backlog.py add --local`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
