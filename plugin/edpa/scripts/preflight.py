#!/usr/bin/env python3
"""
EDPA preflight — readiness check for project_setup.py and pilot kickoff.

Ports docs/kashealth-pilot/preflight.sh to Python with auto-fix offers.
Usable in three ways:

    # 1. Standalone preflight from /edpa:setup --check-only
    python3 plugin/edpa/scripts/preflight.py --org kashealth

    # 2. As Stage 0 inside project_setup.py — caller imports run_preflight()

    # 3. CI / scripted runs
    python3 plugin/edpa/scripts/preflight.py --org kashealth --non-interactive

Exit codes:
    0  — every check OK (warnings allowed unless --strict)
    1  — at least one ERROR (caller should not proceed)
    2  — preflight itself failed (gh missing, network, etc.)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_TYPES = ["Initiative", "Epic", "Feature", "Story", "Defect", "Task"]
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


def _run(cmd, capture=True):
    """Run shell cmd; return (rc, stdout). Never raises."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, timeout=30
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as e:
        return -1, str(e)


def _confirm(prompt, default_yes=False, non_interactive=False, auto_fix=False):
    """Prompt y/N; return True/False. Honors --auto-fix and --non-interactive."""
    if auto_fix:
        return True
    if non_interactive:
        return False
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        ans = input(f"    {_c('?', C.HEAD)} {prompt} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not ans:
        return default_yes
    return ans in ("y", "yes")


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
    rc, out = _run("gh auth status")
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
    rc, out = _run(f"gh api orgs/{org}/members")
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
    rc, out = _run(f"gh repo view {org}/{repo} --json name,defaultBranchRef,visibility")
    if rc != 0 or '"name"' not in out:
        r.err(f"{org}/{repo} not accessible",
              "check that the repo exists and your token has read access")
        return
    try:
        info = json.loads(out)
        ok(f"{org}/{repo} ({info['visibility']}, default={info['defaultBranchRef']['name']})")
    except (ValueError, KeyError):
        r.warn(f"{org}/{repo} accessible but metadata parse failed")


def check_issue_types(r: Result, org: str, non_interactive: bool, auto_fix: bool):
    step(5, "Org-level Issue Types")
    query = (
        f"{{ organization(login: \\\"{org}\\\") "
        "{ issueTypes(first: 20) { nodes { name } } } }"
    )
    rc, out = _run(f"gh api graphql -f query=\"{query}\"")
    if rc != 0:
        r.err("Could not query org Issue Types (GraphQL failed)",
              "gh api graphql -f query='...issueTypes...' to debug")
        return
    try:
        data = json.loads(out)
        nodes = data["data"]["organization"]["issueTypes"]["nodes"]
        present = [n["name"] for n in nodes]
    except (ValueError, KeyError, TypeError):
        r.err("Could not parse issueTypes response")
        return

    missing = [t for t in EXPECTED_TYPES if t not in present]
    for t in EXPECTED_TYPES:
        if t in present:
            ok(f"Issue Type: {t}")
        else:
            print(f"  {_c('✗', C.ERR)} Issue Type missing: {t}")

    if missing:
        fix_cmd = f"python3 {Path(__file__).resolve()} setup --org {org}"
        # The script ships alongside issue_types.py so use that:
        types_script = Path(__file__).parent / "issue_types.py"
        fix_cmd = f"python3 {types_script} setup --org {org}"
        msg = (
            f"{len(missing)} Issue Type(s) missing: {', '.join(missing)}. "
            "EDPA setup will fail with a cryptic GraphQL error if these "
            "are not created first."
        )
        print(f"    {_c('fix:', C.DIM)} {fix_cmd}")
        if _confirm("Run issue_types.py setup now?", default_yes=True,
                    non_interactive=non_interactive, auto_fix=auto_fix):
            print()
            rc, out = _run(f"python3 {types_script} setup --org {org}", capture=False)
            if rc == 0:
                ok("Issue Types created")
                r.fixes_applied.append("issue_types.setup")
            else:
                r.err("issue_types.py setup failed; resolve manually before retrying")
        else:
            r.err(msg)


def check_git_config(r: Result):
    step(6, "Local git config")
    rc, top = _run("git rev-parse --show-toplevel")
    if rc != 0:
        r.warn("Not inside a git repo (preflight is more informative inside a repo)")
        return
    ok(f"Inside git repo: {top.strip()}")
    rc_n, name = _run("git config user.name")
    rc_e, email = _run("git config user.email")
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
    step(7, f"people.yaml github logins vs {org} org members")
    try:
        import yaml
    except ImportError:
        r.warn("yaml module missing; skipping people.yaml cross-check")
        return
    try:
        data = yaml.safe_load(open(people_path))
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
    """Run all preflight checks. Returns exit-code-style int (0/1/2)."""
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

    if org and r.errors == 0:
        check_issue_types(r, org, non_interactive=non_interactive, auto_fix=auto_fix)

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


def main():
    parser = argparse.ArgumentParser(
        description="EDPA preflight — readiness check before project_setup.py"
    )
    parser.add_argument("--org", help="GitHub organization (enables org checks)")
    parser.add_argument("--repo", help="Repository name (requires --org)")
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
