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
- Iteration Capacity (hours) → `.edpa/config/capacity.yaml`
- Derived Hours → `.edpa/reports/` snapshots
- FTE → `.edpa/config/capacity.yaml`
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

## Views to create

1. **Backlog** — Table view, grouped by Issue Type, sorted by WSJF
2. **Current Iteration** — Board view (To Do / In Progress / In Review / Done), filtered by Iteration
3. **Roadmap** — Roadmap view, grouped by Planning Interval
4. **My Work** — Table view, filtered by Primary Owner = @me

## Granularity guardrails

- Story: max Job Size 8 (classic 2/10) or 5 (AI-native 1/5)
- Feature: max Job Size 13
- Epic: max Job Size 20
- Over limit → break down into smaller items

## Definition of Ready

No item enters delivery without:
- Issue Type set
- Parent issue linked
- Job Size estimated
- BV + TC + RR filled
- Primary Owner assigned
- Iteration or Planning Interval assigned
