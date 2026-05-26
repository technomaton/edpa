#!/usr/bin/env python3
"""EDPA V2 project bootstrap — local-only, no GitHub provisioning.

Initializes ``.edpa/`` for a new project. Idempotent: safe to re-run.

What it does:
  1. Create directory tree (config, backlog/*, iterations, reports, …).
  2. Seed ``.edpa/config/people.yaml`` + ``.edpa/config/edpa.yaml`` from
     ``plugin/edpa/templates/*.tmpl`` if missing (idempotent).
  3. Seed ``.edpa/config/id_counters.yaml`` from existing file IDs.
  4. Optionally copy the CI workflow template (``--with-ci``) to
     ``.github/workflows/edpa-contribution-sync.yml`` so the engine
     can read PR signals materialized from PR events.
  5. Optionally install git hooks (``--with-hooks``) — pre-commit +
     pre-push ID safety validators.

What it does NOT do (V2.0 hard cut from V1):
  - No ``gh project`` calls
  - No ``gh issue create``
  - No GitHub Issue Types
  - No issue_map.yaml
  - No GraphQL anywhere

Usage:
    python3 .edpa/engine/scripts/project_setup.py
    python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from id_counter import seed_counters_from_fs, TYPE_DIRS  # noqa: E402
finally:
    sys.path.pop(0)


# ─── Display helpers ────────────────────────────────────────────────────────


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RED = "\033[31m"


def step(n: int, text: str) -> None:
    print(f"\n  {C.CYAN}{C.BOLD}[{n}]{C.RESET} {text}")


def ok(text: str) -> None:
    print(f"      {C.GREEN}✓{C.RESET} {text}")


def warn(text: str) -> None:
    print(f"      {C.YELLOW}!{C.RESET} {text}")


def info(text: str) -> None:
    print(f"      {C.DIM}· {text}{C.RESET}")


# ─── Bootstrap steps ────────────────────────────────────────────────────────


def find_repo_root(start: Path) -> Path:
    """Walk up to git repo root; fall back to start if not a git repo."""
    p = start.resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return start.resolve()


def create_directory_tree(root: Path) -> None:
    edpa = root / ".edpa"
    for d in ("config", "iterations", "reports", "snapshots",
              "pi-objectives", "archive"):
        (edpa / d).mkdir(parents=True, exist_ok=True)
    for backlog_dir in TYPE_DIRS.values():
        (edpa / "backlog" / backlog_dir).mkdir(parents=True, exist_ok=True)
    ok(f"Directory tree at {edpa.relative_to(root)}/")


def _seed_one(template_path: Path, target: Path) -> bool:
    if target.exists():
        return False
    if not template_path.exists():
        warn(f"Template missing: {template_path}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template_path, target)
    return True


def _find_templates_dir(root: Path) -> Path:
    """Returns templates dir whether running from source or vendored layout."""
    candidates = [
        HERE.parent / "templates",
        root / ".edpa" / "engine" / "templates",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def seed_configs(root: Path) -> None:
    templates = _find_templates_dir(root)
    edpa = root / ".edpa"

    if _seed_one(templates / "people.yaml.tmpl", edpa / "config" / "people.yaml"):
        ok("Seeded .edpa/config/people.yaml (edit with your team)")
    else:
        info("people.yaml already present — leaving as-is")

    if _seed_one(templates / "edpa.yaml.tmpl", edpa / "config" / "edpa.yaml"):
        ok("Seeded .edpa/config/edpa.yaml (edit project.name)")
    else:
        info("edpa.yaml already present — leaving as-is")

    for f in ("changelog.jsonl", "sync_state.json"):
        (edpa / f).touch()


def seed_id_counters(root: Path) -> None:
    counters = seed_counters_from_fs(root)
    nonzero = {k: v for k, v in counters.items() if v}
    ok(f"id_counters.yaml seeded ({len(nonzero)} type(s) with existing items)")
    if nonzero:
        info(f"current max IDs: {nonzero}")


def install_ci_workflow(root: Path) -> bool:
    templates = _find_templates_dir(root)
    src = templates / "github-workflows" / "edpa-contribution-sync.yml"
    if not src.exists():
        warn(f"CI workflow template missing — skipping ({src})")
        return False
    dst_dir = root / ".github" / "workflows"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "edpa-contribution-sync.yml"
    if dst.exists():
        info(f"{dst.relative_to(root)} already present — leaving as-is")
        return True
    shutil.copy(src, dst)
    ok(f"Copied CI workflow → {dst.relative_to(root)}")
    info("PR signals will be materialized into YAML after merge")
    return True


def install_hooks(root: Path) -> bool:
    git_hooks = root / ".git" / "hooks"
    if not git_hooks.exists():
        warn("Not a git repo (no .git/hooks) — skipping hooks install")
        return False
    src_dir = HERE / "hooks"
    if not (src_dir / "pre-commit-id-safety").exists():
        src_dir = root / ".edpa" / "engine" / "scripts" / "hooks"

    installed = []
    # Pre-commit + pre-push: ID safety
    for hook in ("pre-commit", "pre-push"):
        src = src_dir / f"{hook}-id-safety"
        dst = git_hooks / hook
        if src.exists() and not dst.exists():
            shutil.copy(src, dst)
            dst.chmod(0o755)
            installed.append(hook)
    # Post-commit: local evidence emitter (V2.1)
    pc_src = src_dir / "post-commit-evidence"
    pc_dst = git_hooks / "post-commit"
    if pc_src.exists() and not pc_dst.exists():
        shutil.copy(pc_src, pc_dst)
        pc_dst.chmod(0o755)
        installed.append("post-commit")
    if installed:
        ok(f"Installed git hooks: {', '.join(installed)}")
        info("pre-commit/pre-push: filename≡id, no upstream collisions")
        info("post-commit: emit commit_author signals into item evidence[]")
    else:
        info("Hooks already installed or sources missing — no changes")
    return True


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="project_setup",
        description="EDPA V2 project bootstrap (local-only, no gh).",
    )
    parser.add_argument(
        "--with-ci", action="store_true",
        help="Copy edpa-contribution-sync.yml to .github/workflows/",
    )
    parser.add_argument(
        "--with-hooks", action="store_true",
        help="Install pre-commit + pre-push ID safety hooks into .git/hooks/",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Project root (default: walk up from CWD to .git/)",
    )
    args = parser.parse_args()

    root = args.root.resolve() if args.root else find_repo_root(Path.cwd())
    print(f"{C.BOLD}EDPA V2 project bootstrap{C.RESET}")
    print(f"Root: {root}")

    step(1, "Directory tree")
    create_directory_tree(root)

    step(2, "Config templates")
    seed_configs(root)

    step(3, "ID counter")
    seed_id_counters(root)

    next_step = 4
    if args.with_ci:
        step(next_step, "CI workflow (--with-ci)")
        install_ci_workflow(root)
        next_step += 1

    if args.with_hooks:
        step(next_step, "Git hooks (--with-hooks)")
        install_hooks(root)

    print(f"\n{C.GREEN}{C.BOLD}EDPA setup complete.{C.RESET}\n")
    print("Next steps:")
    print("  1. Edit .edpa/config/people.yaml — replace example team")
    print("  2. Edit .edpa/config/edpa.yaml — set project.name")
    print("  3. Create your first item:")
    print("       python3 .edpa/engine/scripts/backlog.py add \\")
    print("         --type Initiative --title 'Project Apollo'")
    if not args.with_ci:
        print("  4. (Optional) Enable PR signal materialization:")
        print(f"       python3 {Path(__file__).name} --with-ci --with-hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
