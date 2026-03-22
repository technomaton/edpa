#!/usr/bin/env python3
"""
EDPA GitHub Project Setup — Automated initialization of GitHub Projects v2.

Creates a fully configured GitHub Project with:
- Custom fields (Job Size, BV, TC, RR, WSJF Score, Issue Type, Team)
- Issues for all backlog items (from .edpa/backlog.yaml)
- Labels (Initiative, Epic, Feature, Story)
- Field values set on all project items
- Project linked to repository

Usage:
    python scripts/edpa_project_setup.py --org technomaton --repo edpa-simulation
    python scripts/edpa_project_setup.py --org technomaton --repo edpa-simulation --dry-run

Prerequisite:
    gh auth login (with project scope)
    .edpa/backlog.yaml exists with work item hierarchy
"""

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


# ANSI colors
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    GRAY = "\033[38;5;245m"
    PURPLE = "\033[38;5;93m"


def run(cmd, check=True):
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        return None
    return result.stdout.strip()


def gh_graphql(query):
    """Execute GitHub GraphQL query."""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def step(num, text):
    print(f"\n  {C.CYAN}{C.BOLD}[{num}]{C.RESET} {text}")


def ok(text):
    print(f"      {C.GREEN}✓{C.RESET} {text}")


def fail(text):
    print(f"      {C.RED}✗{C.RESET} {text}")


