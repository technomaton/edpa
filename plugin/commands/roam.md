---
description: Set the ROAM classification (Resolved / Owned / Accepted / Mitigated) on a Risk item
allowed-tools: Read, Bash
model: sonnet
---

# EDPA ROAM

Classify a Risk item using the SAFe ROAM framework.
`$ARGUMENTS` is `<risk-id> [<roam-status>]`.

**ROAM statuses:**
- `resolved` — the risk is resolved; it will not materialize
- `owned` — someone owns it; a mitigation plan exists
- `accepted` — acknowledged; no mitigation planned (accepted risk)
- `mitigated` — actions taken; risk level reduced but not eliminated

Examples: `R-1 owned`, `R-2 resolved`, `R-3` (show menu first).

## Steps

1. Parse `$ARGUMENTS`: extract risk ID (required — ask if missing). Extract
   `roam_status` if supplied as the second word; otherwise show the four statuses
   above and ask the user to pick one.

2. Look up the item with `edpa_item` MCP tool to confirm it is a Risk. Show: ID,
   title, current `roam_status` (if any).

3. Call `edpa_item_roam`:
   ```
   edpa_item_roam(item_id="<risk-id>", roam_status="<status>")
   ```
   On error (not a Risk item, invalid status): show the error and stop.

4. Auto-commit:
   ```bash
   git add .edpa/backlog/
   git commit -m "chore(<risk-id>): ROAM → <status>"
   ```

5. Report: `<risk-id> ROAM status → <status>`.
   The ROAM board in `/edpa:pi-planning` groups risks by this field — suggest a
   re-render if the PI is actively being planned.

## Notes

- Only Risk items accept `roam_status`; the tool rejects other item types.
- Use `/edpa:add Risk "…"` to create a Risk item before classifying it.
- The PI planning ROAM board has four columns (one per status). Unclassified risks
  appear under "Unclassified" on the board.
