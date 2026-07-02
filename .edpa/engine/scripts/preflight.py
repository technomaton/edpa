#!/usr/bin/env python3
"""
EDPA preflight — readiness check for project_setup.py and pilot kickoff.

Ports docs/kashealth-pilot/preflight.sh to Python. Standalone CLI — no code
imports it; run it directly (documented in plugin/README.md for Cursor /
Codex / raw installs):

    python3 .edpa/engine/scripts/preflight.py --org kashealth

    # CI / scripted runs
    python3 .edpa/engine/scripts/preflight.py --org kashealth --non-interactive

Exit codes:
    0  — every check OK (warnings allowed unless --strict)
    1  — at least one ERROR (caller should not proceed)
    2  — bad usage (argparse: invalid --org/--repo value, unknown flag)
"""

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_SCOPES = ["admin:org", "project", "repo", "workflow"]
REQUIRED_PY_MODULES = ["yaml", "openpyxl"]
OPTIONAL_PY_MODULES = ["mcp"]


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


def _c(text, code):
    return f"{code}{text}{C.RESET}" if _isatty() else text


def step(num, title):
    print(f"\n{_c(f'[{num}]', C.HEAD)} {title}")


def ok(msg):
    print(f"  {_c('✓', C.OK)} {msg}")


def warn(msg, fix=None):
    print(f"  {_c('⚠', C.WARN)} {msg}")
    if fix:
        print(f"    {_c('fix:', C.DIM)} {fix}")


def fail(msg, fix=None):
    print(f"  {_c('✗', C.ERR)} {msg}")
    if fix:
        print(f"    {_c('fix:', C.DIM)} {fix}")


def _run(args, capture=True):
    """Run an argv list (never a shell string); return (rc, stdout+stderr).

    Never raises. list-argv + shell=False means user-supplied values
    (--org/--repo) and computed paths are passed as single arguments —
    no metacharacter injection, no quoting bugs on paths with spaces (D-42).
    """
    try:
        result = subprocess.run(
            args, capture_output=capture, text=True, timeout=30, encoding="utf-8"
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as e:
        return -1, str(e)


# -- Individual checks --------------------------------------------------------


class Result:
    def __init__(self):
        self.errors = 0
        self.warnings = 0
        self.fixes_applied = []

    def err(self, msg, fix=None):
        fail(msg, fix)
        self.errors += 1

    def warn(self, msg, fix=None):
        warn(msg, fix)
        self.warnings += 1


def check_toolchain(r: Result):
    step(1, "Toolchain")
    for cmd in ("python3", "git", "gh"):
        path = shutil.which(cmd)
        if path:
            ok(f"{cmd}: {path}")
        else:
            r.err(f"{cmd} not on PATH", f"install {cmd}")

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 10):
        ok(f"Python {py_version} (>= 3.10)")
    else:
        r.err(f"Python {py_version} (need >= 3.10)")

    for mod in REQUIRED_PY_MODULES:
        try:
            __import__(mod)
            ok(f"Python module: {mod}")
        except ImportError:
            r.warn(f"Python module {mod} missing",
                   f"pip3 install {mod} --break-system-packages")
    for mod in OPTIONAL_PY_MODULES:
        try:
            __import__(mod)
            ok(f"Python module: {mod} (optional)")
        except ImportError:
            print(f"  {_c('·', C.DIM)} {mod} not installed (optional, MCP only)")


def check_gh_auth(r: Result):
    step(2, "GitHub CLI authentication")
    rc, out = _run(["gh", "auth", "status"])
    if "Logged in to github.com" not in out:
        r.err("gh not authenticated", "gh auth login")
        return
    user = ""
    for line in out.splitlines():
        if "account " in line:
            parts = line.split("account ", 1)[1].split()
            if parts:
                user = parts[0]
                break
    ok(f"Authenticated as: {user or '<unknown>'}")

    scopes_line = ""
    for line in out.splitlines():
        if "Token scopes" in line:
            scopes_line = line
            break
    for scope in EXPECTED_SCOPES:
        if scope in scopes_line:
            ok(f"scope: {scope}")
        else:
            r.err(f"scope missing: {scope}",
                  f"gh auth refresh -h github.com -s {scope}")


def check_org_access(r: Result, org: str):
    step(3, f"Org access ({org})")
    rc, out = _run(["gh", "api", f"orgs/{org}/members"])
    if rc != 0:
        r.err(f"Cannot list members of {org}",
              f"check that you are a member of {org} org")
        return []
    try:
        members = [m["login"] for m in json.loads(out)]
    except (ValueError, KeyError):
        r.err(f"Could not parse member list for {org}")
        return []
    if not members:
        r.warn(f"{org} has 0 members visible to your token")
        return []
    ok(f"{org} members ({len(members)}): {', '.join(members)}")
    return members


def check_repo(r: Result, org: str, repo: str):
    step(4, f"Target repo ({org}/{repo})")
    rc, out = _run(["gh", "repo", "view", f"{org}/{repo}",
                    "--json", "name,defaultBranchRef,visibility"])
    if rc != 0 or '"name"' not in out:
        r.err(f"{org}/{repo} not accessible",
              "check that the repo exists and your token has read access")
        return
    try:
        info = json.loads(out)
        ok(f"{org}/{repo} ({info['visibility']}, default={info['defaultBranchRef']['name']})")
    except (ValueError, KeyError):
        r.warn(f"{org}/{repo} accessible but metadata parse failed")


