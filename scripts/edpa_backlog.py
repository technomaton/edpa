#!/usr/bin/env python3
"""
EDPA Backlog CLI -- Git-native backlog management tool.

Usage:
    python scripts/edpa_backlog.py tree                    # Full hierarchy
    python scripts/edpa_backlog.py tree --level epic       # Epics only
    python scripts/edpa_backlog.py tree --iteration PI-2026-1.1
    python scripts/edpa_backlog.py show S-200              # Item details
    python scripts/edpa_backlog.py status                  # Project status
    python scripts/edpa_backlog.py status --iteration PI-2026-1.1
    python scripts/edpa_backlog.py wsjf                    # WSJF ranking
    python scripts/edpa_backlog.py wsjf --level feature
    python scripts/edpa_backlog.py validate                # Integrity check
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


# ── ANSI Colors (EDPA palette) ──────────────────────────────────────────────

class C:
    """ANSI color codes matching EDPA design palette."""
    RESET    = "\033[0m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"
    # Level colors
    INIT     = "\033[35m"       # Magenta -- Initiative
    EPIC     = "\033[38;5;93m"  # Purple -- Epic
    FEAT     = "\033[36m"       # Cyan -- Feature
    STORY    = "\033[32m"       # Green -- Story
    # Status colors
    DONE     = "\033[32m"       # Green
    ACTIVE   = "\033[33m"       # Yellow
    PROGRESS = "\033[34m"       # Blue
    PLANNED  = "\033[37m"       # Light gray
    # Utility
    WARN     = "\033[33m"
    ERR      = "\033[31m"
    OK       = "\033[32m"
    HEADER   = "\033[38;5;147m"  # Light purple
    MUTED    = "\033[38;5;245m"  # Gray


def color(text, code):
    return f"{code}{text}{C.RESET}"


def bold(text):
    return f"{C.BOLD}{text}{C.RESET}"


# ── Box-drawing characters ──────────────────────────────────────────────────

PIPE   = "\u2502"   # |
TEE    = "\u251c"   # |-
ELBOW  = "\u2514"   # L
DASH   = "\u2500"   # -
DOT    = "\u2022"   # bullet
ARROW  = "\u2192"   # →


# ── Data Loading ────────────────────────────────────────────────────────────

def find_repo_root():
    """Walk up from CWD to find the repo root (contains .edpa/)."""
    p = Path.cwd()
    while p != p.parent:
        if (p / ".edpa" / "backlog.yaml").exists():
            return p
        p = p.parent
    # Fallback: try the known project path
    fallback = Path("/Users/jurby/projects/edpa")
    if (fallback / ".edpa" / "backlog.yaml").exists():
        return fallback
    return None


def load_backlog(root):
    path = root / ".edpa" / "backlog.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_iteration(root, iteration_id):
    path = root / ".edpa" / "iterations" / f"{iteration_id}.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(root):
    path = root / ".edpa" / "config.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Utility: collect all items flat ─────────────────────────────────────────

def collect_items(backlog):
    """Collect all items into a flat list with level annotation."""
    items = []
    for init in backlog.get("initiatives", []):
        items.append({"level": "Initiative", **init})
        for epic in init.get("epics", []):
            items.append({"level": "Epic", "parent": init["id"], **epic})
            for feat in epic.get("features", []):
                items.append({"level": "Feature", "parent": epic["id"], **feat})
                for story in feat.get("stories", []):
                    items.append({"level": "Story", "parent": feat["id"], **story})
    return items


def find_item(backlog, item_id):
    """Find a single item by ID."""
    for item in collect_items(backlog):
        if item.get("id") == item_id:
            return item
    return None


def status_badge(status):
    """Return colored status badge."""
    s = status or "Unknown"
    if s == "Done":
        return color(f"[{s}]", C.DONE)
    elif s == "Active":
        return color(f"[{s}]", C.ACTIVE)
    elif s == "In Progress":
        return color(f"[{s}]", C.PROGRESS)
    elif s == "Planned":
        return color(f"[{s}]", C.PLANNED)
    else:
        return f"[{s}]"


def level_color(level):
    if level == "Initiative":
        return C.INIT
    elif level == "Epic":
        return C.EPIC
    elif level == "Feature":
        return C.FEAT
    elif level == "Story":
        return C.STORY
    return C.RESET


def wsjf_score(item):
    """Compute WSJF = (bv + tc + rr) / js. Returns 0 if js is 0."""
    js = item.get("js", 0)
    if not js or js == 0:
        return 0.0
    bv = item.get("bv", 0)
    tc = item.get("tc", 0)
    rr = item.get("rr", 0)
    return round((bv + tc + rr) / js, 2)


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_tree(backlog, args):
    """Display the work item hierarchy as a tree."""
    level_filter = getattr(args, "level", None)
    iter_filter = getattr(args, "iteration", None)

    print()
    print(bold(color("  EDPA Backlog Tree", C.HEADER)))
    print(color(f"  {backlog['project']['name']}", C.MUTED))
    print()

    for init in backlog.get("initiatives", []):
        if level_filter and level_filter not in ("init", "initiative"):
            pass  # still show initiative as root context
        print(f"  {color(DOT, C.INIT)} {color(bold(init['id']), C.INIT)} {color(init['title'], C.INIT)}  {status_badge(init.get('status'))}")

        epics = init.get("epics", [])
        for ei, epic in enumerate(epics):
            is_last_epic = ei == len(epics) - 1
            econ = ELBOW if is_last_epic else TEE
            epad = "   " if is_last_epic else f"  {PIPE}"

            wsjf_val = epic.get("wsjf", wsjf_score(epic))
            epic_js = epic.get("js", 0)
            print(f"  {econ}{DASH}{DASH} {color(bold(epic['id']), C.EPIC)} {color(epic['title'], C.EPIC)}  "
                  f"{status_badge(epic.get('status'))}  "
                  f"{color(f'WSJF={wsjf_val}', C.MUTED)}  "
                  f"{color(f'JS={epic_js}', C.DIM)}")

            if level_filter in ("epic", "epics"):
                continue

            features = epic.get("features", [])
            for fi, feat in enumerate(features):
                is_last_feat = fi == len(features) - 1
                fcon = ELBOW if is_last_feat else TEE
                fpad_char = " " if is_last_feat else PIPE

                wsjf_val = feat.get("wsjf", wsjf_score(feat))
                feat_js = feat.get("js", 0)
                print(f" {epad} {fcon}{DASH}{DASH} {color(bold(feat['id']), C.FEAT)} {color(feat['title'], C.FEAT)}  "
                      f"{status_badge(feat.get('status'))}  "
                      f"{color(f'WSJF={wsjf_val}', C.MUTED)}  "
                      f"{color(f'JS={feat_js}', C.DIM)}")

                if level_filter in ("feature", "features"):
                    continue

                stories = feat.get("stories", [])
                # Apply iteration filter if provided
                if iter_filter:
                    stories = [s for s in stories if s.get("iteration") == iter_filter]

                for si, story in enumerate(stories):
                    is_last_story = si == len(stories) - 1
                    scon = ELBOW if is_last_story else TEE

                    story_iter = story.get('iteration', '?')
                    story_assignee = story.get('assignee', '?')
                    story_js = story.get('js', 0)
                    iter_tag = color(f"@{story_iter}", C.MUTED) if story.get("iteration") else ""
                    assignee_tag = color(f"-> {story_assignee}", C.DIM) if story.get("assignee") else ""

                    inner_pad = " " if is_last_feat else PIPE
                    print(f" {epad}  {inner_pad}  {scon}{DASH}{DASH} {color(story['id'], C.STORY)} "
                          f"{color(story['title'], C.STORY)}  "
                          f"{status_badge(story.get('status'))}  "
                          f"{color(f'JS={story_js}', C.DIM)}  "
                          f"{iter_tag}  {assignee_tag}")

    print()


def cmd_show(backlog, args):
    """Show detailed information about a single item."""
    item_id = args.item_id
    item = find_item(backlog, item_id)

    if not item:
        print(color(f"  Error: Item '{item_id}' not found.", C.ERR))
        sys.exit(1)

    level = item.get("level", "?")
    lc = level_color(level)

    print()
    item_id_str = item['id']
    header_line = f"{DASH * 3} {item_id_str} {DASH * 40}"
    print(f"  {color(bold(header_line), lc)}")
    print(f"  {bold('Title:')}    {color(item.get('title', ''), lc)}")
    print(f"  {bold('Level:')}    {level}")
    print(f"  {bold('Status:')}   {status_badge(item.get('status'))}")

    if item.get("owner"):
        print(f"  {bold('Owner:')}    {item['owner']}")
    if item.get("assignee"):
        print(f"  {bold('Assignee:')} {item['assignee']}")
    if item.get("iteration"):
        print(f"  {bold('Iteration:')} {item['iteration']}")
    if item.get("parent"):
        print(f"  {bold('Parent:')}   {item['parent']}")

    # SAFe scores
    js = item.get("js", 0)
    if js:
        bv = item.get("bv", 0)
        tc = item.get("tc", 0)
        rr = item.get("rr", 0)
        w = wsjf_score(item)
        print()
        print(f"  {bold('SAFe Scores:')}")
        print(f"    Job Size (JS):          {js}")
        print(f"    Business Value (BV):     {bv}")
        print(f"    Time Criticality (TC):   {tc}")
        print(f"    Risk Reduction (RR):     {rr}")
        print(f"    WSJF:                    {color(str(w), C.HEADER)}")

    # Epic Hypothesis Statement (SAFe 6)
    eh = item.get("epic_hypothesis")
    if eh:
        print()
        print(f"  {bold('Epic Hypothesis Statement:')}")
        print(f"    {bold('For')}     {eh.get('for', '')}")
        print(f"    {bold('Who')}     {eh.get('who', '')}")
        print(f"    {bold('The')}     {color(eh.get('the', ''), lc)}")
        print(f"    {bold('Is a')}    {eh.get('is_a', '')}")
        print(f"    {bold('That')}    {eh.get('that', '')}")
        print(f"    {bold('Unlike')}  {eh.get('unlike', '')}")
        print(f"    {bold('Our')}     {eh.get('our_solution', '')}")

        bh = eh.get("benefit_hypothesis", {})
        if bh:
            print()
            print(f"  {bold('Benefit Hypothesis:')}")
            print(f"    {color(bh.get('metric',''), C.FEAT)}: {bh.get('baseline','')} {ARROW} {color(bh.get('target',''), C.DONE)}")
            print(f"    Timeframe: {bh.get('timeframe', '')}")

        li = eh.get("leading_indicators", [])
        if li:
            print()
            print(f"  {bold('Leading Indicators:')}")
            for ind in li:
                print(f"    {color(DOT, C.DONE)} {ind}")

        la = eh.get("lagging_indicators", [])
        if la:
            print(f"  {bold('Lagging Indicators:')}")
            for ind in la:
                print(f"    {color(DOT, C.FEAT)} {ind}")

        kc = eh.get("kill_criteria", [])
        if kc:
            print()
            print(f"  {bold('Kill Criteria:')}")
            for k in kc:
                print(f"    {color(DOT, C.ERR)} {k}")

        lbc = eh.get("lean_business_case", {})
        if lbc:
            print()
            print(f"  {bold('Lean Business Case:')}")
            print(f"    Problem:     {lbc.get('problem', '')}")
            print(f"    Opportunity: {lbc.get('opportunity', '')}")
            print(f"    MVP:         {color(lbc.get('mvp', ''), C.DONE)}")
            opts = lbc.get("options_considered", [])
            if opts:
                print(f"    Options:")
                for o in opts:
                    print(f"      {DOT} {o}")

    elif item.get("hypothesis"):
        print()
        print(f"  {bold('Hypothesis:')}")
        print(f"    {color(item['hypothesis'], C.MUTED)}")

    # Contributors
    contribs = item.get("contributors") or item.get("contributions") or []
    if contribs:
        print()
        print(f"  {bold('Contributors:')}")
        for c in contribs:
            person = c.get("person", "?")
            role = c.get("role", "?")
            cw = c.get("cw", "?")
            rs = c.get("rs", "")
            rs_str = f"  rs={rs}" if rs else ""
            print(f"    {DOT} {person:12s}  role={role:12s}  cw={cw}{rs_str}")

    # Child items (for epics -> features, features -> stories)
    if item.get("features"):
        print()
        print(f"  {bold('Features:')}")
        for f in item["features"]:
            w = f.get("wsjf", wsjf_score(f))
            print(f"    {TEE}{DASH}{DASH} {color(f['id'], C.FEAT)} {f['title']}  "
                  f"{status_badge(f.get('status'))}  WSJF={w}")

    if item.get("stories"):
        print()
        print(f"  {bold('Stories:')}")
        for s in item["stories"]:
            print(f"    {TEE}{DASH}{DASH} {color(s['id'], C.STORY)} {s['title']}  "
                  f"{status_badge(s.get('status'))}  JS={s.get('js',0)}  "
                  f"@{s.get('iteration','?')}")

    if item.get("epics"):
        print()
        print(f"  {bold('Epics:')}")
        for e in item["epics"]:
            w = e.get("wsjf", wsjf_score(e))
            print(f"    {TEE}{DASH}{DASH} {color(e['id'], C.EPIC)} {e['title']}  "
                  f"{status_badge(e.get('status'))}  WSJF={w}")

    print()


def cmd_status(backlog, args):
    """Show project or iteration status summary."""
    iter_filter = getattr(args, "iteration", None)

    if iter_filter:
        _show_iteration_status(backlog, iter_filter, args)
        return

    # Overall project status
    items = collect_items(backlog)
    stories = [i for i in items if i["level"] == "Story"]
    features = [i for i in items if i["level"] == "Feature"]
    epics = [i for i in items if i["level"] == "Epic"]

    done_stories = [s for s in stories if s.get("status") == "Done"]
    in_progress = [s for s in stories if s.get("status") == "In Progress"]
    planned = [s for s in stories if s.get("status") == "Planned"]

    total_sp = sum(s.get("js", 0) for s in stories)
    done_sp = sum(s.get("js", 0) for s in done_stories)
    ip_sp = sum(s.get("js", 0) for s in in_progress)

    pct = round(done_sp / total_sp * 100) if total_sp else 0

    print()
    print(bold(color("  EDPA Project Status", C.HEADER)))
    print(color(f"  {backlog['project']['name']}", C.MUTED))
    print(color(f"  {backlog['project']['registration']}  |  {backlog['project']['program']}", C.MUTED))
    print()

    # Progress bar
    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = color("\u2588" * filled, C.DONE) + color("\u2591" * (bar_width - filled), C.MUTED)
    print(f"  Progress: {bar} {bold(f'{pct}%')}")
    print()

    print(f"  {bold('Story Points:')}")
    print(f"    Total:        {total_sp} SP")
    print(f"    {color('Done:', C.DONE)}         {done_sp} SP  ({len(done_stories)} stories)")
    print(f"    {color('In Progress:', C.PROGRESS)}  {ip_sp} SP  ({len(in_progress)} stories)")
    print(f"    {color('Planned:', C.PLANNED)}      {sum(s.get('js', 0) for s in planned)} SP  ({len(planned)} stories)")
    print()

    print(f"  {bold('Hierarchy:')}")
    print(f"    Epics:    {len(epics)}")
    print(f"    Features: {len(features)}")
    print(f"    Stories:  {len(stories)}")
    print()

    # Per-iteration velocity
    iter_ids = sorted(set(s.get("iteration") for s in stories if s.get("iteration")))
    if iter_ids:
        print(f"  {bold('Iteration Velocity:')}")
        for it_id in iter_ids:
            it_stories = [s for s in done_stories if s.get("iteration") == it_id]
            sp = sum(s.get("js", 0) for s in it_stories)
            bar_mini = color("\u2588" * (sp // 2), C.DONE) if sp else ""
            print(f"    {it_id:16s}  {sp:3d} SP  {bar_mini}")
        print()


def _show_iteration_status(backlog, iteration_id, args):
    """Show status for a specific iteration."""
    root = find_repo_root()
    iter_data = load_iteration(root, iteration_id) if root else None

    items = collect_items(backlog)
    stories = [i for i in items if i["level"] == "Story" and i.get("iteration") == iteration_id]

    if not stories:
        print(color(f"  No stories found for iteration '{iteration_id}'.", C.WARN))
        return

    done = [s for s in stories if s.get("status") == "Done"]
    total_sp = sum(s.get("js", 0) for s in stories)
    done_sp = sum(s.get("js", 0) for s in done)
    pct = round(done_sp / total_sp * 100) if total_sp else 0

    print()
    print(bold(color(f"  Iteration: {iteration_id}", C.HEADER)))

    if iter_data:
        it = iter_data.get("iteration", {})
        print(color(f"  {it.get('dates', '')}  |  Status: {it.get('status', '?')}  |  Cadence: {it.get('cadence', '?')}", C.MUTED))

    print()

    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = color("\u2588" * filled, C.DONE) + color("\u2591" * (bar_width - filled), C.MUTED)
    print(f"  Delivery: {bar} {bold(f'{pct}%')}  ({done_sp}/{total_sp} SP)")
    print()

    print(f"  {bold('Stories:')}")
    for s in stories:
        assignee = s.get("assignee", "?")
        print(f"    {color(s['id'], C.STORY):20s} {s['title']:30s}  {status_badge(s.get('status'))}  "
              f"JS={s.get('js',0)}  {color(f'-> {assignee}', C.DIM)}")
    print()

    if iter_data:
        edpa = iter_data.get("edpa", {})
        if edpa:
            inv = color("PASS", C.OK) if edpa.get("invariants_passed") else color("FAIL", C.ERR)
            print(f"  {bold('EDPA:')}")
            print(f"    Mode:       {edpa.get('mode', '?')}")
            print(f"    Invariants: {inv}")
            print()


def cmd_wsjf(backlog, args):
    """Display items ranked by WSJF score."""
    level_filter = getattr(args, "level", None)

    items = collect_items(backlog)

    if level_filter in ("epic", "epics"):
        candidates = [i for i in items if i["level"] == "Epic"]
    elif level_filter in ("feature", "features"):
        candidates = [i for i in items if i["level"] == "Feature"]
    else:
        # Default: show both epics and features
        candidates = [i for i in items if i["level"] in ("Epic", "Feature")]

    # Compute and sort by WSJF descending
    for c in candidates:
        c["_wsjf"] = c.get("wsjf", wsjf_score(c))

    candidates.sort(key=lambda x: x["_wsjf"], reverse=True)

    print()
    print(bold(color("  WSJF Priority Ranking", C.HEADER)))
    print()

    # Table header
    header = f"  {'Rank':>4}  {'ID':8s}  {'Title':30s}  {'WSJF':>6}  {'JS':>4}  {'BV':>4}  {'TC':>4}  {'RR':>4}  {'Status':12s}  Level"
    print(color(header, C.MUTED))
    print(color(f"  {'─' * 105}", C.MUTED))

    for rank, c in enumerate(candidates, 1):
        lc = level_color(c["level"])
        wsjf_val = c["_wsjf"]

        # WSJF color: high=green, medium=yellow, low=gray
        if wsjf_val >= 4.0:
            wsjf_str = color(f"{wsjf_val:6.2f}", C.OK)
        elif wsjf_val >= 2.5:
            wsjf_str = color(f"{wsjf_val:6.2f}", C.WARN)
        else:
            wsjf_str = color(f"{wsjf_val:6.2f}", C.MUTED)

        title = c.get("title", "")[:30]
        status = c.get("status", "?")

        print(f"  {rank:>4}  {color(c['id'], lc):18s}  {title:30s}  {wsjf_str}  "
              f"{c.get('js',0):>4}  {c.get('bv',0):>4}  {c.get('tc',0):>4}  {c.get('rr',0):>4}  "
              f"{status_badge(status):22s}  {color(c['level'], lc)}")

    print()
    print(color(f"  WSJF = (BV + TC + RR) / JS   |   Higher = prioritize first", C.MUTED))
    print()


def cmd_validate(backlog, args):
    """Validate backlog integrity."""
    items = collect_items(backlog)
    stories = [i for i in items if i["level"] == "Story"]
    features = [i for i in items if i["level"] == "Feature"]
    epics = [i for i in items if i["level"] == "Epic"]

    errors = []
    warnings = []

    print()
    print(bold(color("  EDPA Backlog Validation", C.HEADER)))
    print()

    # 1. All stories must have assignee
    for s in stories:
        if not s.get("assignee"):
            errors.append(f"{s['id']} ({s.get('title','')}): missing assignee")

    # 2. All stories must have JS
    for s in stories:
        if not s.get("js") and s.get("js") != 0:
            errors.append(f"{s['id']} ({s.get('title','')}): missing JS (job size)")

    # 3. Story JS should be <= 8
    for s in stories:
        js = s.get("js", 0)
        if js and js > 8:
            warnings.append(f"{s['id']} ({s.get('title','')}): JS={js} exceeds recommended max of 8")

    # 4. All stories must have parent
    for s in stories:
        if not s.get("parent"):
            errors.append(f"{s['id']} ({s.get('title','')}): missing parent feature")

    # 5. All stories should have iteration
    for s in stories:
        if not s.get("iteration"):
            warnings.append(f"{s['id']} ({s.get('title','')}): missing iteration assignment")

    # 6. Check WSJF consistency
    for item in epics + features:
        stored_wsjf = item.get("wsjf")
        if stored_wsjf is not None:
            computed = wsjf_score(item)
            if abs(stored_wsjf - computed) > 0.05:
                warnings.append(f"{item['id']}: stored WSJF={stored_wsjf} != computed {computed}")

    # 7. Check for duplicate IDs
    ids = [i.get("id") for i in items if i.get("id")]
    seen = set()
    for item_id in ids:
        if item_id in seen:
            errors.append(f"Duplicate ID: {item_id}")
        seen.add(item_id)

    # 8. Check contributors CW values are reasonable
    for s in stories:
        contribs = s.get("contributors", [])
        for c in contribs:
            cw = c.get("cw", 0)
            if cw < 0 or cw > 1.5:
                warnings.append(f"{s['id']}: contributor {c.get('person','?')} has unusual cw={cw}")

    # Print results
    checks = [
        ("Story assignees present", not any("missing assignee" in e for e in errors)),
        ("Story JS values present", not any("missing JS" in e for e in errors)),
        ("Story JS <= 8", not any("exceeds recommended" in w for w in warnings)),
        ("Parent references valid", not any("missing parent" in e for e in errors)),
        ("Iteration assignments", not any("missing iteration" in w for w in warnings)),
        ("WSJF consistency", not any("stored WSJF" in w for w in warnings)),
        ("No duplicate IDs", not any("Duplicate ID" in e for e in errors)),
        ("CW values valid", not any("unusual cw" in w for w in warnings)),
    ]

    for label, passed in checks:
        icon = color("PASS", C.OK) if passed else color("FAIL", C.ERR)
        print(f"  [{icon}]  {label}")

    if errors:
        print()
        print(f"  {bold(color('Errors:', C.ERR))}")
        for e in errors:
            print(f"    {color('x', C.ERR)} {e}")

    if warnings:
        print()
        print(f"  {bold(color('Warnings:', C.WARN))}")
        for w in warnings:
            print(f"    {color('!', C.WARN)} {w}")

    print()
    print(f"  {bold('Summary:')}")
    print(f"    Items:    {len(items)}")
    print(f"    Stories:  {len(stories)}")
    print(f"    Errors:   {color(str(len(errors)), C.ERR if errors else C.OK)}")
    print(f"    Warnings: {color(str(len(warnings)), C.WARN if warnings else C.OK)}")

    if not errors and not warnings:
        print()
        print(f"  {color('All checks passed. Backlog is valid.', C.OK)}")
    elif not errors:
        print()
        print(f"  {color('No errors. Backlog is valid (with warnings).', C.WARN)}")
    else:
        print()
        print(f"  {color('Backlog has errors that should be fixed.', C.ERR)}")

    print()
    return len(errors)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="edpa_backlog",
        description="EDPA Git-native backlog management CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # tree
    p_tree = sub.add_parser("tree", help="Display work item hierarchy")
    p_tree.add_argument("--level", choices=["epic", "epics", "feature", "features", "story", "stories"],
                        help="Filter to specific level")
    p_tree.add_argument("--iteration", help="Filter stories to specific iteration (e.g. PI-2026-1.1)")

    # show
    p_show = sub.add_parser("show", help="Show details for a specific item")
    p_show.add_argument("item_id", help="Work item ID (e.g. S-200, E-10, F-100)")

    # status
    p_status = sub.add_parser("status", help="Show project/iteration status")
    p_status.add_argument("--iteration", help="Show status for specific iteration")

    # wsjf
    p_wsjf = sub.add_parser("wsjf", help="Show WSJF-ranked backlog")
    p_wsjf.add_argument("--level", choices=["epic", "epics", "feature", "features"],
                        help="Filter to specific level")

    # validate
    sub.add_parser("validate", help="Validate backlog integrity")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    root = find_repo_root()
    if root is None:
        print(color("Error: Cannot find .edpa/backlog.yaml. Run from the EDPA project directory.", C.ERR))
        sys.exit(1)

    backlog = load_backlog(root)

    if args.command == "tree":
        cmd_tree(backlog, args)
    elif args.command == "show":
        cmd_show(backlog, args)
    elif args.command == "status":
        cmd_status(backlog, args)
    elif args.command == "wsjf":
        cmd_wsjf(backlog, args)
    elif args.command == "validate":
        err_count = cmd_validate(backlog, args)
        sys.exit(1 if err_count else 0)


if __name__ == "__main__":
    main()
