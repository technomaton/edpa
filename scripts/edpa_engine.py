#!/usr/bin/env python3
"""
EDPA Engine — Evidence-Driven Proportional Allocation v2.2

Standalone Python implementation of the EDPA calculation engine.
Computes derived hours from GitHub delivery evidence.

Usage:
    python scripts/edpa_engine.py --iteration PI-2026-1.3 --capacity config/capacity.yaml --heuristics config/cw_heuristics.yaml
    python scripts/edpa_engine.py --iteration PI-2026-1.3 --mode full --capacity config/capacity.yaml --heuristics config/cw_heuristics.yaml
    python scripts/edpa_engine.py --demo  # Run with built-in sample data
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def gh_json(cmd):
    """Run gh CLI command and parse JSON output."""
    try:
        result = subprocess.run(
            ["gh"] + cmd.split() + ["--json", "number,title,assignees,labels,body"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def extract_item_refs(text):
    """Extract work item references (S-123, F-45, E-7) from text."""
    if not text:
        return []
    return re.findall(r'[SFEIATB]-\d+', text)


def detect_evidence(people, items, iteration_id):
    """
    Detect contribution evidence from GitHub data.

    Returns: dict of {(person_id, item_id): {"signals": [...], "evidence_score": float, "cw": float}}
    """
    evidence = {}

    for item in items:
        item_id = item.get("id", "")
        assignees = [a.get("login", "") for a in item.get("assignees", [])]

        for person in people:
            pid = person["id"]

            # Check evidence_scope
            scope = person.get("evidence_scope")
            if scope:
                import fnmatch
                if not any(fnmatch.fnmatch(item_id, pattern) for pattern in scope):
                    # Item doesn't match this contract's scope
                    if not person.get("evidence_default", False):
                        continue  # Skip — not in scope and not default

            signals = []
            score = 0.0

            # Check assignee
            if pid in assignees or person.get("email", "") in assignees:
                score += 4.0
                signals.append("assignee")

            # Check /contribute commands in body
            body = item.get("body", "") or ""
            contribute_pattern = rf'/contribute\s+@{re.escape(pid)}\s+weight:([0-9.]+)'
            contribute_match = re.search(contribute_pattern, body)
            if contribute_match:
                score += 3.0
                signals.append("contribute_command")

            # Check PR author (simplified — looks at linked PRs)
            if item.get("pr_author") == pid:
                score += 2.0
                signals.append("pr_author")

            # Check commit author
            if item.get("commit_authors") and pid in item["commit_authors"]:
                score += 1.0
                signals.append("commit_author")

            # Check PR reviewer
            if item.get("pr_reviewers") and pid in item["pr_reviewers"]:
                score += 1.0
                signals.append("pr_reviewer")

            # Check comments
            if item.get("commenters") and pid in item["commenters"]:
                score += 0.5
                signals.append("issue_comment")

            if signals:
                evidence[(pid, item_id)] = {
                    "signals": signals,
                    "evidence_score": score,
                    "manual_cw": float(contribute_match.group(1)) if contribute_match else None
                }

    return evidence


def compute_cw(evidence_entry, heuristics, person_role=None):
    """Compute Contribution Weight from evidence signals.

    Uses role_overrides (Monte Carlo calibrated) when person_role is known,
    falling back to generic role_weights otherwise.
    """
    if evidence_entry.get("manual_cw") is not None:
        return evidence_entry["manual_cw"]

    signal_to_role = {
        "assignee": "owner",
        "contribute_command": "key",
        "pr_author": "key",
        "commit_author": "reviewer",
        "pr_reviewer": "reviewer",
        "issue_comment": "consulted",
    }

    role_priority = ["assignee", "contribute_command", "pr_author",
                     "commit_author", "pr_reviewer", "issue_comment"]

    role_weights = heuristics.get("role_weights", {})
    role_overrides = heuristics.get("role_overrides", {})

    for signal in role_priority:
        if signal in evidence_entry["signals"]:
            evidence_role = signal_to_role[signal]

            # Check role_overrides first (Monte Carlo calibrated)
            if person_role and person_role in role_overrides:
                override = role_overrides[person_role]
                if evidence_role in override:
                    return override[evidence_role]

            # Fallback to generic weights
            return role_weights.get(evidence_role, 0.15)

    return 0.15


def run_edpa(capacity_config, heuristics, items, mode="simple"):
    """
    Run the core EDPA v2.2 calculation.

    Returns: list of person results with derived hours.
    """
    people = capacity_config.get("people", [])
    threshold = heuristics.get("evidence_threshold", 1.0)
    iteration_id = "computed"

    # Detect evidence
    evidence = detect_evidence(people, items, iteration_id)

    results = []

    for person in people:
        pid = person["id"]
        capacity = person.get("capacity_per_iteration", 0)
        person_items = []

        for item in items:
            item_id = item["id"]
            key = (pid, item_id)

            if key not in evidence:
                continue

            ev = evidence[key]
            if ev["evidence_score"] < threshold:
                continue

            cw = compute_cw(ev, heuristics, person_role=person.get("role"))
            js = item.get("job_size", 0)

            if js <= 0:
                continue

            if mode == "full":
                # Compute Relevance Signal
                max_es = max(
                    (evidence.get((p["id"], item_id), {}).get("evidence_score", 0)
                     for p in people),
                    default=1.0
                )
                rs = min(ev["evidence_score"] / max_es, 1.0) if max_es > 0 else 1.0
            else:
                rs = 1.0

            score = js * cw * rs

            person_items.append({
                "id": item_id,
                "level": item.get("level", "Story"),
                "js": js,
                "cw": round(cw, 4),
                "rs": round(rs, 4),
                "score": round(score, 4),
                "evidence": ev["signals"],
            })

        # Calculate derived hours
        sum_scores = sum(pi["score"] for pi in person_items)

        for pi in person_items:
            if sum_scores > 0:
                ratio = pi["score"] / sum_scores
                hours = ratio * capacity
            else:
                ratio = 0.0
                hours = 0.0
            pi["ratio"] = round(ratio, 6)
            pi["hours"] = round(hours, 2)

        total_derived = sum(pi["hours"] for pi in person_items)

        # Validate invariants
        invariant_ok = True
        if person_items:
            if abs(total_derived - capacity) > 0.01:
                invariant_ok = False
            ratio_sum = sum(pi["ratio"] for pi in person_items)
            if abs(ratio_sum - 1.0) > 0.001:
                invariant_ok = False
            if any(pi["hours"] < 0 for pi in person_items):
                invariant_ok = False

        results.append({
            "id": pid,
            "name": person.get("name", pid),
            "role": person.get("role", ""),
            "capacity": capacity,
            "total_derived": round(total_derived, 2),
            "items": person_items,
            "invariant_ok": invariant_ok,
        })

    return results


def generate_demo_data():
    """Generate sample data for demonstration (multi-contract).

    Alice is split into two contracts:
      - alice-arch  (Arch, 40h) — scoped to Stories (S-*), evidence_default=true
      - alice-pm    (PM,  20h) — scoped to Epics/Features (E-*, F-*)
    Total team capacity: 40 + 20 + 80 + 60 = 200h.
    """
    capacity = {
        "teams": [
            {"id": "Alpha", "planning_factor": 0.8},
        ],
        "people": [
            {"id": "alice-arch", "name": "Alice (Arch)", "role": "Arch", "team": "Alpha",
             "fte": 0.5, "capacity_per_iteration": 40, "email": "alice@example.com",
             "evidence_scope": ["S-*"], "evidence_default": True},
            {"id": "alice-pm", "name": "Alice (PM)", "role": "PM", "team": "Alpha",
             "fte": 0.25, "capacity_per_iteration": 20, "email": "alice@example.com",
             "evidence_scope": ["E-*", "F-*"]},
            {"id": "bob", "name": "Bob (Dev)", "role": "Dev", "team": "Alpha",
             "fte": 1.0, "capacity_per_iteration": 80, "email": "bob@example.com"},
            {"id": "carol", "name": "Carol (Dev)", "role": "Dev", "team": "Alpha",
             "fte": 0.75, "capacity_per_iteration": 60, "email": "carol@example.com"},
        ]
    }

    heuristics = {
        "version": "2.2",
        "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
        "role_overrides": {
            "BO":   {"owner": 1.00, "key": 0.60, "reviewer": 0.35, "consulted": 0.30},
            "PM":   {"owner": 1.00, "key": 0.60, "reviewer": 0.25, "consulted": 0.20},
            "Arch": {"owner": 1.00, "key": 0.60, "reviewer": 0.30, "consulted": 0.15},
            "Dev":  {"owner": 1.00, "key": 0.60, "reviewer": 0.25, "consulted": 0.15},
        },
        "signals": {"assignee": 4.0, "contribute_command": 3.0, "pr_author": 2.0,
                     "commit_author": 1.0, "pr_reviewer": 1.0, "issue_comment": 0.5},
    }

    items = [
        {"id": "S-101", "level": "Story", "job_size": 5,
         "assignees": [{"login": "bob"}],
         "body": "", "pr_author": "bob", "commit_authors": ["bob", "carol"],
         "pr_reviewers": ["alice-arch"], "commenters": []},
        {"id": "S-102", "level": "Story", "job_size": 8,
         "assignees": [{"login": "carol"}],
         "body": "/contribute @alice-arch weight:0.6", "pr_author": "carol",
         "commit_authors": ["carol"], "pr_reviewers": ["bob"],
         "commenters": ["alice-arch"]},
        {"id": "S-103", "level": "Story", "job_size": 3,
         "assignees": [{"login": "bob"}],
         "body": "", "pr_author": "bob", "commit_authors": ["bob"],
         "pr_reviewers": ["alice-arch"], "commenters": []},
        {"id": "F-10", "level": "Feature", "job_size": 13,
         "assignees": [{"login": "alice-pm"}],
         "body": "", "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": ["bob", "carol"]},
        {"id": "S-104", "level": "Story", "job_size": 5,
         "assignees": [{"login": "carol"}],
         "body": "", "pr_author": "carol", "commit_authors": ["carol", "bob"],
         "pr_reviewers": ["alice-arch"], "commenters": []},
        {"id": "E-10", "level": "Epic", "job_size": 21,
         "assignees": [{"login": "alice-pm"}],
         "body": "", "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": ["bob"]},
    ]

    return capacity, heuristics, items


def print_summary(results, mode, iteration_id, planning_factor=0.8):
    """Print human-readable summary table."""
    print(f"\n{'='*70}")
    print(f"EDPA v2.2 — Iteration {iteration_id} ({mode} mode)")
    print(f"{'='*70}")
    print(f"{'Person':<25} {'Role':<8} {'Capacity':>8} {'Derived':>8} {'Items':>6} {'OK':>4}")
    print(f"{'-'*70}")

    team_capacity = 0
    team_derived = 0
    all_ok = True

    for r in results:
        ok = "OK" if r["invariant_ok"] else "FAIL"
        if not r["invariant_ok"]:
            all_ok = False
        team_capacity += r["capacity"]
        team_derived += r["total_derived"]
        print(f"{r['name']:<25} {r['role']:<8} {r['capacity']:>7}h {r['total_derived']:>7}h {len(r['items']):>6} {ok:>4}")

    print(f"{'-'*70}")
    team_planning = round(team_capacity * planning_factor, 1)
    print(f"{'TEAM TOTAL':<25} {'':8} {team_capacity:>7}h {team_derived:>7}h")
    print(f"{'PLANNING CAPACITY':<25} {'':8} {team_planning:>7}h  (factor: {planning_factor})")
    print(f"\nAll invariants passed: {'YES' if all_ok else 'NO'}")

    # Per-person detail
    for r in results:
        if r["items"]:
            print(f"\n--- {r['name']} ({r['capacity']}h) ---")
            print(f"  {'Item':<10} {'Level':<8} {'JS':>4} {'CW':>6} {'Score':>7} {'Ratio':>7} {'Hours':>7}")
            for item in r["items"]:
                print(f"  {item['id']:<10} {item['level']:<8} {item['js']:>4} {item['cw']:>6.2f} {item['score']:>7.2f} {item['ratio']:>6.1%} {item['hours']:>6.1f}h")


def main():
    parser = argparse.ArgumentParser(
        description="EDPA v2.2 — Evidence-Driven Proportional Allocation Engine",
        epilog="Run with --demo to see a worked example without any configuration."
    )
    parser.add_argument("--iteration", help="Iteration ID (e.g., PI-2026-1.3)")
    parser.add_argument("--mode", choices=["simple", "full"], default="simple",
                        help="Calculation mode (default: simple)")
    parser.add_argument("--capacity", help="Path to capacity.yaml")
    parser.add_argument("--heuristics", help="Path to cw_heuristics.yaml")
    parser.add_argument("--output", help="Output path for edpa_results.json")
    parser.add_argument("--demo", action="store_true",
                        help="Run with built-in sample data")
    args = parser.parse_args()

    if args.demo:
        print("Running EDPA demo with sample data...\n")
        capacity, heuristics, items = generate_demo_data()
        iteration_id = "DEMO-1.1"
    else:
        if not args.capacity or not args.heuristics or not args.iteration:
            parser.error("--iteration, --capacity, and --heuristics are required (or use --demo)")

        capacity = load_yaml(args.capacity)
        heuristics = load_yaml(args.heuristics)
        iteration_id = args.iteration

        # In production: gather items from GitHub
        # For now, items must be provided via --items or gathered by the Claude Code skill
        print(f"Loading configuration from {args.capacity} and {args.heuristics}")
        print(f"NOTE: In standalone mode, item data must be gathered from GitHub.")
        print(f"      Use 'gh issue list' and 'gh pr list' to gather evidence,")
        print(f"      or use the Claude Code /edpa close-iteration command for automated gathering.")
        items = []

    # Resolve planning_factor from teams (team-level decision, not cadence)
    teams = capacity.get("teams", [])
    if teams:
        planning_factor = teams[0].get("planning_factor", 0.8)
    else:
        planning_factor = 0.8

    results = run_edpa(capacity, heuristics, items, mode=args.mode)

    all_passed = all(r["invariant_ok"] for r in results if r["items"])
    team_total = sum(r["total_derived"] for r in results)

    output = {
        "iteration": iteration_id,
        "mode": args.mode,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "EDPA v2.2",
        "planning_factor": planning_factor,
        "people": results,
        "team_total": round(team_total, 2),
        "all_invariants_passed": all_passed,
    }

    # Write output
    if args.output:
        output_path = Path(args.output)
    elif not args.demo:
        output_path = Path(f"reports/iteration-{iteration_id}/edpa_results.json")
    else:
        output_path = None

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to: {output_path}")

    print_summary(results, args.mode, iteration_id, planning_factor)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
