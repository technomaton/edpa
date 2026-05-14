---
name: edpa:sync
user-invocable: true
description: >
  Bidirectional sync between GitHub Projects and .edpa/backlog/ YAML files.
  Default (no args) runs pull --commit then push for full bidirectional sync.
  Subcommands: pull, push, diff, status, conflicts, setup-refresh, add-iteration.
  Use when user says "sync", "pull from GitHub", "push to GitHub", or "check sync status".
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+, .edpa/config/edpa.yaml
allowed-tools: Read Write Bash(python3 *) Bash(gh *) Bash(git *) Grep
metadata:
  author: Jaroslav Urbánek
  version: 1.0.0
  domain: governance
  phase: sync
  standard: AgentSkills v1.0
---

# EDPA Sync — GitHub Projects ↔ .edpa/backlog/

## What this does

Synchronizes work items between GitHub Projects v2 and local `.edpa/backlog/` YAML files.
Supports pull (GitHub → local), push (local → GitHub), diff, and status commands.

## Arguments

`$ARGUMENTS` = optional subcommand: "pull", "push", "diff", "status", "conflicts",
"setup-refresh", "add-iteration <ID>", or "pull --commit".

### Argument resolution (when $ARGUMENTS is empty)

If `$ARGUMENTS` is empty or blank, run the **full bidirectional sync**:

1. `python3 .claude/edpa/scripts/sync.py pull --commit` (GitHub → local YAML, auto-commit)
2. If step 1 exits non-zero (network/auth error, unresolved conflicts), **stop** — do not push.
   Surface the error and let the user decide (e.g., `/edpa:sync conflicts`).
3. `python3 .claude/edpa/scripts/sync.py push` (local YAML → GitHub)
4. Report a one-line summary: items pulled, items pushed, any failures.

If `$ARGUMENTS` is `"help"`, print the subcommand list instead:

```
Subcommands:
  (empty)         Full sync: pull --commit, then push   ← default
  pull            GitHub Projects -> .edpa/backlog/
  pull --commit   Pull + auto-commit changes
  push            .edpa/backlog/ -> GitHub Projects
  diff            Show what would change (dry-run)
  status          Show last sync time, local/remote changes, conflicts
  conflicts       List/resolve cross-side conflicts
  setup-refresh   Rebuild field_ids/option_ids/issue_map
  add-iteration <ID>  Add an iteration option to the GH Iteration field
```

## Prerequisites

- `.edpa/config/edpa.yaml` exists with sync settings (github_org, github_project_number)
- `gh auth status` passes
- `.edpa/backlog/` directory exists with per-item YAML files

## Operations

### Pull (GitHub → Local)

```bash
python3 .claude/edpa/scripts/sync.py pull
```

Fetches all items from GitHub Project, updates `.edpa/backlog/{type}/{ID}.md` files (YAML frontmatter + Markdown body).
With `--commit`: auto-commits changes after pull.

### Push (Local → GitHub)

```bash
python3 .claude/edpa/scripts/sync.py push
```

Reads `.edpa/backlog/` YAML files, updates GitHub Project items (field values, status, assignees).

### Diff

```bash
python3 .claude/edpa/scripts/sync.py diff
```

Shows differences between local YAML and GitHub Project state without modifying anything.

### Status

```bash
python3 .claude/edpa/scripts/sync.py status
```

Shows last sync timestamp, number of local/remote changes, conflict count.

## Conflict handling

When both local and remote changed the same field:
1. Show conflict to user with both values
2. Ask user to choose: local, remote, or manual merge
3. Log resolution in `.edpa/changelog.jsonl`

## Error handling

- GitHub API unavailable → "Cannot reach GitHub API. Check `gh auth status`."
- Missing project number → "Configure github_project_number in .edpa/config/edpa.yaml first."
- Sync state corrupt → "Reset sync state? This will do a full pull."
