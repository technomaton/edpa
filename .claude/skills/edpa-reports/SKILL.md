---
name: edpa-reports
description: >
  Generate EDPA timesheets, reports, and exports. Produces per-person MD/JSON reports,
  per-item cost allocation, PI summaries, Excel exports, and frozen snapshots. Use when
  user asks for "reports", "výkazy", "export", "snapshot", or "per-item analysis".
  Requires edpa-engine results (edpa_results.json) as input.
license: MIT
compatibility: Python 3.10+ (openpyxl for XLSX), config/capacity.yaml
allowed-tools: Read Write Bash(python3 *) Bash(cp *) Bash(mkdir *)
metadata:
  author: Jaroslav Urbánek
  version: 1.0.0
  domain: governance
  phase: reports
  standard: AgentSkills v1.0
---

# EDPA Reports — Timesheet & Export Generation

## What this does

Generates all EDPA v2.2 output artifacts from engine results: per-person timesheets (MD+JSON),
per-item cost allocation, frozen snapshots, PI summaries, and Excel exports.

## Arguments

`$ARGUMENTS` = iteration ID, or "pi" for PI-level aggregation, or "per-item {item_id}" for single item analysis.

## Prerequisites

- `reports/iteration-{ID}/edpa_results.json` exists (run edpa-engine first)
- `config/capacity.yaml` exists

## Output artifacts

### Per-person reports (Iteration Close)

For each person, generate:

**Markdown report** (`vykaz-{person}.md`):
```markdown
# VÝKAZ PRÁCE — {name}
Projekt: {project_name}
Registrace: {registration}
Období: {iteration} ({dates})
Kapacita: {capacity}h ({fte} FTE)
Metodika: EDPA v2.2 ({mode})

| Item | Typ | JS | CW | Score | Podíl | Hodiny |
|------|-----|----|----|-------|-------|--------|
| {rows} |
| **CELKEM** | | | | **{sum}** | **100%** | **{total}** |

Snapshot: {iteration}.json
Podpis (BankID): ☐ Čeká na podpis
```

**JSON report** (`vykaz-{person}.json`):
Include all fields from edpa_results.json for this person plus project metadata and signature status.

### Per-item cost allocation

For each item with ≥ 2 contributors:
```
ItemShare[P] = DerivedHours[P, item] / Σ DerivedHours[*, item]
```

Output hierarchically: Epic → Feature → Story with contributor breakdown per level.
Write to `reports/iteration-{ID}/item-costs.xlsx`.

### Frozen snapshot

Write to `/snapshots/iteration-{ID}.json`:
```json
{
  "snapshot_version": "2.2",
  "iteration": "{id}",
  "generated_at": "ISO-8601",
  "frozen": true,
  "methodology": "EDPA v2.2",
  "capacity_registry": { "...from config..." },
  "edpa_results": { "...from engine..." },
  "signature_status": "pending"
}
```

**FREEZE RULE: Once written, snapshot is immutable. Corrections create new revisions with incremented version suffix.**

### PI aggregation

When $ARGUMENTS = "pi":
1. Load all iteration results in current PI
2. Aggregate per person: Σ hours across iterations
3. Compare to expected (capacity × iterations_count)
4. Write `reports/pi-{ID}/pi-summary.xlsx`

### Excel export

Use openpyxl to create formatted XLSX:
```python
import openpyxl
# Create workbook with sheets: Summary, Per-Person, Per-Item, Validation
```

## Error handling

- Missing edpa_results.json → "Run edpa-engine for {iteration} first."
- Invariant failures in results → include warning banner in reports
- Snapshot already exists → create revision (iteration-{ID}_rev2.json)
