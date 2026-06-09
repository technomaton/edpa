#!/usr/bin/env python3
"""EDPA V2 project bootstrap — local-only, no GitHub provisioning.

Initializes ``.edpa/`` for a new project. Idempotent: safe to re-run.

What it does:
  1. Vendor the engine (scripts + schemas + templates + VERSION) into
     ``.edpa/engine/`` from the plugin, so CI workflows, the documented
     ``.edpa/engine/scripts/*.py`` CLI, and non-Claude-Code tools all
     resolve. Mirrors ``install.sh``; no-op when already running from the
     vendored copy.
  2. Create directory tree (config, backlog/*, iterations, reports, …).
  3. Seed ``.edpa/config/people.yaml`` + ``.edpa/config/edpa.yaml`` from
     ``plugin/edpa/templates/*.tmpl`` if missing (idempotent).
  4. Seed ``.edpa/config/id_counters.yaml`` from existing file IDs.
  5. Optionally copy the CI workflow template (``--with-ci``) to
     ``.github/workflows/edpa-contribution-sync.yml`` so the engine
     can read PR signals materialized from PR events.
  6. Optionally install git hooks (``--with-hooks``) — pre-commit + pre-push
     ID safety, commit-msg ticket-attached, post-commit local-evidence. Detects
     lefthook (prints a paste-ready snippet instead of clobbering .git/hooks/),
     warns on foreign hooks, and is idempotent. ``--refresh-hooks`` re-registers
     only; ``--check-hooks`` is a read-only doctor.

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

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import json
import re
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
    # Disable ANSI when stdout isn't a TTY (CI, the SessionStart auto-update
    # self-heal path) so escape codes don't leak into captured output.
    _tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    RESET = "\033[0m" if _tty else ""
    BOLD = "\033[1m" if _tty else ""
    DIM = "\033[2m" if _tty else ""
    GREEN = "\033[32m" if _tty else ""
    YELLOW = "\033[33m" if _tty else ""
    CYAN = "\033[36m" if _tty else ""
    RED = "\033[31m" if _tty else ""


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


def _plugin_version(plugin_edpa: Path) -> str | None:
    """Pinned plugin version from <PLUGIN_ROOT>/.claude-plugin/plugin.json."""
    pj = plugin_edpa.parent / ".claude-plugin" / "plugin.json"
    if pj.exists():
        try:
            return json.loads(pj.read_text(encoding="utf-8"))["version"]
        except (ValueError, KeyError):
            return None
    return None


def vendor_engine(root: Path) -> bool:
    """Copy the plugin engine into ``.edpa/engine/`` so CI workflows, the
    documented ``.edpa/engine/scripts/*.py`` CLI, and non-Claude-Code tools
    all resolve. Mirrors install.sh's vendor step for the ``/edpa:setup``
    path — restores vendoring the CC path lost when the engine moved from
    ``.claude/edpa/`` to ``.edpa/engine/`` (only install.sh was rewired).

    No-op when project_setup.py is already running from the vendored copy
    (``HERE`` == ``<root>/.edpa/engine/scripts``) — nothing to copy.
    """
    src = HERE.parent                    # plugin's edpa/ dir (scripts/schemas/templates)
    target = root / ".edpa" / "engine"
    if src.resolve() == target.resolve():
        info("Engine already vendored (running from .edpa/engine/) — skipping")
        return False
    if not (src / "scripts").exists():
        warn(f"Engine source not found at {src} — skipping vendor")
        return False
    target.mkdir(parents=True, exist_ok=True)
    # "assets" carries the prebuilt PI planning bundle (pi-bundle.html) that
    # pi_planning.py hydrates — vendored so /edpa:pi-planning works with only
    # Python on the target machine.
    for sub in ("scripts", "schemas", "templates", "assets"):
        s = src / sub
        if s.exists():
            shutil.copytree(s, target / sub, dirs_exist_ok=True)
    # Plugin rules live at plugin/rules (one level above edpa/), NOT
    # edpa/rules — mirror install.sh's "$PLUGIN_SRC/rules" source. Getting
    # this wrong silently skips rules so --with-rules later fails.
    rules_src = src.parent / "rules"
    if rules_src.exists():
        shutil.copytree(rules_src, target / "rules", dirs_exist_ok=True)
    version = _plugin_version(src)
    if version:
        (target / "VERSION").write_text(version + "\n", encoding="utf-8")
    hooks_dir = target / "scripts" / "hooks"
    if hooks_dir.is_dir():
        for f in hooks_dir.iterdir():
            if f.is_file():
                f.chmod(0o755)
    n = len(list((target / "scripts").glob("*.py")))
    ver = f", VERSION {version}" if version else ""
    ok(f"Vendored engine → .edpa/engine/ ({n} scripts{ver})")
    return True


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


def _stamp_methodology(edpa_yaml: Path) -> None:
    """Rewrite governance.methodology to the live plugin version so a freshly
    seeded edpa.yaml never carries the template's frozen version string
    (mirrors install.sh's stamp step)."""
    version = _plugin_version(HERE.parent)
    if not version or not edpa_yaml.exists():
        return
    text = edpa_yaml.read_text(encoding="utf-8")
    new = re.sub(r'(methodology:\s*"?EDPA )[^"\n]+("?)', rf"\g<1>{version}\2", text)
    if new != text:
        edpa_yaml.write_text(new, encoding="utf-8")
        ok(f"Stamped governance.methodology → EDPA {version}")


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
    _stamp_methodology(edpa / "config" / "edpa.yaml")

    # V2.1 C7: seed cw_heuristics.yaml so engine reads the documented
    # defaults (signal weights, gate transitions, yaml_edit weights)
    # from .edpa/config/ instead of falling through to a hardcoded
    # minimum that lacks gate_weights entirely.
    if _seed_one(templates / "cw_heuristics.yaml.tmpl",
                 edpa / "config" / "cw_heuristics.yaml"):
        ok("Seeded .edpa/config/cw_heuristics.yaml (tune weights here)")
    else:
        info("cw_heuristics.yaml already present — leaving as-is")

    (edpa / "sync_state.json").touch()


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


def install_rules(root: Path) -> bool:
    """Copy plugin/rules/*.md into the project's .claude/rules/.

    Claude Code auto-loads files under .claude/rules/ into every agent
    session in that workspace, so this is the supported path for
    distributing architectural rules with a plugin. Idempotent: existing
    files at the destination are not overwritten (so user edits survive
    re-runs).
    """
    src_dir = HERE.parent / "rules"
    if not src_dir.exists():
        src_dir = root / ".edpa" / "engine" / "rules"
    if not src_dir.exists():
        warn(f"Rules source dir missing — skipping ({src_dir})")
        return False
    dst_dir = root / ".claude" / "rules"
    dst_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    skipped: list[str] = []
    for rule in sorted(src_dir.glob("*.md")):
        dst = dst_dir / rule.name
        if dst.exists():
            skipped.append(rule.name)
            continue
        shutil.copy(rule, dst)
        installed.append(rule.name)
    if installed:
        ok(f"Installed rules: {', '.join(installed)} → .claude/rules/")
        info("Auto-loaded into every Claude Code agent session in this repo")
    if skipped:
        info(f"Already present (preserved): {', '.join(skipped)}")
    return True


# ─── Git hook registration ───────────────────────────────────────────────────

EDPA_HOOK_SENTINEL = "EDPA-MANAGED-HOOK"

# git hook name → (vendored source filename, one-line purpose)
_HOOK_SPECS: tuple[tuple[str, str, str], ...] = (
    ("pre-commit", "pre-commit-id-safety",
     "ID safety: staged backlog filename≡id consistency"),
    ("pre-push", "pre-push-id-safety",
     "ID safety: no ID collisions with the remote tip"),
    ("commit-msg", "commit-msg-ticket-attached",
     "require an EDPA item ref (or a 'no-ticket:' escape)"),
    ("post-commit", "post-commit-evidence",
     "emit commit_author evidence into the item's evidence[]"),
)
_HOOK_SRC = {hook: name for hook, name, _ in _HOOK_SPECS}
_HOOK_PURPOSE = {hook: purpose for hook, _, purpose in _HOOK_SPECS}

# Lefthook owns .git/hooks/ — it writes dispatcher shims there (and can set
# core.hooksPath), so any plain copy EDPA drops into .git/hooks/ is ignored or
# clobbered. Presence of a lefthook config is the canonical "managed" signal.
_LEFTHOOK_CONFIGS = (
    "lefthook.yml", "lefthook.yaml", ".lefthook.yml", ".lefthook.yaml",
    "lefthook.toml", "lefthook.json",
)

# Paste-ready lefthook config. pre-push reads its refs on stdin, so its command
# MUST set ``use_stdin: true`` — without it lefthook keeps a pseudo-TTY open and
# hangs the push. {1}/{2} are the args git passes the hook (commit-msg: the
# message file; pre-push: remote name + URL).
LEFTHOOK_SNIPPET = """\
# --- EDPA-managed hooks: paste into lefthook.yml, then run `lefthook install` ---
# Merge these `commands:` under any matching hook keys you already have;
# do not duplicate the top-level hook name.
pre-commit:
  commands:
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety
commit-msg:
  commands:
    edpa-ticket-attached:
      run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}
post-commit:
  commands:
    edpa-evidence:
      run: sh .edpa/engine/scripts/hooks/post-commit-evidence
pre-push:
  commands:
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}
      use_stdin: true
"""


def detect_lefthook(root: Path) -> Path | None:
    """Return the lefthook config path if this repo is managed by lefthook."""
    for name in _LEFTHOOK_CONFIGS:
        p = root / name
        if p.exists():
            return p
    return None


def _hook_src_dir(root: Path) -> Path:
    """Hook sources — plugin layout when running from source, else vendored."""
    src_dir = HERE / "hooks"
    if not (src_dir / "pre-commit-id-safety").exists():
        src_dir = root / ".edpa" / "engine" / "scripts" / "hooks"
    return src_dir


def _is_edpa_owned(path: Path) -> bool:
    """True if an installed hook carries EDPA's sentinel (vs. a foreign hook)."""
    try:
        return EDPA_HOOK_SENTINEL in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def install_hooks(root: Path, *, refresh: bool = False,
                  check_only: bool = False) -> bool:
    """Register EDPA's git hooks robustly.

    Per-hook decision (replaces the old blunt ``not dst.exists()`` guard, which
    silently dropped EDPA hooks whenever any file already held the slot — the
    lefthook collision that stopped contribution evidence from firing):

      * lefthook detected → print the lefthook snippet, leave .git/hooks/ alone
        (lefthook owns it); the user pastes it + runs ``lefthook install``.
      * dst missing       → install (copy + chmod 0755).
      * dst EDPA-owned    → ``refresh`` overwrites with the current version so a
        plugin update propagates hook fixes (update_engine.sh self-heal path);
        otherwise reported as already active.
      * dst foreign       → never touched; loud warning with manual chain-in
        instructions.

    ``check_only`` reports status and writes nothing (the ``--check-hooks``
    doctor). Returns False only when there is no .git/hooks at all.
    """
    git_hooks = root / ".git" / "hooks"
    if not git_hooks.exists():
        warn("Not a git repo (no .git/hooks) — skipping hooks")
        return False

    lefthook_cfg = detect_lefthook(root)
    if lefthook_cfg:
        warn(f"lefthook detected ({lefthook_cfg.name}) — it owns .git/hooks/, "
             f"so EDPA registers via lefthook, not by copying hooks.")
        if not check_only:
            info("EDPA does not edit your lefthook config. Add this block, "
                 "then run `lefthook install`:")
            print()
            print(LEFTHOOK_SNIPPET)
        info("Re-check anytime: python3 .edpa/engine/scripts/project_setup.py "
             "--check-hooks")
        return True

    src_dir = _hook_src_dir(root)
    installed: list[str] = []
    refreshed: list[str] = []
    active: list[str] = []
    missing: list[str] = []
    foreign: list[str] = []
    for hook, src_name, _ in _HOOK_SPECS:
        src = src_dir / src_name
        dst = git_hooks / hook
        if not src.exists():
            continue
        if not dst.exists():
            if check_only:
                missing.append(hook)
            else:
                shutil.copy(src, dst)
                dst.chmod(0o755)
                installed.append(hook)
        elif _is_edpa_owned(dst):
            if not check_only and refresh:
                shutil.copy(src, dst)
                dst.chmod(0o755)
                refreshed.append(hook)
            else:
                active.append(hook)
        else:
            foreign.append(hook)

    if installed:
        ok(f"Installed git hooks: {', '.join(installed)}")
    if refreshed:
        ok(f"Refreshed git hooks: {', '.join(refreshed)}")
    if active:
        (ok if check_only else info)(f"Active EDPA hooks: {', '.join(active)}")
    if missing:
        warn(f"Missing EDPA hooks: {', '.join(missing)} — run "
             f"/edpa:setup --with-hooks")
    for hook in foreign:
        warn(f"{hook}: .git/hooks/{hook} already exists and is NOT EDPA-managed "
             f"— EDPA's hook was NOT installed (skipped, your file untouched).")
        info(f"   purpose not wired: {_HOOK_PURPOSE[hook]}")
        info(f"   chain EDPA in by adding to .git/hooks/{hook}:  "
             f"sh .edpa/engine/scripts/hooks/{_HOOK_SRC[hook]} \"$@\"")
    if not (installed or refreshed or active or missing or foreign):
        info("No EDPA hook sources found (engine not vendored?) — nothing to do")
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
        help="Install pre-commit + commit-msg + post-commit + pre-push hooks "
             "into .git/hooks/ (ID safety + ticket-attached + local evidence)",
    )
    parser.add_argument(
        "--with-rules", action="store_true",
        help="Copy plugin's architectural rules to .claude/rules/ so they "
             "auto-load into every Claude Code session in this repo.",
    )
    parser.add_argument(
        "--refresh-hooks", action="store_true",
        help="Re-register EDPA git hooks only (install missing, refresh "
             "EDPA-owned, warn on foreign / print lefthook snippet). Skips "
             "vendor/seed — used by the auto-update self-heal path.",
    )
    parser.add_argument(
        "--check-hooks", action="store_true",
        help="Report EDPA git hook status (active/missing/foreign/lefthook) "
             "without changing anything — the hooks doctor.",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Project root (default: walk up from CWD to .git/)",
    )
    args = parser.parse_args()

    root = args.root.resolve() if args.root else find_repo_root(Path.cwd())

    # Hook-only fast paths. They skip vendor/seed so they are cheap and safe to
    # call on every session start (update_engine.sh self-heal) or on demand
    # (the --check-hooks doctor). check_only wins if both are passed.
    if args.check_hooks or args.refresh_hooks:
        print(f"{C.BOLD}EDPA git hooks{C.RESET}  (root: {root})")
        install_hooks(root, refresh=args.refresh_hooks,
                      check_only=args.check_hooks)
        return 0

    print(f"{C.BOLD}EDPA V2 project bootstrap{C.RESET}")
    print(f"Root: {root}")

    step(1, "Vendor engine")
    vendor_engine(root)

    step(2, "Directory tree")
    create_directory_tree(root)

    step(3, "Config templates")
    seed_configs(root)

    step(4, "ID counter")
    seed_id_counters(root)

    next_step = 5
    if args.with_ci:
        step(next_step, "CI workflow (--with-ci)")
        install_ci_workflow(root)
        next_step += 1

    if args.with_hooks:
        step(next_step, "Git hooks (--with-hooks)")
        install_hooks(root, refresh=True)
        next_step += 1

    if args.with_rules:
        step(next_step, "Architectural rules (--with-rules)")
        install_rules(root)

    print(f"\n{C.GREEN}{C.BOLD}EDPA setup complete.{C.RESET}\n")
    print("Next steps:")
    print("  1. Edit .edpa/config/people.yaml — replace example team")
    print("  2. Edit .edpa/config/edpa.yaml — set project.name")
    print("  3. Create your first item:")
    print("       python3 .edpa/engine/scripts/backlog.py add \\")
    print("         --type Initiative --title 'Project Apollo'")
    if not (args.with_ci and args.with_hooks and args.with_rules):
        print("  4. (Recommended) Enable full local-first attribution:")
        print(f"       python3 {Path(__file__).name} "
              f"--with-ci --with-hooks --with-rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
