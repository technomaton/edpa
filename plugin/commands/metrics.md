# /edpa:metrics — PI Predictability & Confidence Trending

Show a table of per-PI metrics (planned vs delivered SP, predictability %, average team
confidence vote, objective completion ratio, average velocity) for the last N Program
Increments. Use it in Inspect&Adapt to spot trends before committing to the next PI scope.

## Usage

```
/edpa:metrics [--window N] [--pi PI-YYYY-M]
```

| Argument | Default | Description |
|---|---|---|
| `--window N` | 5 | Number of most-recent PIs to include |
| `--pi PI-YYYY-M` | all | Limit to a single PI |

## Steps

1. **Parse arguments** — extract `--window` (default 5) and optional `--pi` filter.

2. **Collect metrics** — call the `edpa_pi_metrics` MCP tool:
   ```
   edpa_pi_metrics(window=<N>, pi=<PI-ID or omit>)
   ```
   The tool reads:
   - `.edpa/iterations/PI-YYYY-M.yaml` — PI status, dates
   - `.edpa/iterations/PI-YYYY-M.N.yaml` — planned/delivered SP per iteration
   - `.edpa/pi-objectives/PI-YYYY-M.yaml` — team confidence votes + objective status
   - Backlog items (via `_sp_rollup`) when SP is not in iteration YAMLs

3. **Render output** — display the Markdown table (already rendered by the tool):

   | PI | Status | Planned SP | Delivered SP | Predictability | Avg Velocity | Confidence | Objectives |
   |---|---|---:|---:|---:|---:|---:|---|
   | PI-2026-1 | closed | 84 | 84 | 100.0% | 28.0 | 3.5/5 | 3/3 |

   If any PI has team confidence votes, also show the per-team breakdown.

4. **Offer follow-up actions**:
   - "Run `/edpa:forecast PI-YYYY-M` to see Monte-Carlo completion probability for the current PI."
   - "Run `/edpa:objectives PI-YYYY-M` to update confidence votes."
   - "Files written: `.edpa/reports/pi-metrics.json` and `.edpa/reports/pi-metrics.md`."

## Reading the table

| Column | Meaning |
|---|---|
| **Predictability** | `delivered_sp / planned_sp × 100`. 100% = fully met commitments. |
| **Avg Velocity** | Average delivered SP per closed iteration in this PI. |
| **Confidence** | Average of all team confidence votes (1 = very low, 5 = very high). |
| **Objectives** | `done / committed` PI objectives across all teams. |

A predictability < 80% or confidence ≤ 2 in consecutive PIs is an Inspect&Adapt signal.
