---
description: Update fields on a backlog item (iteration, js, WSJF inputs, assignee, title) with before/after diff
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Update Item

Update one or more fields on a backlog item. `$ARGUMENTS` is `<item-id> [field=value ...]`.

**Allowed fields:** `title`, `iteration`, `assignee`, `js`, `bv`, `tc`, `rr_oe`

Examples:
- `S-42 iteration=PI-2026-1.4`
- `S-42 js=8 bv=13`
- `F-100 assignee=urbanek`
- `S-42 title="New title"`
- `S-42` — interactive: guided field selection

## Steps

1. Parse `$ARGUMENTS`. Extract item ID (required — ask if missing).
   Parse remaining tokens as `field=value` pairs (quotes supported for title).

2. Read the current item with the `edpa_item` MCP tool. Show current values for the
   fields the user is about to change (the "before" snapshot). For interactive mode
   (no fields given), show all editable fields and ask which ones to change.

3. Call `edpa_item_update`:
   ```
   edpa_item_update(item_id="<id>", fields={"<field>": <value>, ...})
   ```
   On error (invalid field, invalid iteration/person ID): show the error and stop.

4. Show a before/after diff of changed fields:
   ```
   iteration: PI-2026-1.3 → PI-2026-1.4
   js:        5 → 8   (wsjf: 2.40 → 3.84)
   ```

5. Auto-commit:
   ```bash
   git add .edpa/backlog/
   git commit -m "chore(<item-id>): update <field-list>"
   ```
   Where `<field-list>` is the comma-joined list of changed fields (e.g. `js,bv`).

## Notes

- `wsjf` is always recomputed automatically from `js`, `bv`, `tc`, `rr_oe` — do not
  pass it directly.
- To change status use `/edpa:change-state`; to reparent an item use
  `edpa_item_link_parent`.
- Person IDs come from `id:` entries in `.edpa/config/people.yaml`.
- Numeric fields (`js`, `bv`, `tc`, `rr_oe`) accept integers only.
