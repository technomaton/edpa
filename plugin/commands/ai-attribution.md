# EDPA AI Attribution

**Usage:** `/edpa:ai-attribution <iteration> [--json]`

Compute the human vs AI-agent delivery ratio for an iteration.

Scans every Done backlog item in the iteration for `agent_contribution`
signals — emitted by the `local_evidence.py` post-commit hook whenever a
commit carries a `Co-Authored-By: Claude … <…@anthropic.com>` trailer.

## What it produces

- **ai_delivery_ratio** — fraction of items that had AI assistance
- **per-item** — AI signal count, human signal count, which agents
- **per-person** — each contributor's AI-assisted-item ratio
- Written to `.edpa/reports/iteration-<id>/ai_attribution.json` and
  `ai-attribution-<id>.md`

## Steps

1. Parse arguments:
   - `<iteration>` — required, e.g. `PI-2026-1.3`
   - `--json` — print raw JSON to stdout

2. Run the script:

```bash
python3 .edpa/engine/scripts/ai_attribution.py \
  --iteration <iteration> \
  [--json]
```

3. Show the summary table or, if `--json`, print the JSON result.

## Example

```
/edpa:ai-attribution PI-2026-1.3

AI Attribution — PI-2026-1.3
  Items total      : 12
  AI-assisted      : 8
  AI delivery ratio: 66.7%
  Agents           : claude-sonnet-4-6

By person:
  jurby                 8/12 items (67% AI)
```
