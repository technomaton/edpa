# Audit Trail & Freeze Rules

## Five pillars of audit compliance

1. **GitHub delivery evidence** — commits, PRs, reviews, comments (living data)
2. **Capacity registry** — `.edpa/config/people.yaml` (versioned in git)
3. **Frozen snapshot** — `.edpa/snapshots/iteration-{ID}.json` (immutable)
4. **Reproducible calculation** — Score = JS × CW (× RS), DerivedHours = (Score/ΣScores) × Capacity
5. **Signed output** — BankID electronic signature (Czech law 21/2020 Sb.)

## Freeze rule

After Iteration Close generates a snapshot:
- Snapshot is **frozen** (immutable)
- Evidence is **never overwritten in-place**
- Corrections create **new revisions** with incremented suffix

Example:
```
.edpa/snapshots/PI-2026-1.3.json          # original
.edpa/snapshots/PI-2026-1.3_rev2.json     # correction
.edpa/snapshots/PI-2026-1.3_rev3.json     # second correction
```

Each revision includes: reason for correction, diff from previous, timestamp, author.

## Snapshot format

```json
{
  "snapshot_version": "2.2",
  "iteration": "PI-2026-1.3",
  "generated_at": "2026-05-12T18:00:00Z",
  "frozen": true,
  "methodology": "EDPA 1.0.0-beta",
  "mode": "simple",
  "capacity_registry": { "...": "copy from .edpa/config/people.yaml at computation time" },
  "items": [
    {
      "id": "S-200",
      "level": "Story",
      "job_size": 8,
      "status": "Done",
      "contributors": [
        {
          "person": "turyna",
          "cw": 1.0,
          "relevance_signal": 1.0,
          "score": 8.0,
          "evidence": ["assignee", "pr_author", "commits"]
        }
      ]
    }
  ],
  "derived_reports": [
    {"person": "urbanek", "capacity": 40, "total_derived": 40.0, "items_count": 8}
  ],
  "invariants": {
    "all_passed": true,
    "sum_equals_capacity": true,
    "ratio_sum_equals_one": true,
    "no_negative_hours": true
  },
  "signature_status": "pending"
}
```

## BankID signing

Phase 1 (immediate): GitHub Issue comment with confirmation + BankID screenshot
Phase 2 (later): Integration via Signi.com or DigiSign with BankID API

Signed documents stored in `.edpa/reports/signed/`.

## Reporting pipeline

```
Iteration Close → per person:
  .edpa/reports/iteration-{ID}/vykaz-{person}.md
  .edpa/reports/iteration-{ID}/vykaz-{person}.json
  .edpa/reports/iteration-{ID}/summary.xlsx
  .edpa/reports/iteration-{ID}/item-costs.xlsx

PI Close → aggregation:
  .edpa/reports/pi-{PI}/pi-summary.xlsx

Annual:
  .edpa/reports/{year}/annual.xlsx
```
