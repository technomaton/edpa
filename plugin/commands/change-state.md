---
description: Change the status of a backlog item (wraps edpa_item_transition with workflow validation)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Change State

Change the status of a backlog item. `$ARGUMENTS` is `<item-id> [<new-status>]`.

Examples: `S-42 Done`, `F-100 Implementing`, `D-7` (show status menu first).

## Status workflows

**Portfolio** (Initiative, Epic):
`Funnel → Reviewing → Analyzing → Ready → Implementing → Done`

**Delivery** (Feature, Story, Defect):
`Funnel → Analyzing → Backlog → Implementing → Validating → Deploying → Releasing → Done`

**Other** (Task, Event, Risk): any status string is accepted.

## Steps

1. Parse `$ARGUMENTS`: extract item ID (required — ask if missing). The second word,
   if present, is the target status.

2. Look up the current item with the `edpa_item` MCP tool. Show: ID, type, title,
   current status.

3. If target status was not supplied, display the allowed workflow for the item's type
   (see above) and ask the user to pick one.

4. Call `edpa_item_transition`:
   ```
   edpa_item_transition(item_id="<id>", status="<new-status>")
   ```
   On error: show the error message and stop (do NOT commit).

5. Auto-commit the YAML change:
   ```bash
   git add .edpa/backlog/
   git commit -m "chore(<item-id>): transition to <new-status>"
   ```
   The commit-msg hook requires an EDPA item ID in the scope — the transitioning item's
   ID (`<item-id>`) satisfies that requirement.

6. Report: `<item-id> → <new-status>` (plus `closed_at: <ts>` if transitioning to Done).

## What NOT to do

- Do NOT edit the YAML directly — `edpa_item_transition` enforces workflow rules and
  stamps `closed_at` (Done, first time only).
- Do NOT skip the commit — the transition is delivery evidence; the engine reads status
  change timestamps from the git log.
