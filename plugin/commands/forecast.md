---
description: Monte-Carlo PI completion forecast — p20/p50/p80 delivery bands and scope recommendation
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Forecast

Run a Monte-Carlo PI completion forecast. `$ARGUMENTS` is `<pi-id> [options]`.

Fits a velocity distribution from the last N closed iterations and simulates
remaining-iteration delivery 1000×, returning p20/p50/p80 delivery bands,
completion probability, and a scope recommendation.

Examples:
- `PI-2026-2` — forecast PI-2026-2 using last 3 closed iterations
- `PI-2026-2 --window 5` — use a wider velocity history window
- `PI-2026-2 --simulations 2000` — higher precision

**Options:**
- `--window N` — number of closed iterations to sample for velocity baseline (default: 3, minimum: 2)
- `--simulations N` — Monte-Carlo runs (default: 1000)

## Steps

1. Parse `$ARGUMENTS`. Extract PI ID (required — ask if missing).

2. Run the forecast script:
   ```bash
   python3 .edpa/engine/scripts/forecast.py \
     --pi <PI-ID> [--window N] [--simulations N] \
     --edpa-root .edpa
   ```

3. Display the result in a readable format:
   ```
   PI Completion Forecast: PI-2026-2
   ─────────────────────────────────────────────
   Velocity baseline (last 3 iterations): avg=28 SP, σ=4.2 SP
   Remaining: 3 iterations, 72 SP not yet Done

   Delivery bands (1000 simulations):
     p80 (likely):       90 SP  ✓ +18
     p50 (median):       84 SP  ✓ +12
     p20 (conservative): 70 SP  ✗ -2

   Completion probability: 71%
   Recommendation: At risk. Suggest reducing scope by ~X SP.
   ```

4. If the forecast indicates risk (completion probability < 75%), proactively suggest:
   - Which backlog items could be descoped (lowest WSJF, Backlog status)
   - `/edpa:change-state <item> Backlog` to defer them

## Notes

- **Requires at least 2 closed iterations** to compute velocity stats. If fewer exist,
  the script exits with an error message.
- The forecast reads from `.edpa/iterations/` (velocity) and `.edpa/backlog/` (remaining SP).
  It does NOT write to the backlog — it is read-only.
- Output files are saved to `.edpa/reports/forecast/forecast-<pi>.json` and `.md`
  for audit trail and re-use in `/edpa:pi-planning`.
- For programmatic access, use the `edpa_forecast_pi` MCP tool directly.
