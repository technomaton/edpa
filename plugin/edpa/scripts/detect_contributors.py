#!/usr/bin/env python3
"""
EDPA Contributor Auto-Detection

Scans a merged PR for evidence signals and updates backlog YAML contributors.
Called by contributor-detect.yml GitHub Action on PR merge.

Evidence signals detected:
  - PR author → key contributor
  - PR reviewers → reviewer
  - Commit authors → reviewer (if different from PR author)
  - Item IDs from branch name and PR title → which backlog items to update

Environment variables (set by GitHub Actions):
  PR_NUMBER, PR_AUTHOR, PR_TITLE, PR_BRANCH, GH_TOKEN
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required")
    sys.exit(1)


def run_gh(args):
    """Run gh CLI command and return JSON output."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"gh error: {result.stderr}")
        return None
    return json.loads(result.stdout) if result.stdout.strip() else None


def extract_item_ids(text):
    """Extract EDPA item IDs (S-200, F-100, E-10, I-1) from text."""
    return re.findall(r'\b([SFEIT]-\d+)\b', text or "")


def find_backlog_file(edpa_root, item_id):
    """Find the YAML file for an item ID."""
    prefix = item_id.split("-")[0]
    type_dirs = {"S": "stories", "F": "features", "E": "epics", "I": "initiatives", "T": "stories"}
    type_dir = type_dirs.get(prefix, "stories")
    path = edpa_root / "backlog" / type_dir / f"{item_id}.yaml"
    if path.exists():
        return path
    # Try all directories
    for d in ["stories", "features", "epics", "initiatives"]:
        p = edpa_root / "backlog" / d / f"{item_id}.yaml"
        if p.exists():
            return p
    return None


def load_people_map(edpa_root):
    """Load people.yaml and create github_login → person_id map."""
    people_path = edpa_root / "config" / "people.yaml"
    if not people_path.exists():
        return {}
    data = yaml.safe_load(people_path.read_text()) or {}
    mapping = {}
    for p in data.get("people", []):
        pid = p.get("id", "")
        email = p.get("email", "")
        name = p.get("name", "")
        github = p.get("github", "")
        if github:
            mapping[github.lower()] = pid
        if email:
            mapping[email.lower()] = pid
        if name:
            mapping[name.lower()] = pid
    return mapping


def update_contributors(yaml_path, new_contributors):
    """Update contributors list in a backlog YAML file.

    Only adds new contributors — never removes existing ones.
    If a contributor already exists with a higher CW, keeps the higher value.
    """
    data = yaml.safe_load(yaml_path.read_text()) or {}
    existing = data.get("contributors", [])

    # Build lookup of existing contributors
    existing_map = {}
    for c in existing:
        existing_map[c["person"]] = c

    changed = False
    for nc in new_contributors:
        person = nc["person"]
        if person in existing_map:
            # Keep existing if higher CW
            if existing_map[person].get("cw", 0) < nc.get("cw", 0):
                existing_map[person]["cw"] = nc["cw"]
                existing_map[person]["role"] = nc["role"]
                changed = True
        else:
            existing.append(nc)
            existing_map[person] = nc
            changed = True

    if changed:
        data["contributors"] = existing
        yaml_path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        return True
    return False


def main():
    pr_number = os.environ.get("PR_NUMBER", "")
    pr_author = os.environ.get("PR_AUTHOR", "")
    pr_title = os.environ.get("PR_TITLE", "")
    pr_branch = os.environ.get("PR_BRANCH", "")

    if not pr_number:
        print("No PR_NUMBER set. Run this from contributor-detect.yml action.")
        sys.exit(1)

    edpa_root = Path(".edpa")
    if not edpa_root.exists():
        print(".edpa/ not found")
        sys.exit(1)

    people_map = load_people_map(edpa_root)
    print(f"People map: {len(people_map)} entries")

    # Extract item IDs from branch name and PR title
    item_ids = set()
    item_ids.update(extract_item_ids(pr_branch))
    item_ids.update(extract_item_ids(pr_title))

    # Also check commit messages
    commits = run_gh(["pr", "view", pr_number, "--json", "commits"])
    if commits:
        for c in commits.get("commits", []):
            msg = c.get("messageHeadline", "") + " " + c.get("messageBody", "")
            item_ids.update(extract_item_ids(msg))

    if not item_ids:
        print("No item IDs found in PR branch, title, or commits")
        return

    print(f"Item IDs: {sorted(item_ids)}")

    # Get PR reviewers
    reviews = run_gh(["pr", "view", pr_number, "--json", "reviews,reviewRequests"])
    reviewer_logins = set()
    if reviews:
        for r in reviews.get("reviews", []):
            login = r.get("author", {}).get("login", "")
            if login and login != pr_author:
                reviewer_logins.add(login)

    # Get commit authors (unique, excluding PR author)
    commit_authors = set()
    if commits:
        for c in commits.get("commits", []):
            for field in ["authors", "committers"]:
                for a in c.get(field, []):
                    login = a.get("login", "")
                    if login and login != pr_author:
                        commit_authors.add(login)

    print(f"PR author: {pr_author}")
    print(f"Reviewers: {reviewer_logins}")
    print(f"Commit authors: {commit_authors}")

    # Resolve logins to person IDs
    def resolve(login):
        return people_map.get(login.lower(), login)

    # Build contributors for each item
    heuristics_path = edpa_root / "config" / "heuristics.yaml"
    if heuristics_path.exists():
        h = yaml.safe_load(heuristics_path.read_text()) or {}
        weights = h.get("role_weights", {})
    else:
        weights = {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15}

    for item_id in sorted(item_ids):
        yaml_path = find_backlog_file(edpa_root, item_id)
        if not yaml_path:
            print(f"  {item_id}: no YAML file found, skipping")
            continue

        new_contributors = []

        # PR author = key contributor
        person_id = resolve(pr_author)
        if person_id:
            new_contributors.append({
                "person": person_id,
                "role": "key",
                "cw": weights.get("key", 0.6),
                "source": f"pr_author:#{pr_number}",
            })

        # Reviewers
        for login in reviewer_logins:
            person_id = resolve(login)
            if person_id:
                new_contributors.append({
                    "person": person_id,
                    "role": "reviewer",
                    "cw": weights.get("reviewer", 0.25),
                    "source": f"pr_reviewer:#{pr_number}",
                })

        # Commit authors (as reviewers — lower signal than PR author)
        for login in commit_authors:
            person_id = resolve(login)
            if person_id:
                new_contributors.append({
                    "person": person_id,
                    "role": "reviewer",
                    "cw": weights.get("reviewer", 0.25),
                    "source": f"commit_author:#{pr_number}",
                })

        if new_contributors:
            updated = update_contributors(yaml_path, new_contributors)
            status = "updated" if updated else "unchanged"
            print(f"  {item_id}: {len(new_contributors)} contributors → {status}")
        else:
            print(f"  {item_id}: no contributors to add")


if __name__ == "__main__":
    main()
