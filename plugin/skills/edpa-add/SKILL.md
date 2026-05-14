---
name: edpa:add
user-invocable: true
description: >
  Create a new backlog item (Initiative / Epic / Feature / Story) using GH-first flow:
  gh issue create → server-assigned number → collision-free EDPA ID (e.g. S-42) →
  local YAML → auto-commit. Falls back to local-first when offline or before setup.
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+, edpa.yaml sync config
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Add — Create Backlog Item

## What this does

Creates a new work item in the EDPA backlog using **GH-first flow**:

1. `gh issue create` → GitHub assigns an atomic issue number (#42)
2. EDPA ID = type prefix + issue number → `S-42`, `E-15`, `F-8`, `I-3`
3. `gh project item-add` → adds to GitHub Project
4. Writes `.edpa/backlog/<type>/S-42.md` (YAML frontmatter + empty Markdown body for prose)
5. Updates `.edpa/config/issue_map.yaml`
6. `git commit -m "feat(S-42): <title>"`

**Why GH-first:** Multiple team members (especially with AI assistance) can create items simultaneously. Sequential local IDs (`S-5.yaml`) collide when two people run `backlog.py add` before either pushes. GitHub's issue number is an atomic server-side counter — no collision possible.

**Offline / pre-setup fallback:** Pass `--local` to use sequential local ID scan. Use before `/edpa:setup` has been run or when working without connectivity.

## Arguments

`$ARGUMENTS` — natural language description of the item to create. Examples:
- `Story "Implementovat login endpoint" --parent F-1 --js 5`
- `Epic "Authentication" --parent I-1`
- `Initiative "Medical Platform"`
- `Feature "OAuth flow" --parent E-1 --js 8 --bv 13 --tc 5 --rr 3`

## Steps

### 1. Parse arguments

Extract from `$ARGUMENTS`:
- **type** — one of `Initiative`, `Epic`, `Feature`, `Story` (required)
- **title** — item title (required)
- **parent** — parent EDPA ID (required for Epic/Feature/Story)
- **js** — Job Size, modified Fibonacci 1–100 (Stories only, optional)
- **bv / tc / rr** — WSJF inputs (optional)
- **assignee** — person ID from people.yaml (optional)
- **iteration** — e.g. `PI-2026-1.2` (optional)

If type or title is missing, ask the user before proceeding.

If parent is missing for Epic/Feature/Story, show the current backlog tree and ask:
```bash
python3 .edpa/engine/scripts/backlog.py tree
```

### 2. Run backlog.py add

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

The script auto-detects whether sync config is present in `edpa.yaml` and chooses GH-first or local-first accordingly.

### 3. Show result

Display the created item ID, GH issue URL (if GH-first), and file path. If the user created multiple items in sequence, offer to show the updated backlog tree:

```bash
python3 .edpa/engine/scripts/backlog.py tree
```

### 4. Suggest next steps

- If type is Initiative or Epic: "Add child items next — what Epics/Features go under this?"
- If type is Story: "Set iteration when known: `--iteration PI-2026-1.X`"
- If JS is missing on a Story: "Add Job Size for WSJF: `backlog.py add --type Story ... --js <1-100>`"

## What NOT to do

- **Never write YAML files directly** — always use `backlog.py add` so hierarchy, ID assignment, and GH sync happen correctly.
- **Never call `gh issue create` manually** — `backlog.py add` does it with correct labels and body format.
- **Never invent IDs** — IDs come from GH issue numbers (GH-first) or sequential scan (local-first). Inventing them causes conflicts.
- **Never skip `--parent`** for non-Initiative items — flat backlogs break WSJF calculation and engine allocation.
- **Do not add `.github/ISSUE_TEMPLATE/` files** — EDPA uses org-level Issue Types (stronger than templates) and the skill covers all creation paths. GH UI templates would be a third source of truth with no consumer. If a team wants GH UI forms, they add them manually outside EDPA core.
