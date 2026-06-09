---
name: insights
description: Mid-iteration anomaly detection — flags capacity overload, job-size creep, stalled stories, and critical-path blockers
allowed-tools: mcp__plugin_edpa_edpa__edpa_insights
---

# /edpa:insights

Detect mid-iteration anomalies for the given iteration.

```
/edpa:insights <iteration> [--overload N] [--js-max N] [--stale-days N]
```

Examples:
- `/edpa:insights PI-2026-1.3`
- `/edpa:insights PI-2026-1.3 --overload 1.05`
- `/edpa:insights PI-2026-1.3 --js-max 5 --stale-days 3`

## What is detected

| Signal | Default threshold | Severity |
|--------|------------------|----------|
| **capacity_overload** | derived_hours / capacity > 110% | 🔴 critical (>120%), 🟡 warning (>110%) |
| **job_size_creep** | JS > 8 | 🟡 warning |
| **stalled_story** | in_progress, no git commit > 5 days | 🟡 warning |
| **critical_path_blocker** | depends_on an unfinished item | 🔴 critical |

## Prerequisites

Run the engine for the iteration first so `edpa_results.json` exists:

```bash
python3 .edpa/engine/scripts/engine.py --iteration <iteration>
```

## Steps

1. Parse arguments: extract `iteration` (required), optional thresholds.
2. Call `edpa_insights` MCP tool with the parsed arguments.
3. Display the anomaly report (rendered markdown).
4. If `anomaly_count == 0`: confirm "No anomalies detected."
5. If anomalies found: summarise critical vs warning counts and list messages.

## Output files

Written to `.edpa/reports/iteration-<iteration>/`:
- `insights.json` — machine-readable anomaly list
- `insights-<iteration>.md` — human-readable markdown report
