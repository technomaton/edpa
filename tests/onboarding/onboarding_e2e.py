#!/usr/bin/env python3
"""EDPA onboarding E2E harness — fresh-repo sandbox, both install paths.

Drives a brand-new (throwaway) git repo through EDPA's two onboarding paths
and asserts the engine-vendoring outcome. All checks are OFFLINE and use
auto-cleaned temp repos — no network, no GitHub, no writes outside /tmp.

Run with the interpreter that has pexpect (miniconda on this machine):

    /opt/miniconda3/bin/python3 tests/onboarding/onboarding_e2e.py
    /opt/miniconda3/bin/python3 tests/onboarding/onboarding_e2e.py --keep

Checks:

  A. install.sh vendor mechanic (control)  → .edpa/engine/scripts/*.py PRESENT
  B. /edpa:setup mechanic (project_setup)  → .edpa/engine/ ... (currently MISSING)
     The skill's Step 1 runs only project_setup.py, which never copies the
     engine. This assertion FAILS today and documents the onboarding gap.
  C. install.sh overwrite prompt           → driven interactively via pexpect
  D. SessionStart hook on fresh repo        → skips (cannot bootstrap an engine)
  E. SessionStart hook on stale engine      → re-vendors (maintenance only)

Exit 0 only if every assertion holds. A failing Path B means the gap between
the skill's promise ("Vendors the engine into .edpa/engine/") and its actual
Step 1 is still present.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import pexpect
except ImportError:
    sys.exit(
        "pexpect not importable by this interpreter.\n"
        "Re-run with the one that has it (miniconda):\n"
        f"  /opt/miniconda3/bin/python3 {__file__}"
    )

# ─── Paths (harness lives at tests/onboarding/ → repo root is parents[2]) ────
REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
PLUGIN_EDPA = PLUGIN / "edpa"
INSTALL_SH = REPO / "install.sh"
PROJECT_SETUP = PLUGIN_EDPA / "scripts" / "project_setup.py"
UPDATE_ENGINE_SH = PLUGIN_EDPA / "scripts" / "hooks" / "update_engine.sh"
PLUGIN_VERSION = json.loads(
    (PLUGIN / ".claude-plugin" / "plugin.json").read_text()
)["version"]

KEEP = "--keep" in sys.argv


class C:
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    GRN = "\033[32m"; RED = "\033[31m"; YEL = "\033[33m"; CYN = "\033[36m"


results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    tag = f"{C.GRN}PASS{C.R}" if ok else f"{C.RED}FAIL{C.R}"
    print(f"  [{tag}] {name}")
    for line in detail.splitlines():
        print(f"         {C.DIM}{line}{C.R}")


def new_sandbox(label: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"edpa-onb-{label}-"))
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=d, check=True)
    return d


def cleanup(d: Path) -> None:
    if KEEP:
        print(f"         {C.DIM}(kept: {d}){C.R}")
    else:
        shutil.rmtree(d, ignore_errors=True)


def has_py(p: Path) -> bool:
    return p.is_dir() and any(p.glob("*.py"))


# ─── A. install.sh vendor mechanic (control) ────────────────────────────────
def check_install_sh_vendors() -> None:
    sb = new_sandbox("install")
    try:
        engine = sb / ".edpa" / "engine"
        engine.mkdir(parents=True)
        # Replicates install.sh:154-169 against the LOCAL working tree.
        for sub in ("scripts", "schemas", "templates"):
            shutil.copytree(PLUGIN_EDPA / sub, engine / sub)
        (engine / "VERSION").write_text(PLUGIN_VERSION + "\n")
        n = len(list((engine / "scripts").glob("*.py")))
        record(
            "Path A — install.sh vendor mechanic (control)",
            has_py(engine / "scripts"),
            f"replicated install.sh:154-169 → .edpa/engine/scripts/ has {n} *.py",
        )
    finally:
        cleanup(sb)


# ─── B. /edpa:setup mechanic — the gap ──────────────────────────────────────
def check_setup_skill_vendors() -> None:
    sb = new_sandbox("setup")
    try:
        # Exactly what plugin/skills/edpa-setup/SKILL.md Step 1 runs, with
        # ${CLAUDE_PLUGIN_ROOT} resolved to the real plugin path.
        proc = subprocess.run(
            [sys.executable, str(PROJECT_SETUP),
             "--with-ci", "--with-hooks", "--with-rules"],
            cwd=sb, capture_output=True, text=True,
        )
        engine_scripts = sb / ".edpa" / "engine" / "scripts"
        backlog = engine_scripts / "backlog.py"   # skill Step 3 target
        tail = "\n".join(proc.stdout.strip().splitlines()[-2:])
        step3 = "resolves" if backlog.exists() else "WOULD FAIL — file absent"
        record(
            "Path B — /edpa:setup vendors the engine",
            has_py(engine_scripts),
            f"project_setup.py exit={proc.returncode}; "
            f".edpa/engine/scripts present={engine_scripts.is_dir()}; "
            f"backlog.py present={backlog.exists()}\n"
            f"→ skill Step 3 'python3 .edpa/engine/scripts/backlog.py add' {step3}\n"
            f"last output: {tail}",
        )
    finally:
        cleanup(sb)


# ─── C. install.sh overwrite prompt, driven via pexpect ─────────────────────
def check_install_prompt() -> None:
    sb = new_sandbox("prompt")
    try:
        marker = sb / ".edpa" / "engine" / "MARKER"
        marker.parent.mkdir(parents=True)
        marker.write_text("preexisting\n")
        env = dict(os.environ)
        env.pop("EDPA_FORCE_INSTALL", None)
        child = pexpect.spawn(
            "sh", [str(INSTALL_SH)], cwd=str(sb),
            encoding="utf-8", timeout=30, env=env,
        )
        steps = []
        child.expect(r"Overwrite\? \[y/N\]")
        steps.append("saw prompt: 'Overwrite? [y/N]'")
        child.sendline("n")
        child.expect("Aborted")
        steps.append("sent 'n' → 'Aborted.'")
        child.expect(pexpect.EOF)
        child.close()
        intact = marker.exists()
        record(
            "install.sh overwrite prompt (driven via pexpect, offline)",
            child.exitstatus == 1 and intact,
            "\n".join(steps)
            + f"\nexit={child.exitstatus}; engine untouched on abort={intact}",
        )
    finally:
        cleanup(sb)


# ─── D. SessionStart hook on a fresh repo → skips ───────────────────────────
def check_hook_skips_fresh() -> None:
    sb = new_sandbox("hookfresh")
    try:
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
        proc = subprocess.run(
            ["sh", str(UPDATE_ENGINE_SH)], cwd=sb,
            capture_output=True, text=True, env=env,
        )
        absent = not (sb / ".edpa" / "engine").exists()
        record(
            "SessionStart hook on fresh repo → skips (cannot bootstrap)",
            proc.returncode == 0 and absent,
            f"exit={proc.returncode}; .edpa/engine still absent={absent}\n"
            f"confirms update_engine.sh skip #2 — never creates a missing engine",
        )
    finally:
        cleanup(sb)


# ─── E. SessionStart hook on a stale engine → re-vendors ────────────────────
def check_hook_updates_existing() -> None:
    sb = new_sandbox("hookstale")
    try:
        engine = sb / ".edpa" / "engine"
        (engine / "scripts").mkdir(parents=True)
        (engine / "VERSION").write_text("0.0.0\n")
        cfg = sb / ".edpa" / "config"
        cfg.mkdir(parents=True)
        (cfg / "edpa.yaml").write_text("governance:\n  methodology: EDPA 0.0.0\n")
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
        proc = subprocess.run(
            ["sh", str(UPDATE_ENGINE_SH)], cwd=sb,
            capture_output=True, text=True, env=env,
        )
        new_version = (engine / "VERSION").read_text().strip()
        last_err = (proc.stderr.strip().splitlines() or [""])[-1]
        record(
            "SessionStart hook on stale engine → re-vendors (maintenance only)",
            proc.returncode == 0
            and new_version == PLUGIN_VERSION
            and has_py(engine / "scripts"),
            f"exit={proc.returncode}; VERSION 0.0.0 → {new_version} "
            f"(plugin={PLUGIN_VERSION}); scripts/*.py now present="
            f"{has_py(engine / 'scripts')}\nstderr: {last_err}",
        )
    finally:
        cleanup(sb)


def main() -> int:
    for p in (INSTALL_SH, PROJECT_SETUP, UPDATE_ENGINE_SH):
        if not p.exists():
            sys.exit(f"missing expected file: {p}")
    print(f"{C.B}EDPA onboarding E2E — fresh-repo sandbox "
          f"(plugin {PLUGIN_VERSION}){C.R}")
    print(f"{C.DIM}interpreter: {sys.executable}{C.R}\n")

    check_install_sh_vendors()
    check_setup_skill_vendors()
    check_install_prompt()
    check_hook_skips_fresh()
    check_hook_updates_existing()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{C.B}Summary: {passed}/{len(results)} checks passed{C.R}")
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print(f"\n{C.RED}{C.B}Onboarding gap reproduced:{C.R}")
        for n in failed:
            print(f"  {C.RED}✗{C.R} {n}")
        print(f"\n{C.YEL}Root cause:{C.R} plugin/skills/edpa-setup/SKILL.md Step 1 runs only")
        print("  project_setup.py, which never copies plugin/edpa/{scripts,schemas,")
        print("  templates} → .edpa/engine/. The skill's description + layout diagram")
        print("  both claim it vendors. Only curl|sh install.sh vendors; the")
        print("  SessionStart hook can't bootstrap a missing engine (skip #2).")
        print(f"\n{C.YEL}Fix options:{C.R}")
        print("  1. Add a vendor step to SKILL.md Step 1 (cp -R is in allowed-tools), or")
        print("  2. Make project_setup.py vendor the engine when run from the plugin.")
        return 1
    print(f"{C.GRN}All onboarding paths healthy.{C.R}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
