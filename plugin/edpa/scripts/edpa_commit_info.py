#!/usr/bin/env python3
"""
EDPA Commit Info — generates structured JSON after a git commit.

Reads the latest commit and produces edpa-commit-info/1.0 schema output
for Claude Code post-commit hooks.

Usage:
    python edpa_commit_info.py

Output (stdout): JSON object with schema edpa-commit-info/1.0
"""

import json
import re
import subprocess
from datetime import datetime, timezone


def git(*args):
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def extract_item_refs(text):
    """Extract EDPA work item references (S-123, F-45, E-7, etc.) from text."""
    if not text:
        return []
    return sorted(set(re.findall(r'[SFEIATB]-\d+', text)))


def get_changed_edpa_files(diff_output):
    """Identify .edpa/ files in a diff."""
    edpa_files = []
    for line in diff_output.splitlines():
        if line.startswith(("A\t", "M\t", "D\t")):
            path = line.split("\t", 1)[1]
            if path.startswith(".edpa/"):
                edpa_files.append(path)
    return edpa_files


def main():
    try:
        # Get latest commit info (single git-log call for all fields)
        log_line = git("log", "-1", "--format=%H%n%s%n%an%n%ae")
        commit_hash, commit_msg, commit_author, commit_email = log_line.split("\n", 3)
        branch = git("rev-parse", "--abbrev-ref", "HEAD")

        # Get changed files
        diff_output = git("diff-tree", "--no-commit-id", "-r", "--name-status", "HEAD")
        edpa_files = get_changed_edpa_files(diff_output)

        # Extract item references from commit message
        item_refs = extract_item_refs(commit_msg)

        # Count files changed
        files_changed = len([l for l in diff_output.splitlines() if l.strip()])

        info = {
            "schema": "edpa-commit-info/1.0",
            "commit": commit_hash[:12],
            "branch": branch,
            "author": commit_author,
            "email": commit_email,
            "message": commit_msg,
            "item_refs": item_refs,
            "edpa_files_changed": edpa_files,
            "files_changed": files_changed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        print(json.dumps(info, indent=2))

    except subprocess.TimeoutExpired:
        print(json.dumps({"schema": "edpa-commit-info/1.0", "error": "git timeout"}))
    except Exception as e:
        print(json.dumps({"schema": "edpa-commit-info/1.0", "error": str(e)}))


if __name__ == "__main__":
    main()
