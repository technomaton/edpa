#!/usr/bin/env python3
"""
EDPA GitHub Project Setup — Automated initialization of GitHub Projects v2.

Creates a fully configured GitHub Project with:
- Custom fields (Job Size, BV, TC, RR, WSJF Score, Team)
- Issues for all backlog items (from .edpa/ per-item YAML files)
- Native Issue Types assigned via GraphQL (Initiative, Epic, Feature, Story)
- Enabler label for technical work items
- Field values set on all project items
- Project linked to repository

Usage:
    python .claude/edpa/scripts/project_setup.py --org technomaton --repo edpa-simulation
    python .claude/edpa/scripts/project_setup.py --org technomaton --repo edpa-simulation --dry-run

Prerequisite:
    gh auth login (with project scope)
    .edpa/backlog/ directory with per-item YAML files (initiatives/, epics/, features/, stories/)
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
    """Run a shell command and return stdout, or None on failure.

    On failure the captured stderr is echoed to ours so callers (and
    test suites that pipe stderr) can see *why* the call failed instead
    of just receiving a bare None.
    """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
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


def _bootstrap_pi_stub_if_empty(iter_dir: Path) -> None:
    """Drop a stub PI-{year}-1.yaml into iterations/ if the directory has
    no PI YAML yet. Defaults: 1-week iterations × 5 per PI, status planning,
    starting next Monday. Customer edits or replaces it during PI Planning.
    """
    iter_dir.mkdir(parents=True, exist_ok=True)
    if any(iter_dir.glob("PI-*.yaml")):
        return
    from datetime import date, timedelta
    today = date.today()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    weeks = 5  # pi_iterations × iteration_weeks (1)
    pi_id = f"PI-{monday.year}-1"
    end = monday + timedelta(weeks=weeks) - timedelta(days=1)
    stub = (
        f"# PI-level metadata. Per-iteration files live alongside as\n"
        f"# {pi_id}.{{1..N}}.yaml; the assistant reconstructs the\n"
        f"# timeline at runtime via _pi_loader.py.\n\n"
        f"pi:\n"
        f"  id: {pi_id}\n"
        f"  status: planning\n"
        f"  iteration_weeks: 1\n"
        f"  pi_iterations: {weeks}\n"
        f"  start_date: {monday.isoformat()}\n"
        f"  end_date: {end.isoformat()}\n"
    )
    (iter_dir / f"{pi_id}.yaml").write_text(stub, encoding="utf-8")
    ok(f"Bootstrapped {iter_dir}/{pi_id}.yaml (1-week × 5)")


def info(text):
    print(f"      {C.GRAY}{text}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(description="EDPA GitHub Project Setup")
    parser.add_argument("--org", required=True, help="GitHub organization")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--project-title", default="EDPA — Medical Platform",
                        help="Project title")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip interactive prompts (e.g. project-views "
                             "configuration). Useful for CI / scripted runs.")
    args = parser.parse_args()

    full_repo = f"{args.org}/{args.repo}"

    print(f"\n{C.BOLD}{C.PURPLE}  EDPA GitHub Project Setup{C.RESET}")
    print(f"  {C.GRAY}Organization: {args.org}")
    print(f"  Repository:  {full_repo}")
    print(f"  Backlog:     .edpa/backlog/ (per-item files){C.RESET}")

    if args.dry_run:
        print(f"  {C.YELLOW}Mode: DRY RUN{C.RESET}")

    # Load items from per-file .edpa/backlog/ directories
    backlog_dir = Path(".edpa/backlog")
    if not backlog_dir.is_dir():
        fail("Cannot find .edpa/backlog/ directory")
        sys.exit(1)

    items = []
    for type_dir in ["initiatives", "epics", "features", "stories"]:
        dir_path = backlog_dir / type_dir
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.yaml")):
            raw = yaml.safe_load(open(f))
            if not raw:
                continue
            entry = {
                "id": raw["id"],
                "title": raw.get("title", ""),
                "level": raw.get("type", ""),
                "js": raw.get("js", 0),
                "bv": raw.get("bv", 0),
                "tc": raw.get("tc", 0),
                "rr": raw.get("rr", 0),
                "wsjf": raw.get("wsjf", 0),
                "status": raw.get("status", "Active"),
                "owner": raw.get("owner", ""),
                "assignee": raw.get("assignee", ""),
                "iteration": raw.get("iteration", ""),
                "type": raw.get("epic_type", ""),
                "parent": raw.get("parent", ""),
            }
            items.append(entry)

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
        f'--name "Team" --data-type SINGLE_SELECT '
        f'--single-select-options "Core,Platform,Management"')
    ok("Team (SINGLE_SELECT)")

    # Create typed SAFe status fields (single-select per level)
    # Portfolio: Initiative + Epic share one workflow
    # Delivery: Feature + Story share another workflow
    portfolio_opts = "Funnel,Reviewing,Analyzing,Ready,Implementing,Done"
    delivery_opts = "Funnel,Analyzing,Backlog,Implementing,Validating,Deploying,Releasing,Done"

    typed_status_fields = {
        "Initiative Status": portfolio_opts,
        "Epic Status": portfolio_opts,
        "Feature Status": delivery_opts,
        "Story Status": delivery_opts,
    }

    for fname, opts in typed_status_fields.items():
        run(f'gh project field-create {project_num} --owner {args.org} '
            f'--name "{fname}" --data-type SINGLE_SELECT '
            f'--single-select-options "{opts}"')
        ok(f"{fname} (SINGLE_SELECT)")

    # Iteration field — populated from .edpa/iterations/*.yaml IDs.
    # GitHub's native ITERATION type requires a fixed cadence + duration that
    # doesn't always match SAFe PI windows; SINGLE_SELECT is more flexible
    # and lets sync round-trip the iteration tag verbatim.
    iter_dir = Path(".edpa/iterations")
    iteration_options = []
    if iter_dir.is_dir():
        for f in sorted(iter_dir.glob("*.yaml")):
            try:
                iter_doc = yaml.safe_load(open(f)) or {}
                iid = iter_doc.get("iteration", {}).get("id") or f.stem
                iteration_options.append(iid)
            except (yaml.YAMLError, OSError):
                continue
    # Always create the Iteration field. Without it, every subsequent push
    # of an item with `iteration:` set fails with "no field_id for 'Iteration'"
    # and pull wipes local iteration tags. Use a TBD placeholder when no
    # iterations exist yet; real options are added later via setup-refresh
    # or sync add-iteration once iteration YAMLs land.
    if not iteration_options:
        iteration_options = ["TBD"]
    opts_str = ",".join(iteration_options)
    run(f'gh project field-create {project_num} --owner {args.org} '
        f'--name "Iteration" --data-type SINGLE_SELECT '
        f'--single-select-options "{opts_str}"')
    ok(f"Iteration (SINGLE_SELECT, {len(iteration_options)} options)")

    # Refresh field IDs after creating typed status fields. GitHub's
    # ProjectV2 API occasionally returns 5xx right after a burst of
    # field-create calls (eventual consistency under load); retry once
    # so the wizard isn't fragile to that.
    import time
    field_json = run(f'gh project field-list {project_num} --owner {args.org} --format json --limit 100')
    if not field_json:
        time.sleep(2)
        field_json = run(f'gh project field-list {project_num} --owner {args.org} --format json --limit 100')
    if not field_json:
        fail(f"gh project field-list returned no output for project #{project_num}. "
             f"Check that gh CLI is authenticated and the project is reachable.")
        sys.exit(1)
    try:
        fields = json.loads(field_json).get("fields", [])
    except (ValueError, TypeError) as exc:
        fail(f"Could not parse field-list JSON ({exc}); raw output: {field_json[:200]!r}")
        sys.exit(1)
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
    # STEP 5: Query native Issue Type IDs from organization
    # ═══════════════════════════════════════════════════════════
    step(5, "Querying organization Issue Type IDs")
    issue_type_ids = {}
    type_query = f'{{ organization(login: "{args.org}") {{ issueTypes(first: 20) {{ nodes {{ id name }} }} }} }}'
    type_result = gh_graphql(type_query)
    if type_result and type_result.get("data"):
        for t in type_result["data"]["organization"]["issueTypes"]["nodes"]:
            issue_type_ids[t["name"]] = t["id"]
        ok(f"Found {len(issue_type_ids)} issue types: {', '.join(issue_type_ids.keys())}")
    else:
        fail("Could not query issue types from org. Run 'issue_types.py setup --org ORG' first.")
        fail("Issue Type assignment will be skipped.")
        issue_type_ids = {}

    # ═══════════════════════════════════════════════════════════
    # STEP 6: Create issues
    # ═══════════════════════════════════════════════════════════
    step(6, f"Creating {len(items)} issues")
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

        # Add Enabler label only for items with type: Enabler in backlog
        label_flag = ""
        if item.get("type") == "Enabler":
            label_flag = ' --label "Enabler"'

        result = run(f'gh issue create --repo {full_repo} --title "{title}" '
                     f'--body "{body}"{label_flag}')
        if result:
            issue_url = result.strip()
            issue_num = issue_url.split("/")[-1]
            ok(f"{title} → #{issue_num}")

            # Assign native Issue Type via GraphQL
            issue_node_id = None
            type_id = issue_type_ids.get(item["level"])
            if type_id:
                node_query = (
                    f'{{ repository(owner: "{args.org}", name: "{args.repo}") '
                    f'{{ issue(number: {issue_num}) {{ id }} }} }}'
                )
                node_result = gh_graphql(node_query)
                if node_result and node_result.get("data"):
                    issue_node_id = node_result["data"]["repository"]["issue"]["id"]
                    mutation = (
                        f'mutation {{ updateIssueIssueType(input: '
                        f'{{ issueId: "{issue_node_id}", issueTypeId: "{type_id}" }}) '
                        f'{{ issue {{ id }} }} }}'
                    )
                    gh_graphql(mutation)
                    info(f"  Issue type → {item['level']}")

            # Add to project
            add_result = run(f'gh project item-add {project_num} --owner {args.org} '
                           f'--url {issue_url} --format json')
            if add_result:
                item_data = json.loads(add_result)
                project_item_id = item_data.get("id", "")
                # Resolve issue node ID if not already resolved (needed for sub-issue linking)
                if not issue_node_id:
                    node_query = (
                        f'{{ repository(owner: "{args.org}", name: "{args.repo}") '
                        f'{{ issue(number: {issue_num}) {{ id }} }} }}'
                    )
                    node_result = gh_graphql(node_query)
                    if node_result and node_result.get("data"):
                        issue_node_id = node_result["data"]["repository"]["issue"]["id"]
                issue_map[item["id"]] = (issue_num, project_item_id, issue_node_id)

                # Close done items
                if item["status"] == "Done":
                    run(f'gh issue close {issue_num} --repo {full_repo}')
        else:
            fail(f"Failed: {title}")

    # ═══════════════════════════════════════════════════════════
    # STEP 7: Set custom field values
    # ═══════════════════════════════════════════════════════════
    step(7, "Setting custom field values on project items")

    # Map item level to its typed status field name
    level_status_field = {
        "Initiative": "Initiative Status",
        "Epic": "Epic Status",
        "Feature": "Feature Status",
        "Story": "Story Status",
    }

    set_count = 0
    for item in items:
        mapping = issue_map.get(item["id"])
        if not mapping:
            continue
        _, proj_item_id, _ = mapping

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

        # Set typed status field based on item level
        status_field_name = level_status_field.get(item["level"])
        if status_field_name and item.get("status"):
            status_opt = option_ids.get(f"{status_field_name}:{item['status']}")
            if status_opt:
                set_field(status_field_name, option_id=status_opt)

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

        # Set iteration field (single-select) when item has one assigned
        if item.get("iteration"):
            iter_opt = option_ids.get(f"Iteration:{item['iteration']}")
            if iter_opt:
                set_field("Iteration", option_id=iter_opt)

    ok(f"{set_count} field values set")

    # ═══════════════════════════════════════════════════════════
    # STEP 8: Link sub-issues (parent-child hierarchy)
    # ═══════════════════════════════════════════════════════════
    step(8, "Linking sub-issues (parent-child hierarchy)")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _sub_issue_linker import link_items  # noqa: E402

    counts = link_items(
        items, issue_map,
        on_skip=lambda cid, pid, msg: info(f"  {cid} → {pid} (skipped, {msg})"),
        on_error=lambda cid, pid, msg: info(f"  {cid} → {pid} (failed: {msg})"),
    )
    if counts["linked"]:
        ok(f"{counts['linked']} sub-issue links created")
    if counts["errors"]:
        info(f"{counts['errors']} links failed (see above)")
    if counts == {"linked": 0, "errors": 0, "skipped": 0}:
        info("No parent references found in backlog items")
    link_count = counts["linked"]   # downstream summary uses this

    # ═══════════════════════════════════════════════════════════
    # STEP 9: Persist GitHub state for sync
    # ═══════════════════════════════════════════════════════════
    step(9, "Persisting GitHub state (.edpa/config/edpa.yaml + issue_map.yaml)")
    config_path = Path(".edpa/config/edpa.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        sync = config.get("sync", {})
        sync["github_org"] = args.org
        sync["github_repo"] = args.repo
        sync["github_project_number"] = project_num
        sync["github_project_id"] = project_id
        sync["field_ids"] = dict(field_ids)
        sync["option_ids"] = dict(option_ids)
        config["sync"] = sync

        # Persist project.name from --project-title so MCP edpa_status
        # stops reporting "unknown" after a fresh setup. Only overwrite
        # the placeholder; respect a name the user set by hand.
        project = config.get("project") or {}
        if not project.get("name") or project.get("name") in ("My Project", "", None):
            project["name"] = args.project_title
            config["project"] = project

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        ok(f"Project #{project_num}, {len(field_ids)} fields, {len(option_ids)} options saved")

        # Bootstrap a stub PI-level YAML if iterations/ is empty so the
        # assistant has something to report immediately after setup.
        # AI-native defaults: 1-week iterations × 5 per PI. Customer
        # creates the per-iteration files (PI-{id}.{n}.yaml) as the team
        # plans them; gaps surface via edpa_validate.
        _bootstrap_pi_stub_if_empty(Path(".edpa/iterations"))

    issue_map_path = Path(".edpa/config/issue_map.yaml")
    serializable_map = {
        "github_repo": f"{args.org}/{args.repo}",
        "github_project_number": project_num,
        "items": {
            iid: {
                "issue_number": int(num),
                "project_item_id": pid,
                "node_id": nid,
            }
            for iid, (num, pid, nid) in issue_map.items()
            if num and pid
        },
    }
    issue_map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(issue_map_path, "w") as f:
        yaml.dump(serializable_map, f, default_flow_style=False, allow_unicode=True, sort_keys=True)
    ok(f"issue_map.yaml: {len(serializable_map['items'])} items mapped")

    # ═══════════════════════════════════════════════════════════
    # STEP 10 (optional): Configure GitHub Project views by issue type
    # ═══════════════════════════════════════════════════════════
    views_created = _maybe_create_project_views(args, project_num,
                                                non_interactive=args.non_interactive)

    # ═══════════════════════════════════════════════════════════
    # DONE
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'═' * 70}")
    print(f"  {C.GREEN}{C.BOLD}Setup complete!{C.RESET}")
    print(f"  Project: https://github.com/orgs/{args.org}/projects/{project_num}")
    print(f"  Issues:  {len(issue_map)} created")
    print(f"  Fields:  {set_count} values set")
    print(f"  Links:   {link_count} sub-issue links")
    if views_created is True:
        print(f"  Views:   created automatically (Initiative / Epic / Feature / Story / Status)")
    elif views_created is False:
        print(f"  Views:   creation failed — see warnings above; run "
              f"`python .claude/edpa/scripts/create_project_views.py` to retry")
    else:
        print(f"  Views:   skipped — run `python .claude/edpa/scripts/create_project_views.py` "
              f"when you want them")
    print(f"\n  {C.YELLOW}{C.BOLD}Next steps:{C.RESET}")
    print(f"  1. Enable automations in GitHub UI (Settings → Workflows):")
    print(f"     - Item added to project → Set status to Todo")
    print(f"     - Auto-add issues from linked repository")
    print(f"{'═' * 70}\n")


def _maybe_create_project_views(args, project_num, non_interactive=False):
    """Optional STEP 10: ask the maintainer whether to auto-create the
    standard GitHub Project views (per-level filters + status board).
    Try once; on subprocess failure, log + continue (non-fatal).

    Returns:
      True   — views created successfully
      False  — invocation tried but failed (warning printed)
      None   — user declined or non-interactive mode skipped them
    """
    step(10, "Configure GitHub Project views (optional)")
    if non_interactive:
        info("non-interactive mode — skipping (run create_project_views.py manually)")
        return None
    try:
        answer = input(f"      Configure standard views now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        info("no input available — skipping")
        return None
    if answer in ("n", "no"):
        info("skipped — you can run create_project_views.py later")
        return None

    views_script = Path(__file__).resolve().parent / "create_project_views.py"
    if not views_script.exists():
        fail(f"create_project_views.py not found at {views_script}")
        return False

    project_url = f"https://github.com/orgs/{args.org}/projects/{project_num}"
    try:
        result = subprocess.run(
            ["python3", str(views_script), "--url", project_url],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        fail(f"create_project_views invocation failed: {exc}")
        return False

    if result.returncode != 0:
        fail(f"create_project_views returned exit {result.returncode}")
        if result.stderr:
            print(f"      {result.stderr.strip()}")
        return False
    ok("Views configured (Initiative / Epic / Feature / Story / Status)")
    return True


if __name__ == "__main__":
    main()