def check_git_config(r: Result):
    step(5, "Local git config")
    rc, top = _run(["git", "rev-parse", "--show-toplevel"])
    if rc != 0:
        r.warn("Not inside a git repo (preflight is more informative inside a repo)")
        return
    ok(f"Inside git repo: {top.strip()}")
    rc_n, name = _run(["git", "config", "user.name"])
    rc_e, email = _run(["git", "config", "user.email"])
    name = name.strip()
    email = email.strip()
    if name and email:
        ok(f"git user.name + user.email: {name} <{email}>")
    else:
        r.err("git user.name / user.email not set "
              "(EDPA auto-commit feature in v1.8.1+ silently skips otherwise)",
              "git config --global user.email 'you@example.com' "
              "&& git config --global user.name 'Your Name'")


def check_people_yaml_members(r: Result, org: str, org_members: list,
                              people_path: Path):
    if not people_path.exists():
        return  # not yet seeded; not a preflight concern at Stage 0
    step(6, f"people.yaml github logins vs {org} org members")
    try:
        import yaml
    except ImportError:
        r.warn("yaml module missing; skipping people.yaml cross-check")
        return
    try:
        data = yaml.safe_load(open(people_path, encoding="utf-8"))
    except Exception as e:
        r.warn(f"Could not parse {people_path}: {e}")
        return
    declared = []
    for entry in (data or {}).get("people", []) or []:
        gh = (entry.get("github") or "").strip()
        if gh:
            declared.append(gh)
    if not declared:
        ok(f"{people_path.name} has no github logins to verify (skipping)")
        return
    org_set = set(org_members)
    missing = [g for g in declared if g not in org_set]
    if not missing:
        ok(f"All {len(declared)} declared github logins are org members")
    else:
        r.warn(
            f"{len(missing)} declared github login(s) not in org: "
            f"{', '.join(missing)}",
            "fix the github: field in .edpa/config/people.yaml or "
            "invite them to the org"
        )


# -- Public API ---------------------------------------------------------------


def run_preflight(*, org: str | None = None, repo: str | None = None,
                  people_yaml: Path | None = None, non_interactive: bool = False,
                  auto_fix: bool = False, strict: bool = False) -> int:
    """Run all preflight checks. Returns exit-code-style int (0/1).

    ``non_interactive`` / ``auto_fix`` are accepted for CLI stability; since
    the V1 org Issue-Types check was removed (D-42), no check prompts or
    offers auto-fixes, so both are currently no-ops.
    """
    del non_interactive, auto_fix  # compat only — no prompts remain (D-42)
    r = Result()

    print(_c("EDPA preflight", C.BOLD))
    if org:
        print(f"  org:  {org}")
    if repo:
        print(f"  repo: {org}/{repo}" if org else f"  repo: {repo}")

    check_toolchain(r)
    check_gh_auth(r)

    org_members = []
    if org:
        if r.errors == 0:
            org_members = check_org_access(r, org)
        else:
            print(f"\n{_c('skipping org checks — earlier failures must be resolved first', C.DIM)}")

    if org and repo and r.errors == 0:
        check_repo(r, org, repo)

    check_git_config(r)

    if people_yaml is None:
        people_yaml = Path(".edpa/config/people.yaml")
    if org and org_members:
        check_people_yaml_members(r, org, org_members, people_yaml)

    print()
    if r.errors:
        print(_c(f"✗ {r.errors} error(s), {r.warnings} warning(s)", C.ERR))
        if r.fixes_applied:
            print(_c(f"  ({len(r.fixes_applied)} auto-fix(es) applied — re-run preflight to confirm)", C.DIM))
        return 1
    if r.warnings and strict:
        print(_c(f"✗ {r.warnings} warning(s) (--strict)", C.WARN))
        return 1
    if r.warnings:
        print(_c(f"✓ ready ({r.warnings} warning(s) — review before kickoff)", C.WARN))
    else:
        print(_c("✓ ready — every check passed", C.OK))
    if r.fixes_applied:
        print(_c(f"  ({len(r.fixes_applied)} auto-fix(es) applied during this run)", C.DIM))
    return 0


_GH_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _gh_name(value: str) -> str:
    """argparse type for --org/--repo: conservative GitHub name charset.

    _run() passes values as single argv elements (no shell), so this is a
    friendly-error guard against typos/metacharacters, not the security
    boundary.
    """
    if not _GH_NAME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"invalid GitHub org/repo name {value!r} "
            "(allowed: letters, digits, '.', '_', '-')"
        )
    return value


def main():
    parser = argparse.ArgumentParser(
        description="EDPA preflight — readiness check before project_setup.py"
    )
    parser.add_argument("--org", type=_gh_name,
                        help="GitHub organization (enables org checks)")
    parser.add_argument("--repo", type=_gh_name,
                        help="Repository name (requires --org)")
    parser.add_argument("--people-yaml", default=".edpa/config/people.yaml",
                        help="Path to people.yaml (default: .edpa/config/people.yaml)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Never prompt; auto-fix offers default to NO")
    parser.add_argument("--auto-fix", action="store_true",
                        help="Apply offered fixes without prompting")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors")
    args = parser.parse_args()

    rc = run_preflight(
        org=args.org,
        repo=args.repo,
        people_yaml=Path(args.people_yaml),
        non_interactive=args.non_interactive,
        auto_fix=args.auto_fix,
        strict=args.strict,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
