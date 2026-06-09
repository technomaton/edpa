---
description: Add or remove a dependency edge between two backlog items (program board arrows)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Link Dependency

Add or remove a dependency between two backlog items.
`depends_on=[B]` on item A means "A depends on B" — B must land first.
These edges appear as arrows on the PI program board.

`$ARGUMENTS` is `<item-id> <depends-on-id> [remove]`.

Examples:
- `S-42 S-38` — S-42 now depends on S-38
- `S-42 S-38 remove` — remove that dependency

## Steps

1. Parse `$ARGUMENTS`:
   - `<item-id>` — the item that has the dependency (required — ask if missing)
   - `<depends-on-id>` — the prerequisite item (required — ask if missing)
   - `remove` keyword (optional; default action is `add`)

2. Call `edpa_item_link_dep`:
   ```
   edpa_item_link_dep(item_id="<id>", depends_on_id="<dep-id>", action="add"|"remove")
   ```
   On error (cycle detected, item not found, self-loop): show the error and stop.

3. Auto-commit:
   ```bash
   git add .edpa/backlog/
   git commit -m "chore(<item-id>): <add|remove> dependency on <dep-id>"
   ```

4. Report the updated `depends_on` list for `<item-id>`. If any dependencies remain,
   suggest viewing the program board: `/edpa:pi-planning <pi-id>`.

## Notes

- Cycles are rejected automatically — if A→B and B→C exist, adding C→A fails.
- Items can depend on items from different teams or iterations; the program board
  highlights cross-team dependency arrows in red until the prerequisite reaches Done.
- To view all dependency arrows for a PI at once: `/edpa:pi-planning <pi-id>`.
