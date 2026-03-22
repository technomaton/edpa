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

## Governance vs Delivery Evidence

Commits on governance paths are **excluded** from evidence detection:

| Path | Content | Evidence? |
|------|---------|-----------|
| `src/`, `tests/`, `docs/` | Source code, tests, documentation | **YES** — delivery evidence |
| `.edpa/` | Backlog YAML, sync state, changelog | **NO** — governance metadata |
| `config/` | Capacity, heuristics, project config | **NO** — configuration |
| `snapshots/`, `reports/` | Frozen snapshots, generated reports | **NO** — auto-generated output |
| `signed/` | BankID signatures | **NO** — audit artifacts |

**Why:** When PM changes an Epic's status in `backlog.yaml` and commits,
that's administration — not work on the deliverable. Without this filter,
PM would get commit-based CW (0.25) for a governance change, inflating
their hours on that Epic.

The `governance_only_authors` field on each item tracks people who
committed **only** to governance paths for that item. They are excluded
from `commit_author` evidence but can still have evidence via assignee,
PR review, /contribute, or comments.

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
