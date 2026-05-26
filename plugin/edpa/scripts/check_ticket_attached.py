#!/usr/bin/env python3
"""Block commits that don't reference an EDPA backlog item (commit-msg hook).

V2.1 Krok C4 — architectural rule: every commit should be attributable
to a tracked piece of work in `.edpa/backlog/`. This hook enforces it
at commit time, before the post-commit ``local_evidence.py`` would
silently emit nothing.

Pass conditions (any one is enough):
  1. Subject or body contains an EDPA item ID (regex ``[A-Z]{1,3}-\\d+``).
  2. Subject starts with an explicit escape hatch:
       ``no-ticket:`` / ``[no-ticket]`` / ``WIP:`` / ``wip:``
     (The escape stays in the commit msg as audit trail in git log.)
  3. Subject starts with an auto-generated prefix:
       ``chore(evidence):``    (local_evidence follow-up)
       ``chore(ci-materialization):``  (sync_pr_contributions follow-up)
       ``Merge``               (merge commit)
       ``Revert``              (revert commit)
       ``Initial commit``      (git's default)
  4. Diff is empty (e.g. amend with no changes).
  5. All staged files are "operational" — not real work:
       - root-level dotfiles (``.gitignore``, ``.editorconfig``, …)
       - top-level config (``package.json``, ``LICENSE``, ``CHANGELOG.md``…)
       - ``.github/`` configuration

Fail otherwise. The user can:
  - rewrite the message with an item ID (`git commit --amend`)
  - opt out explicitly with the ``no-ticket:`` prefix
  - or, if truly orphan work, create a ticket first via /edpa:add

Usage (typically called by .git/hooks/commit-msg, not by humans):
    python3 .edpa/engine/scripts/check_ticket_attached.py <COMMIT_EDITMSG path>

Disable entirely with: export EDPA_NO_TICKET_CHECK=1
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_ITEM_REF_RE = re.compile(r"\b[A-Z]{1,3}-\d{1,9}\b")

_ESCAPE_PREFIXES = (
    "no-ticket:",
    "[no-ticket]",
    "WIP:", "wip:",
)
_AUTO_PREFIXES = (
    "chore(evidence):",
    "chore(ci-materialization):",
    "Merge ",
    "Merge branch",
    "Merge pull request",
    "Revert ",
    'Revert "',
    "Initial commit",
    "fixup!", "squash!",  # autosquash markers
)

# Operational files that don't represent backlog-tracked work.
_OPERATIONAL_PATHS = frozenset({
    "LICENSE", "LICENSE.md", "NOTICE",
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md",
    ".gitignore", ".gitattributes", ".editorconfig",
    "package.json", "package-lock.json",
    "pyproject.toml", "setup.py", "requirements.txt",
})
_OPERATIONAL_DIR_PREFIXES = (
    ".github/",
    ".vscode/",
    ".idea/",
)

ENV_DISABLE = "EDPA_NO_TICKET_CHECK"


def _git(args: list[str]) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _staged_paths() -> list[str]:
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [p for p in (out or "").splitlines() if p]


def _is_operational(path: str) -> bool:
    if path in _OPERATIONAL_PATHS:
        return True
    for prefix in _OPERATIONAL_DIR_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_auto_or_escape(subject: str) -> bool:
    return any(subject.startswith(p) for p in (_AUTO_PREFIXES + _ESCAPE_PREFIXES))


def check_message(msg: str, staged: list[str]) -> tuple[bool, str]:
    """Return (passes, reason)."""
    # Strip git-added comment lines (anything starting with #).
    lines = [ln for ln in msg.splitlines() if not ln.startswith("#")]
    clean = "\n".join(lines).strip()
    subject = lines[0].strip() if lines else ""

    if _is_auto_or_escape(subject):
        return True, "auto-prefix or escape hatch in subject"

    if _ITEM_REF_RE.search(clean):
        return True, "item ID found in message"

    if not staged:
        return True, "empty diff"

    if all(_is_operational(p) for p in staged):
        return True, "only operational paths staged"

    return False, (
        "non-trivial staged changes but no EDPA item ID and no escape "
        "hatch in commit subject"
    )


def main() -> int:
    if os.environ.get(ENV_DISABLE) == "1":
        return 0

    if len(sys.argv) < 2:
        # Without arg fall back to .git/COMMIT_EDITMSG via git rev-parse
        toplevel = _git(["rev-parse", "--show-toplevel"])
        if not toplevel:
            return 0
        msg_path = Path(toplevel.strip()) / ".git" / "COMMIT_EDITMSG"
    else:
        msg_path = Path(sys.argv[1])

    if not msg_path.exists():
        return 0

    msg = msg_path.read_text(encoding="utf-8")
    staged = _staged_paths()
    passes, reason = check_message(msg, staged)
    if passes:
        return 0

    subject = (msg.splitlines() or [""])[0].strip()
    print("", file=sys.stderr)
    print("✗ EDPA: commit blocked — no item reference detected.", file=sys.stderr)
    print(f"  Subject: {subject!r}", file=sys.stderr)
    print(f"  Reason:  {reason}", file=sys.stderr)
    print(f"  Staged:  {len(staged)} file(s) "
          f"({', '.join(staged[:3])}{'…' if len(staged) > 3 else ''})",
          file=sys.stderr)
    print("", file=sys.stderr)
    print("  Fix options:", file=sys.stderr)
    print("    1. Reference an existing item (recommended):", file=sys.stderr)
    print("         git commit --amend -m 'S-5: implement login flow'",
          file=sys.stderr)
    print("    2. Create a new item first, then reference it:", file=sys.stderr)
    print("         /edpa:add Story 'Login flow' --parent F-1", file=sys.stderr)
    print("         git commit --amend  # then add 'S-N: …' to the msg",
          file=sys.stderr)
    print("    3. Explicit opt-out (logged in commit msg as audit trail):",
          file=sys.stderr)
    print("         git commit --amend -m 'no-ticket: …reason…'", file=sys.stderr)
    print("    4. Hard bypass (NOT recommended):", file=sys.stderr)
    print("         git commit --no-verify  # or EDPA_NO_TICKET_CHECK=1",
          file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
