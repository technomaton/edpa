# Audit Trail & Freeze Rules (v1.11)

## Six pillars of audit compliance

1. **GitHub delivery evidence** — commits, PRs, reviews, comments (living data)
2. **Capacity registry** — `.edpa/config/people.yaml` (versioned in git)
3. **Per-signal audit refs** — every contribution has a resolvable
   `ref` to a specific GitHub artifact (issue#N, pr#N/commit/SHA,
   etc.). See [`docs/audit-references.md`](audit-references.md).
4. **Frozen snapshot** — `.edpa/snapshots/iteration-{ID}.json` (immutable)
5. **Reproducible calculation** — `cw[P, item] = score[P, item] / Σ_persons score`
   (per-item normalization), `DerivedHours[P, item] = (JS×cw / Σ_items JS×cw) × Capacity`
6. **Signed output** — BankID electronic signature (Czech law 21/2020 Sb.)

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

## Snapshot format (v1.11)

```json
{
  "snapshot_version": "1.11",
  "iteration": "PI-2026-1.3",
  "generated_at": "2026-05-12T18:00:00Z",
  "frozen": true,
  "methodology": "EDPA 1.11.0",
  "mode": "gates",
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
          "cw": 0.419,
          "contribution_score": 5.50,
          "signals": [
            {
              "type": "commit_author",
              "ref": "pr#146/commit/fa9f440",
              "weight": 4.00,
              "detected_at": "2026-05-08T15:23:11Z"
            },
            {
              "type": "manual:pr_body",
              "ref": "pr#146/body",
              "excerpt": "/contribute @turyna weight:1.5",
              "weight": 1.50,
              "detected_at": "2026-05-08T15:23:11Z"
            }
          ]
        },
        {
          "person": "mtury",
          "cw": 0.470,
          "contribution_score": 6.17,
          "signals": [
            {"type": "commit_author", "ref": "pr#146/commit/6b5b69c", "weight": 4.00,
             "detected_at": "2026-05-08T15:23:11Z"},
            {"type": "pr_reviewer", "ref": "pr#146/review/2845102347", "weight": 2.17,
             "detected_at": "2026-05-08T15:23:11Z"}
          ]
        },
        {
          "person": "jurby",
          "cw": 0.111,
          "contribution_score": 1.46,
          "signals": [
            {"type": "issue_comment", "ref": "issue#137/comment/c984712", "weight": 1.46,
             "detected_at": "2026-05-08T15:23:11Z"}
          ]
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
    "per_item_cw_sums_to_one": true,
    "ratio_sum_equals_one": true,
    "no_negative_hours": true
  },
  "signature_status": "pending"
}
```

Note the v1.11 structure:

- **`contributors[].cw`** is the per-item share (Σ across persons =
  1.0 per item). Different from v1.10 where cw was an absolute
  [0,1] role-based weight.
- **`contributors[].contribution_score`** is the raw signal-weight
  sum, the input to per-item normalization.
- **`contributors[].signals[]`** is the per-signal audit trail with
  resolvable `ref` for each evidence source. Two collectors feed
  this list:
  - **`detect_contributors.py`** (v1.11) — PR/issue API surfaces:
    `commit_author`, `pr_reviewer`, `issue_comment`, `manual:*`.
  - **`yaml_edit_signals.py`** (v1.17) — git diff over
    `.edpa/backlog/<typ>/<id>.yaml` per iteration window:
    `yaml_edit:create`, `yaml_edit:block_add`, `yaml_edit:list_grow`,
    `yaml_edit:scalar_change`, `yaml_edit:lines_volume`,
    `yaml_edit:contributors_rebalance`, `yaml_edit:revert`. Each
    signal carries `ref = commit/<sha>/<file>` so an auditor opens
    the commit diff to verify what changed.
  See [`docs/audit-references.md`](audit-references.md) for
  verification commands per signal type.
- **No `as:` field** — role labels are derived at display time from
  the highest-priority signal type.

## BankID signing

Phase 1 (immediate): GitHub Issue comment with confirmation + BankID screenshot
Phase 2 (later): Integration via Signi.com or DigiSign with BankID API

Signed documents stored in `.edpa/reports/signed/`.

## Reporting pipeline

```
Iteration Close → per person:
  .edpa/reports/iteration-{ID}/vykaz-{person}.md
  .edpa/reports/iteration-{ID}/vykaz-{person}.json
  .edpa/reports/iteration-{ID}/edpa-results.xlsx    ← Team Summary + Item Costs tabs

PI Close → aggregation:
  .edpa/reports/pi-{PI}/pi-summary-{PI}.md

Annual:
  .edpa/reports/{year}/annual.xlsx
```
