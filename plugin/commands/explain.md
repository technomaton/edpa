---
description: Explain one person's allocation — signal → CW → JS×CW → ratio → hours, with full audit trail
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Explain

Explain how a person's hours were derived for an iteration.
`$ARGUMENTS` is `<person-id> <iteration-id> [--item <item-id>]`.

Outputs: signal → contribution_score → CW → JS×CW → ratio → hours,
with an invariant check (Σ derived == capacity).

Examples:
- `urbanek PI-2026-1.1` — full allocation narrative for urbanek
- `urbanek PI-2026-1.1 --item S-206` — zoom in on one item
- `turyna PI-2026-1.2`

## Prerequisites

The engine must have been run for the iteration — `/edpa:explain` reads
`.edpa/reports/iteration-<id>/edpa_results.json` (does **not** re-run the engine).

## Steps

1. Parse `$ARGUMENTS`. Extract `<person-id>` and `<iteration-id>` (both required — ask if missing).
   Optionally extract `--item <item-id>`.

2. Run the explainer script:
   ```bash
   python3 .edpa/engine/scripts/explain.py \
     --person <person-id> \
     --iteration <iteration-id> \
     [--item <item-id>] \
     --edpa-root .edpa
   ```
   Equivalently via the engine shortcut:
   ```bash
   python3 .edpa/engine/scripts/engine.py \
     --explain <person-id> --iteration <iteration-id> \
     [--explain-item <item-id>] \
     --edpa-root .edpa
   ```

3. Display the markdown output as-is. It contains:
   - A summary table: Item | JS | CW | Score | Ratio | Hours
   - Per-item detail: evidence signals (type, ref, weight) → contribution_score →
     CW formula → score (JS × CW) → ratio formula → hours
   - Invariant footer: Σ derived == capacity ✓/✗

4. If the invariant fails (✗), surface a warning and suggest re-running
   `/edpa:engine <iteration-id>` to refresh results.

## Notes

- Items with manually-set `contributors[]` (no `signals[]`) show "manual CW" — this is
  normal for backlog items where GitHub signals haven't been detected yet.
- `contribution_score` = sum of signal weights. `cw` = that person's share across all
  contributors on the item. `score` = JS × cw. `ratio` = score / Σ scores.
  `hours` = ratio × capacity.
- The `--item` filter is useful for answering "why did urbanek get 24h for S-206?"
  without the full iteration noise.
- Output can be saved: `explain.py ... --output explain-urbanek-PI-2026-1.1.md`
