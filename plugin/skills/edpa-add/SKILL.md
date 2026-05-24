---
name: edpa:add
user-invocable: true
description: >
  Create a new backlog item (Initiative / Epic / Feature / Story / Defect / Event)
  via strict GH-first flow: gh issue create → server-assigned number → EDPA ID =
  "{prefix}-{num}" → GH title rewritten to "{ID}: {title}" → sub-issue link to
  parent → local YAML → auto-commit. Requires sync config; no local-only mode.
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+, edpa.yaml sync config
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Add — Create Backlog Item

## What this does

Creates a new work item in the EDPA backlog using **strict GH-first flow**:

1. `gh issue create` → GitHub assigns an atomic issue number (#42)
2. `gh issue edit --title` → GH title becomes `"S-42: <title>"` so the GH UI matches the local identifier
3. EDPA ID = type prefix + issue number → `I-3`, `E-15`, `F-8`, `S-42`, `D-7`, `EV-2`
4. `addSubIssue` GraphQL mutation → child appears under parent's "Sub-issues" panel in the GH UI
5. `gh project item-add` → adds to GitHub Project; native Issue Type assigned via GraphQL
6. Writes `.edpa/backlog/<type>/S-42.md` (YAML frontmatter + empty Markdown body)
7. Updates `.edpa/config/issue_map.yaml` with `{issue_number, project_item_id, node_id}`
8. `git commit -m "feat(S-42): <title>"`

**Why strict GH-first (no local fallback):** Pilot feedback showed two ID series — sequential local + GH issue numbers — drifting whenever someone added items offline or before `/edpa:setup`. A later `sync push` couldn't reconcile them. GitHub's atomic issue counter is now the single source of truth. If sync is not configured, `add` fails fast with an explicit hint to run `/edpa:setup`.

**Title format mirror:** The GH issue title always carries the EDPA ID prefix (`I-3: …`, `S-42: …`) so a search for `S-42` lands on the same item in repo and GH. Sub-issue linking keeps the parent-child hierarchy visible in the GH UI, not just in local YAML.

## Arguments

`$ARGUMENTS` — natural language description of the item to create. Examples:
- `Story "Implementovat login endpoint" --parent F-1 --js 5`
- `Epic "Authentication" --parent I-1`
- `Initiative "Medical Platform"`
- `Feature "OAuth flow" --parent E-1 --js 8 --bv 13 --tc 5 --rr 3`
- `Defect "Login button greyed out" --parent F-1`

## Steps

### 1. Verify sync config exists

Before invoking `backlog.py add`, ensure `.edpa/config/edpa.yaml` has the `sync.github_org`, `sync.github_repo`, and `sync.github_project_number` fields set. If they are missing, do **not** attempt the add — instead tell the user to run `/edpa:setup` first. The CLI will refuse the add anyway, but failing in the skill avoids a confusing CLI error.

### 2. Parse arguments

Extract from `$ARGUMENTS`:
- **type** — one of `Initiative`, `Epic`, `Feature`, `Story`, `Defect`, `Event` (required)
- **title** — item title (required)
- **parent** — parent EDPA ID (required for Epic/Feature/Story/Defect/Event)
- **js** — Job Size, modified Fibonacci 1–100 (Stories only, optional)
- **bv / tc / rr** — WSJF inputs (optional)
- **assignee** — person ID from people.yaml (optional)
- **iteration** — e.g. `PI-2026-1.2` (optional)

If type or title is missing, ask the user before proceeding.

If parent is missing for a non-Initiative item, show the current backlog tree and ask:
```bash
python3 .edpa/engine/scripts/backlog.py tree
```

### 3. Run backlog.py add

```bash
python3 .edpa/engine/scripts/backlog.py add \
  --type <TYPE> \
  --title "<TITLE>" \
  [--parent <PARENT_ID>] \
  [--js <JS>] \
  [--bv <BV>] \
  [--tc <TC>] \
  [--rr <RR>] \
  [--assignee <PERSON_ID>] \
  [--iteration <ITER_ID>]
```

The script will:
- fail-fast with exit code 1 if sync config is missing
- create the GH issue, rewrite its title to `"<ID>: <title>"`, set the Issue Type, add it to the project, and link it under its parent
- write the local `.md`, update `issue_map.yaml` (with `node_id`), and commit

### 4. Show result

Display the created item ID, GH issue URL, and file path. If the user created multiple items in sequence, offer to show the updated backlog tree:

```bash
python3 .edpa/engine/scripts/backlog.py tree
```

### 5. Suggest next steps

- If type is Initiative or Epic: "Add child items next — what Epics/Features go under this?"
- If type is Story: "Set iteration when known: `--iteration PI-2026-1.X`"
- If JS is missing on a Story: "Add Job Size for WSJF: `backlog.py add --type Story ... --js <1-100>`"

## What NOT to do

- **Never write YAML files directly** — always use `backlog.py add` so hierarchy, ID assignment, GH issue creation, title rewrite, and sub-issue linking all happen atomically.
- **Never call `gh issue create` manually** — it skips the title rewrite (no `S-42:` prefix) and the sub-issue link, leaving the GH UI inconsistent with the local backlog.
- **Never invent IDs** — every EDPA ID is `{prefix}-{gh_issue_number}` where the number comes from `gh issue create`. Inventing them creates orphans.
- **Never try a "local-only" workaround** when sync is not configured — the `--local` flag was removed because it produced divergent ID series. Run `/edpa:setup` first.
- **Never skip `--parent`** for non-Initiative items — flat backlogs break WSJF calculation, engine allocation, and the GH sub-issue panel.
- **Do not add `.github/ISSUE_TEMPLATE/` files** — EDPA uses org-level Issue Types (stronger than templates) and the skill covers all creation paths. GH UI templates would be a third source of truth with no consumer.
