# GitHub Projects Setup Guide

## Required custom fields

Create these on your GitHub Project:

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| Issue Type | Single select | Initiative, Epic, Feature, Story, Task, Bug | Work item hierarchy |
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
- Iteration Capacity (hours) → `config/capacity.yaml`
- Derived Hours → `reports/` snapshots
- FTE → `config/capacity.yaml`
- Signature status → `/snapshots/` + `/signed/`

## Hierarchy via sub-issues

GitHub sub-issues (GA April 2025) support 8 levels:

```
Initiative (top-level issue, Issue Type = Initiative)
  └── Epic (sub-issue, Issue Type = Epic)
       └── Feature (sub-issue, Issue Type = Feature)
            └── Story (sub-issue, Issue Type = Story)
                 └── Task (sub-issue or checklist, Issue Type = Task)
```

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
