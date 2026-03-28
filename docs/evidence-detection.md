# Evidence Detection Rules

## GitHub Signals → Evidence Score → CW

| Signal | Evidence Score | Typical CW | Detection method |
|--------|---------------|------------|-----------------|
| Assignee on issue | +4 | 1.0 (owner) | GitHub API: issue.assignees |
| `/contribute @person weight:X` | +3 | explicit | Issue body/comment regex |
| PR author referencing item | +2 | 0.6 (key) | PR title/body contains S-XXX |
| Commit author with item ref | +1 | 0.25 (reviewer) | Commit message contains S-XXX |
| PR reviewer | +1 | 0.25 (reviewer) | PR reviews API |
| Issue/PR comment | +0.5 | 0.15 (consulted) | Comments API (exclude bots) |

## Detection algorithm

```
for each person P:
  for each item in iteration:
    evidence_score = 0
    signals = []

    if P in item.assignees:
      evidence_score += 4; signals.append("assignee")
    if P has /contribute on item:
      evidence_score += 3; signals.append("contribute_command")
    if P authored PR referencing item:
      evidence_score += 2; signals.append("pr_author")
    if P committed with item ref in message:
      evidence_score += 1; signals.append("commit_author")
    if P reviewed PR referencing item:
      evidence_score += 1; signals.append("pr_reviewer")
    if P commented on item (non-trivial):
      evidence_score += 0.5; signals.append("issue_comment")

    if evidence_score >= threshold (default 1.0):
      CW = role_weights[highest_signal(signals)]
      add (P, item, CW, evidence_score) to relevant_items
```

## All commits are delivery evidence

EDPA measures **contribution to project delivery**, not "lines of code".

| Activity | Evidence? | Why |
|----------|-----------|-----|
| Dev commits code (`src/`) | **YES** | Implementation work |
| PM updates backlog (`.edpa/`) | **YES** | Planning, prioritization, specification |
| Arch edits config (`.edpa/config/`) | **YES** | Architecture decisions, configuration |
| BO comments on Epic | **YES** | Strategic direction, business decisions |
| QA writes tests (`tests/`) | **YES** | Quality assurance |

Analytical and preparatory work (planning, specification, prioritization) is the
**majority of project work** — not development itself. A PM who spends 4 hours
defining acceptance criteria and updating the backlog contributes as much as a
Dev who spends 4 hours coding.

The CW matrix per role ensures correct proportions — not by filtering commits,
but by **weighting each role's contribution appropriately** (Monte Carlo calibrated).

## Branch naming → item detection

PR branch `feature/S-200-omop-parser` → extract `S-200` → match to issue.

Regex: `[SFEIATB]-\d+`

## Manual override

In issue body or comment:
```
/contribute @urbanek weight:0.6
/contribute @tuma weight:0.3
```

Overrides auto-detected CW for that person on that item.

## Relevance Signal (RS)

For full (audit) mode:
```
RS[P, item] = min(evidence_score[P, item] / max_evidence_score_on_item, 1.0)
```

For simple (operational) mode: RS = 1.0 (effectively ignored).
