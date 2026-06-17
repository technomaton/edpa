---
name: add
user-invocable: true
description: >
  Create a new backlog item (Initiative / Epic / Feature / Story / Defect /
  Event / Risk) — V2 local-first. ID allocated from id_counters.yaml,
  parent hierarchy validated by MCP edpa_item_create, YAML written under
  .edpa/backlog/, auto-committed. No GitHub calls at create time;
  PR-derived signals arrive separately via the contribution-sync workflow.
license: MIT
compatibility: Python 3.10+, MCP edpa server
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Add — Create Backlog Item

## What this does

V2 local-first add. No `gh` calls.

1. `id_counter.next_id(type)` from `.edpa/config/id_counters.yaml` →
   next available number, atomic via file lock + `max(counter, fs_scan)`.
2. EDPA ID = `{prefix}-{num}` → `I-3`, `E-15`, `F-8`, `S-42`, `D-7`,
   `EV-2`, `R-1`.
3. MCP `edpa_item_create` handler validates parent type hierarchy
   in-process (Story→Feature, Feature→Epic, Epic→Initiative).
4. Writes `.edpa/backlog/<type>/{ID}.md` directly via
   `_md_frontmatter.save_md`.
5. `git commit -m "feat({ID}): <title>"`.

PR-derived signals (pr_reviewer, issue_comment) arrive
asynchronously via the CI workflow at
`.github/workflows/edpa-contribution-sync.yml` — see
`/edpa:setup --with-ci` and `docs/v2/decisions.md` ADR-012.

## Parallel ID allocation — collision handling

ID allocation is **local-first** (no central coordinator). If two devs both
pull `main` when last Story is `S-4` and both run `/edpa:add Story`, both
will get `S-5` locally — the collision surfaces at PR merge time.

EDPA detects + resolves this via four defense layers:
- **Pre-commit hook** (`validate_ids.py --staged`) — local staged consistency
- **Pre-push hook** (`validate_ids.py --pre-push`) — blocks push if local ID
  already exists on `origin/main`
- **CI workflow** (`edpa-collision-check.yml`) — comments on PR + fails check
  when collision detected
- **Manual recovery** (`renumber_collisions.py --apply`) — renames local
  file, rewrites `id:` field, updates `parent:` refs in dependent items,
  bumps `id_counters.yaml`. Then dev: `git add . && git commit && git merge
  main && git push` (resolve `id_counters.yaml` merge conflict by taking the
  MAX value).

Full guide with decision tree + common shapes:
[`docs/dev-collisions.md`](../../../docs/dev-collisions.md).

## Arguments

`$ARGUMENTS` — natural language description. Examples:
- `Story "Implementovat login endpoint" --parent F-1 --js 5`
- `Epic "Authentication" --parent I-1`
- `Initiative "Medical Platform"`
- `Feature "OAuth flow" --parent E-1 --js 8 --bv 13 --tc 5 --rr 3`
- `Defect "Login button greyed out" --parent F-1`

## Steps

### 1. Parse arguments

Extract from `$ARGUMENTS`:
- **type** — one of `Initiative`, `Epic`, `Feature`, `Story`, `Defect`, `Event`, `Risk` (required)
- **title** — item title (required)
- **parent** — parent EDPA ID (required for Epic/Feature/Story; flexible for Defect/Event/Risk)
- **js** — Job Size, modified Fibonacci 1–100 (Stories only, optional)
- **bv / tc / rr** — WSJF inputs (optional)
- **assignee** — person ID from people.yaml (optional)
- **iteration** — e.g. `PI-2026-1.2` (optional)
- **contributor** — repeatable `PERSON:ROLE:CW` (optional)

If type or title is missing, ask the user before proceeding.

If parent is missing for Story/Feature/Epic, show the current backlog
tree and ask:

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
  [--iteration <ITER_ID>] \
  [--contributor <PERSON:ROLE:CW>]
```

The script will:
- allocate the next ID atomically from `.edpa/config/id_counters.yaml`
  (auto-created on first use)
- validate parent existence + type hierarchy via MCP
- write `.edpa/backlog/<type>/{ID}.md` with frontmatter + empty body
- auto-commit `feat({ID}): <title>`

### 3. Show result

Display the created item ID and file path. Offer to show the backlog
tree if multiple items were added in sequence.

### 4. Suggest next steps

- Initiative/Epic → "Add child items: what Epics/Features go under this?"
- Story without `--js` → "Set Job Size for WSJF: re-run with `--js <1-100>`"
- Story without `--iteration` → "Set iteration when known: `--iteration PI-2026-1.X`"

## What NOT to do

- **Never write YAML files directly** — always use `backlog.py add` so
  ID allocation, parent validation, and frontmatter shape go through
  one path (MCP `edpa_item_create`).
- **Never invent IDs.** They come from `id_counter.next_id()` which
  uses a file lock + fs scan. Manual IDs collide.
- **Never skip `--parent`** for Story/Feature/Epic — flat backlogs
  break WSJF calculation and engine allocation.
- **Don't add `.github/ISSUE_TEMPLATE/` files.** V2 doesn't create
  GitHub Issues for backlog items.

## V1 → V2 note

Pre-2.0.0 the GH-first path created a GitHub Issue and used its
server-assigned number as the EDPA ID. That path was removed in
2.0.0 because (a) it required `gh auth` per developer, (b) lost
items survived loss of the GitHub repo, and (c) `sync.py` complexity
(~1800 lines) was eating ~30% of EDPA's codebase. See
`docs/v2/concept.md` for the full rationale, or the
`v1-github-coupled` branch tag for the historical implementation.
