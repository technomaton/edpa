---
name: add
user-invocable: true
description: >
  Create a new backlog item (Initiative / Epic / Feature / Story / Defect /
  Event / Risk) — V2 local-first. ID from the project's ID authority (the
  local counter, or a reservation on the shared git remote that is unique
  across worktrees, branches and developers), parent hierarchy validated
  by MCP edpa_item_create, YAML written under .edpa/backlog/,
  auto-committed. No GitHub calls at create time;
  PR-derived signals arrive separately via the contribution-sync workflow.
license: MIT
compatibility: Python 3.10+, MCP edpa server
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Add — Create Backlog Item

## What this does

V2 local-first add. No `gh` calls.

1. `id_counter.next_id(type)` → next available number. Where it comes
   from depends on the project's ID authority
   (`id_counter.py status` shows which):
   - **local** — `max(id_counters.yaml, fs_scan, clone high-water mark) + 1`
     under a file lock; unique within this clone (all its worktrees).
   - **remote** (ADR-014) — reserved in the ID ledger on the shared git
     remote first, so it is unique across worktrees, branches and
     developers. Takes ~2 s; needs the network.
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

## Parallel ID allocation

**Remote ID authority** (team projects — `ids.authority: remote`): the ID
is reserved on the shared remote before the file is written, so two
sessions cannot get the same one. There is nothing to merge "just to
claim the number" — the ticket file travels with the feature branch.

If the command fails with an ID-ledger message, **do not work around it**
by writing the file yourself or picking a number: an item without a
reservation is rejected by the pre-commit and pre-push hooks. Relay the
message — it says what to do (`init-remote` once per repository; fix the
connection; create the ticket from a clone that may push; or use a block
pre-reserved with `id_counter.py reserve`).

**Local ID authority** (solo / no shared remote): worktrees of one clone
share a sequence, but two clones can still mint the same number. That is
caught by the pre-push hook (`validate_ids.py --pre-push`, including the
usual case where both items sit at the same path) and repaired with
`renumber_collisions.py --apply`.

Full guide — switching a project to the ledger, the checks, recovery:
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
- allocate the next ID through the project's ID authority (local counter,
  or a reservation in the shared ledger)
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
- **Never invent IDs.** They come from `id_counter.next_id()`. Manual
  IDs collide, and under the remote ID authority the hooks reject any
  item that has no reservation.
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
