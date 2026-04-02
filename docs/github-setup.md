# GitHub Projects Setup Guide

## Native Issue Types (org-level)

Issue Types are a native GitHub feature, managed at the organization level (not per-project custom fields). Create them via `.claude/edpa/scripts/issue_types.py setup`:

| Issue Type | Description |
|------------|-------------|
| Initiative | Business case, investment proposal |
| Epic | Strategic goal, 6-9 months |
| Feature | Must fit within a Planning Interval |
| Story | Delivered within an iteration |
| Defect | Defect in existing functionality |
| Task | Technical work |

> **Note:** Enabler is a **label** classification (Business vs Enabler), not an Issue Type. An Epic can be labeled "Enabler" to mark it as an Enabler Epic (SAFe).

## Required custom fields

Create these on your GitHub Project:

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| Job Size | Number | Fibonacci: 1,2,3,5,8,13,20 | Relative size estimate |
| Business Value | Number | Fibonacci: 1-20 | WSJF input |
| Time Criticality | Number | Fibonacci: 1-20 | WSJF input |
| Risk Reduction | Number | Fibonacci: 1-20 | WSJF input |
| WSJF Score | Number | Auto-calculated | Priority score |
| Planning Interval | Iteration | PI-2026-1, PI-2026-2... | PI assignment |
| Iteration | Iteration | PI-2026-1.1, PI-2026-1.2... | Iteration assignment |
| Team | Single select | Your team names | Team assignment |
| Primary Owner | Assignee | | Accountable person |
| Confidence | Single select | Low, Medium, High | Planning confidence |

## Fields NOT to put in GitHub Projects

These belong in the Evidence & Reporting layer, not operational metadata:
- Iteration Capacity (hours) → `.edpa/config/people.yaml`
- Derived Hours → `.edpa/reports/` snapshots
- FTE → `.edpa/config/people.yaml`
- Signature status → `.edpa/snapshots/` + `.edpa/reports/signed/`

## Hierarchy via sub-issues and native Issue Types

GitHub sub-issues (GA April 2025) support 8 levels. Each level uses a **native GitHub Issue Type** (org-level, not labels):

```
Initiative (top-level issue, native Issue Type = Initiative)
  └── Epic (sub-issue, native Issue Type = Epic)
       └── Feature (sub-issue, native Issue Type = Feature)
            └── Story (sub-issue, native Issue Type = Story)
                 └── Task (sub-issue or checklist, native Issue Type = Task)
```

Filter syntax: `type:Epic`, `type:Story`, etc.

## Item ID convention

Each work item has a unique ID with a type prefix and sequential number, starting from 1 per type:

| Type | Prefix | Example IDs |
|------|--------|-------------|
| Initiative | `I-` | I-1, I-2, I-3 |
| Epic | `E-` | E-1, E-2, E-3 |
| Feature | `F-` | F-1, F-2, F-3 |
| Story | `S-` | S-1, S-2, S-3 |
| Defect | `D-` | D-1, D-2, D-3 |
| Task | `T-` | T-1, T-2, T-3 |

- IDs are sequential per type (not globally unique across types)
- The prefix makes IDs globally unique: `S-1` and `F-1` are different items
- IDs are immutable — never renumber after creation
- YAML filename matches the ID: `.edpa/backlog/stories/S-1.yaml`
- Branch naming uses the ID: `feature/S-1-login-endpoint`
- Commit messages reference the ID: `feat(S-1): implement login`

## Status fields (4 typed)

GitHub Projects uses **4 separate Single Select fields** — one per work-item level — each with SAFe-aligned workflow steps:

| Field | Applies to | Options |
|-------|-----------|---------|
| **Initiative Status** | Initiative | Funnel, Reviewing, Analyzing, Ready, Implementing, Done |
| **Epic Status** | Epic | Funnel, Reviewing, Analyzing, Ready, Implementing, Done |
| **Feature Status** | Feature | Funnel, Analyzing, Backlog, Implementing, Validating, Deploying, Releasing, Done |
| **Story Status** | Story | Funnel, Analyzing, Backlog, Implementing, Validating, Deploying, Releasing, Done |

**Portfolio workflow** (Initiative + Epic): Funnel → Reviewing → Analyzing → Ready → Implementing → Done

**Delivery workflow** (Feature + Story): Funnel → Analyzing → Backlog → Implementing → Validating → Deploying → Releasing → Done

**Engine logic:** `status == "Done"` means finished. Everything else is in-work. No Blocked/Spillover labels.

`project_setup.py` creates these 4 status fields and their options automatically.

## Views to create

Each hierarchy level gets its own Board — no mixing Epics with Stories:

1. **All Items** — Table view, grouped by Status, sorted by WSJF (hierarchical with sub-issues)
2. **Stories Board** — Board view, filter `type:Story` (daily work)
3. **Features Board** — Board view, filter `type:Feature` (PI planning)
4. **Epics Board** — Board view, filter `type:Epic` (strategic)
5. **WSJF Ranking** — Table view, grouped by Issue Type, sorted by WSJF
6. **Current Iteration** — Board view, filter `type:Story` + current iteration
7. **My Work** — Table view, filtered by `assignee:@me`
8. **Roadmap** — Roadmap view, grouped by Planning Interval

## Granularity guardrails

- Story: max Job Size 8 (classic 2/10) or 5 (AI-native 1/5)
- Feature: max Job Size 13
- Epic: max Job Size 20
- Over limit → break down into smaller items

## GitHub Projects Automations

### Enable (recommended)

| Automation | Why |
|-----------|-----|
| **Item added to project → Set Status to "Funnel"** | New issues get a default status automatically. EDPA sync picks this up on next pull. |
| **Auto-add issues from linked repository** | Issues created in the repo appear in the project automatically — no manual `Add item` needed. |

### Do NOT enable

| Automation | Why NOT |
|-----------|---------|
| **Pull request merged → Set Status to "Done"** | Premature — item may still need QA, documentation, or acceptance. Status should be set explicitly after verification. |
| **Item closed → Auto-archive** | **CRITICAL:** Archived items disappear from API queries. `sync.py` stops seeing them. EDPA engine loses data for hour derivation and audit trail. **Never enable this.** |
| **Item reopened → Set Status to "Implementing"** | Interferes with EDPA's sync — a reopened item might need a different status (e.g., Funnel for next iteration). |

### How to configure

1. Open project → **...** menu → **Workflows**
2. Enable only the two recommended automations
3. Leave all others disabled

> **Auto-archive warning:** If you accidentally archive items, they can be restored via the project's Archive tab, but `sync.py` will not see them until unarchived. Run `sync.py status` to detect missing items.

## Recommended Insights charts

GitHub Projects Insights provides real-time dashboards (complementary to EDPA engine's governance-grade calculations):

| Chart | Configuration | Purpose |
|-------|--------------|---------|
| **Burn-down** | X: Time, Y: Count of items, Group: Status | Iteration progress tracking |
| **Items by Status** | Bar chart, Group: Status | Current work distribution |
| **Items by Team** | Bar chart, Group: Team | Workload balance across teams |
| **Items by Issue Type** | Bar chart, Group: Issue Type | Hierarchy balance (too many Epics vs Stories?) |

Configure in project → **Insights** tab → **New chart**.

> **EDPA engine vs Insights:** Insights shows real-time visual dashboards. EDPA engine computes governance-grade derived hours, contribution weights, and cost allocation at iteration close. They are complementary, not competing.

## Definition of Ready

No item enters delivery without:
- Issue Type set
- Parent issue linked
- Job Size estimated
- BV + TC + RR filled
- Primary Owner assigned
- Iteration or Planning Interval assigned
