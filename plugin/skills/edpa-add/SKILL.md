---
name: edpa:add
user-invocable: true
description: >
  Create a new backlog item (Initiative / Epic / Feature / Story / Defect /
  Event / Risk). Dual mode: V1 GH-first (gh issue create → server number →
  EDPA ID) or V2 local-first via --local (id_counter.yaml, no gh). Default:
  GH-first when sync config exists; --local opts into the V2 path.
license: MIT
compatibility: GitHub CLI (gh) optional, Python 3.10+, MCP edpa server
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Add — Create Backlog Item

## What this does

Creates a new work item in the EDPA backlog. Two paths are supported.

### V1 GH-first (default when sync is configured)

1. `gh issue create` → GitHub assigns an atomic issue number (#42)
2. `gh issue edit --title` → GH title becomes `"S-42: <title>"` so the GH UI matches the local identifier
3. EDPA ID = type prefix + issue number → `I-3`, `E-15`, `F-8`, `S-42`, `D-7`, `EV-2`
4. `addSubIssue` GraphQL mutation → child appears under parent's "Sub-issues" panel in the GH UI
5. `gh project item-add` → adds to GitHub Project; native Issue Type assigned via GraphQL
6. Writes `.edpa/backlog/<type>/S-42.md` (YAML frontmatter + empty Markdown body)
7. Updates `.edpa/config/issue_map.yaml` with `{issue_number, project_item_id, node_id}`
8. `git commit -m "feat(S-42): <title>"`

### V2 local-first (opt-in via `--local`)

1. `id_counter.next_id(type)` from `.edpa/config/id_counters.yaml` → next available number; atomic via file lock + `max(counter, fs_scan)`
2. EDPA ID = `{prefix}-{num}` (same shape as V1, but allocated locally — no `gh` roundtrip)
3. MCP `edpa_item_create` handler validates parent type hierarchy in-process (Story→Feature, Feature→Epic, Epic→Initiative)
4. Writes `.edpa/backlog/<type>/{ID}.md` directly via `_md_frontmatter.save_md`
5. `git commit -m "feat({ID}): <title>"` — no `issue_map.yaml`, no GH calls

**Default selection logic:**
- Sync configured + no `--local` → GH-first path (V1 behavior preserved)
- Sync missing + no `--local` → fail-fast with hint to run `/edpa:setup` OR pass `--local`
- `--local` set → V2 local-first path regardless of sync config

**Why we keep both for now:** V2 hard-cut happens in `docs/v2/plan.md` Krok 6. Until then, existing GH-coupled projects keep working unchanged; new projects (or those migrated via `migrate_v1_to_v2.py`) use `--local`.

**Title format mirror (GH path only):** The GH issue title carries the EDPA ID prefix (`I-3: …`, `S-42: …`) so a search for `S-42` lands on the same item in repo and GH. The local path skips this — git history is the audit trail.

**Title format mirror:** The GH issue title always carries the EDPA ID prefix (`I-3: …`, `S-42: …`) so a search for `S-42` lands on the same item in repo and GH. Sub-issue linking keeps the parent-child hierarchy visible in the GH UI, not just in local YAML.

## Arguments

`$ARGUMENTS` — natural language description of the item to create. Examples:
- `Story "Implementovat login endpoint" --parent F-1 --js 5`
- `Epic "Authentication" --parent I-1`
- `Initiative "Medical Platform"`
- `Feature "OAuth flow" --parent E-1 --js 8 --bv 13 --tc 5 --rr 3`
- `Defect "Login button greyed out" --parent F-1`

## Steps

### 1. Choose mode

- **V1 GH-first (default):** confirm `.edpa/config/edpa.yaml` has `sync.github_org`, `sync.github_repo`, and `sync.github_project_number`. If missing, tell the user to either run `/edpa:setup` or pass `--local`.
- **V2 local-first:** pass `--local`. Works without any sync config; ID comes from `.edpa/config/id_counters.yaml` (auto-created on first use).

Pick V2 local when: the project is offline-only, hosted on GitLab/Forgejo, or the user already migrated to V2. Otherwise V1 GH-first stays the default until Krok 6 in `docs/v2/plan.md` deletes the GH path.

### 2. Parse arguments

Extract from `$ARGUMENTS`:
- **type** — one of `Initiative`, `Epic`, `Feature`, `Story`, `Defect`, `Event`, `Risk` (required)
- **title** — item title (required)
- **parent** — parent EDPA ID (required for Epic/Feature/Story; flexible for Defect/Event/Risk)
- **js** — Job Size, modified Fibonacci 1–100 (Stories only, optional)
- **bv / tc / rr** — WSJF inputs (optional)
- **assignee** — person ID from people.yaml (optional)
- **iteration** — e.g. `PI-2026-1.2` (optional)
- **local** — opt into V2 local-first path (no `gh`)

If type or title is missing, ask the user before proceeding.

If parent is missing for a non-Initiative non-Defect/Event/Risk item, show the current backlog tree and ask:
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
  [--iteration <ITER_ID>] \
  [--local]
```

The script will:
- without `--local`: fail-fast with exit code 1 if sync config is missing; otherwise create the GH issue, rewrite its title to `"<ID>: <title>"`, set the Issue Type, add it to the project, link it under its parent, write the local `.md`, update `issue_map.yaml`, and commit
- with `--local`: allocate the next ID from `.edpa/config/id_counters.yaml`, write the local `.md` via the MCP `edpa_item_create` handler (parent type validated in-process), and commit. No `gh` calls.

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

- **Never write YAML files directly** — always use `backlog.py add` so ID allocation, parent validation, and frontmatter shape all go through one path (MCP `edpa_item_create` for `--local`, GH factory otherwise).
- **Never call `gh issue create` manually** in the GH path — it skips the title rewrite (no `S-42:` prefix) and the sub-issue link, leaving the GH UI inconsistent with the local backlog.
- **Never invent IDs.** GH path: ID comes from `gh issue create`. Local path: ID comes from `id_counter.next_id()` (counter file + fs_scan). Both are atomic; manual IDs cause collisions.
- **Never skip `--parent`** for Story/Feature/Epic — flat backlogs break WSJF calculation, engine allocation, and (GH path) the sub-issue panel.
- **Do not add `.github/ISSUE_TEMPLATE/` files** — EDPA uses org-level Issue Types (stronger than templates) and the skill covers all creation paths. GH UI templates would be a third source of truth with no consumer.