def info(text):
    print(f"      {C.GRAY}{text}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(description="EDPA GitHub Project Setup")
    parser.add_argument("--org", required=True, help="GitHub organization")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--project-title", default="EDPA — Medical Platform",
                        help="Project title")
    parser.add_argument("--backlog", default=".edpa/backlog.yaml",
                        help="Path to backlog YAML")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    args = parser.parse_args()

    full_repo = f"{args.org}/{args.repo}"

    print(f"\n{C.BOLD}{C.PURPLE}  EDPA GitHub Project Setup{C.RESET}")
    print(f"  {C.GRAY}Organization: {args.org}")
    print(f"  Repository:  {full_repo}")
    print(f"  Backlog:     {args.backlog}{C.RESET}")

    if args.dry_run:
        print(f"  {C.YELLOW}Mode: DRY RUN{C.RESET}")

    # Load backlog
    backlog_path = Path(args.backlog)
    if not backlog_path.exists():
        fail(f"Backlog not found: {args.backlog}")
        sys.exit(1)

    with open(backlog_path) as f:
        backlog = yaml.safe_load(f)

    # Flatten items
    items = []
    for init in backlog.get("initiatives", []):
        items.append({"id": init["id"], "title": init["title"], "level": "Initiative",
                       "js": 0, "bv": 0, "tc": 0, "rr": 0, "wsjf": 0,
                       "status": init.get("status", "Active")})
        for epic in init.get("epics", []):
            items.append({"id": epic["id"], "title": epic["title"], "level": "Epic",
                           "js": epic.get("js", 0), "bv": epic.get("bv", 0),
                           "tc": epic.get("tc", 0), "rr": epic.get("rr", 0),
                           "wsjf": epic.get("wsjf", 0),
                           "status": epic.get("status", "Active"),
                           "owner": epic.get("owner", "")})
            for feat in epic.get("features", []):
                items.append({"id": feat["id"], "title": feat["title"], "level": "Feature",
                               "js": feat.get("js", 0), "bv": feat.get("bv", 0),
                               "tc": feat.get("tc", 0), "rr": feat.get("rr", 0),
                               "wsjf": feat.get("wsjf", 0),
                               "status": feat.get("status", "Active"),
                               "owner": feat.get("owner", "")})
                for story in feat.get("stories", []):
                    items.append({"id": story["id"], "title": story["title"], "level": "Story",
                                   "js": story.get("js", 0), "bv": story.get("bv", 0),
                                   "tc": story.get("tc", 0), "rr": story.get("rr", 0),
                                   "wsjf": 0,
                                   "status": story.get("status", "Planned"),
                                   "assignee": story.get("assignee", ""),
                                   "iteration": story.get("iteration", "")})

    print(f"\n  {C.BOLD}Backlog: {len(items)} items{C.RESET}")
    for level in ["Initiative", "Epic", "Feature", "Story"]:
        count = sum(1 for i in items if i["level"] == level)
        if count:
            print(f"    {level}: {count}")

    if args.dry_run:
        print(f"\n  {C.YELLOW}Dry run complete. {len(items)} items would be created.{C.RESET}")
        return

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Create labels
    # ═══════════════════════════════════════════════════════════
    step(1, "Creating labels")
    labels = {
        "Initiative": ("f472b6", "Business case, investment"),
        "Epic": ("6366f1", "Strategic goal, 6-9 months"),
        "Feature": ("22d3ee", "Must fit in Planning Interval"),
        "Story": ("34d399", "Delivered in Iteration"),
        "Bug": ("f87171", "Defect in existing functionality"),
        "Enabler": ("fbbf24", "Technical work without direct business value"),
    }
    for name, (color, desc) in labels.items():
        result = run(f'gh label create "{name}" --color "{color}" --description "{desc}" --repo {full_repo}')
        if result is not None:
            ok(f"{name} ({color})")
        else:
            info(f"{name} (already exists)")

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Create GitHub Project
    # ═══════════════════════════════════════════════════════════
    step(2, "Creating GitHub Project")
    result = run(f'gh project create --owner {args.org} --title "{args.project_title}" --format json')
    if result:
        project_data = json.loads(result)
        project_id = project_data["id"]
        project_num = project_data["number"]
        ok(f"Project #{project_num} created (id={project_id})")
    else:
        # Project might already exist, find it
        result = run(f'gh project list --owner {args.org} --format json')
        projects = json.loads(result).get("projects", [])
        match = [p for p in projects if args.project_title in p.get("title", "")]
        if match:
            project_num = match[0]["number"]
            project_id = match[0]["id"]
            info(f"Project #{project_num} already exists")
        else:
            fail("Could not create or find project")
            sys.exit(1)

    # ═══════════════════════════════════════════════════════════
    # STEP 3: Create custom fields
    # ═══════════════════════════════════════════════════════════
    step(3, "Creating custom fields")
    number_fields = ["Job Size", "Business Value", "Time Criticality",
                     "Risk Reduction", "WSJF Score"]
    for name in number_fields:
        run(f'gh project field-create {project_num} --owner {args.org} '
            f'--name "{name}" --data-type NUMBER')
        ok(f"{name} (NUMBER)")

    run(f'gh project field-create {project_num} --owner {args.org} '
        f'--name "Issue Type" --data-type SINGLE_SELECT '
        f'--single-select-options "Initiative,Epic,Feature,Story,Task,Bug"')
    ok("Issue Type (SINGLE_SELECT)")

    run(f'gh project field-create {project_num} --owner {args.org} '
        f'--name "Team" --data-type SINGLE_SELECT '
        f'--single-select-options "Core,Platform,Management"')
    ok("Team (SINGLE_SELECT)")

    # Get field IDs
    field_json = run(f'gh project field-list {project_num} --owner {args.org} --format json')
    fields = json.loads(field_json).get("fields", [])
    field_ids = {f["name"]: f["id"] for f in fields}
    option_ids = {}
    for f in fields:
        for opt in f.get("options", []):
            option_ids[f"{f['name']}:{opt['name']}"] = opt["id"]

    info(f"Fields: {len(field_ids)}, Options: {len(option_ids)}")

    # ═══════════════════════════════════════════════════════════
    # STEP 4: Link project to repo
    # ═══════════════════════════════════════════════════════════
    step(4, "Linking project to repository")
    run(f'gh project link {project_num} --owner {args.org} --repo {full_repo}')
    ok(f"Linked to {full_repo}")

    # ═══════════════════════════════════════════════════════════
    # STEP 5: Create issues
    # ═══════════════════════════════════════════════════════════
    step(5, f"Creating {len(items)} issues")
    issue_map = {}  # item_id → (issue_number, project_item_id)

    for item in items:
        title = f"{item['id']}: {item['title']}"
        body_parts = [f"{item['level']}"]
        if item.get("js"): body_parts.append(f"JS={item['js']}")
        if item.get("bv"): body_parts.append(f"BV={item['bv']}")
        if item.get("tc"): body_parts.append(f"TC={item['tc']}")
        if item.get("rr"): body_parts.append(f"RR={item['rr']}")
        if item.get("wsjf"): body_parts.append(f"WSJF={item['wsjf']}")
        if item.get("assignee"): body_parts.append(f"owner={item['assignee']}")
        if item.get("iteration"): body_parts.append(f"iteration={item['iteration']}")
        body = ", ".join(body_parts)

        label = item["level"]
        result = run(f'gh issue create --repo {full_repo} --title "{title}" '
                     f'--body "{body}" --label "{label}"')
        if result:
            issue_url = result.strip()
            issue_num = issue_url.split("/")[-1]
            ok(f"{title} → #{issue_num}")

            # Add to project
            add_result = run(f'gh project item-add {project_num} --owner {args.org} '
                           f'--url {issue_url} --format json')
            if add_result:
                item_data = json.loads(add_result)
                project_item_id = item_data.get("id", "")
                issue_map[item["id"]] = (issue_num, project_item_id)

                # Close done items
                if item["status"] == "Done":
                    run(f'gh issue close {issue_num} --repo {full_repo}')
        else:
            fail(f"Failed: {title}")

    # ═══════════════════════════════════════════════════════════
    # STEP 6: Set custom field values
    # ═══════════════════════════════════════════════════════════
    step(6, "Setting custom field values on project items")

    status_map = {
        "Done": option_ids.get("Status:Done"),
        "In Progress": option_ids.get("Status:In Progress"),
        "Active": option_ids.get("Status:In Progress"),
        "Planned": option_ids.get("Status:Todo"),
        "Todo": option_ids.get("Status:Todo"),
    }
    type_map = {
        "Initiative": option_ids.get("Issue Type:Initiative"),
        "Epic": option_ids.get("Issue Type:Epic"),
        "Feature": option_ids.get("Issue Type:Feature"),
        "Story": option_ids.get("Issue Type:Story"),
    }

    set_count = 0
    for item in items:
        mapping = issue_map.get(item["id"])
        if not mapping:
            continue
        _, proj_item_id = mapping

        def set_field(field_name, number=None, option_id=None):
            nonlocal set_count
            fid = field_ids.get(field_name)
            if not fid:
                return
            cmd = f'gh project item-edit --project-id {project_id} --id {proj_item_id} --field-id {fid}'
            if number is not None:
                cmd += f' --number {number}'
            elif option_id:
                cmd += f' --single-select-option-id {option_id}'
            else:
                return
            run(cmd)
            set_count += 1

        # Set Issue Type
        type_opt = type_map.get(item["level"])
        if type_opt:
            set_field("Issue Type", option_id=type_opt)

        # Set Status
        status_opt = status_map.get(item["status"])
        if status_opt:
            set_field("Status", option_id=status_opt)

        # Set number fields
        if item.get("js"):
            set_field("Job Size", number=item["js"])
        if item.get("bv"):
            set_field("Business Value", number=item["bv"])
        if item.get("tc"):
            set_field("Time Criticality", number=item["tc"])
        if item.get("rr"):
            set_field("Risk Reduction", number=item["rr"])
        if item.get("wsjf"):
            set_field("WSJF Score", number=item["wsjf"])

    ok(f"{set_count} field values set")

    # ═══════════════════════════════════════════════════════════
    # STEP 7: Update config
    # ═══════════════════════════════════════════════════════════
    step(7, "Updating .edpa/config.yaml")
    config_path = Path(".edpa/config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        sync = config.get("sync", {})
        sync["github_org"] = args.org
        sync["github_project_number"] = project_num
        sync["github_project_id"] = project_id
        config["sync"] = sync
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        ok(f"Project #{project_num} saved to config")

    # ═══════════════════════════════════════════════════════════
    # DONE
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'═' * 70}")
    print(f"  {C.GREEN}{C.BOLD}Setup complete!{C.RESET}")
    print(f"  Project: https://github.com/orgs/{args.org}/projects/{project_num}")
    print(f"  Issues:  {len(issue_map)} created")
    print(f"  Fields:  {set_count} values set")
    print(f"\n  {C.YELLOW}{C.BOLD}Manual step required:{C.RESET}")
    print(f"  GitHub Projects v2 API does not support view column configuration.")
    print(f"  Open the project in browser and click '+' in the table header to add:")
    print(f"    Issue Type, Job Size, Business Value, Time Criticality,")
    print(f"    Risk Reduction, WSJF Score, Team")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
