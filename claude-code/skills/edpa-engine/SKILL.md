---
name: edpa-engine
description: >
  Run EDPA evidence-driven calculation for an iteration. Gathers GitHub delivery evidence
  (commits, PRs, reviews, comments), computes CW from heuristics, calculates Score and
  DerivedHours, validates invariants. Use when closing an iteration, computing derived hours,
  or running "EDPA výpočet". Produces per-person allocation data for the reports skill.
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+, config/capacity.yaml, config/cw_heuristics.yaml
allowed-tools: Read Bash(gh *) Bash(git *) Bash(python3 *) Grep
metadata:
  author: Jaroslav Urbánek
  version: 1.0.0
  domain: governance
  phase: engine
  standard: AgentSkills v1.0
---

# EDPA Engine — Evidence-Driven Calculation

## What this does

Computes derived hours for all team members for a given iteration using EDPA v2.2 formula.

## Arguments

`$ARGUMENTS` = iteration ID (e.g., "PI-2026-1.3") or "latest" for most recent closed iteration.

## Prerequisites

- `config/capacity.yaml` exists (run edpa-setup first)
- `config/cw_heuristics.yaml` exists
- GitHub issues have Job Size field populated
- Iteration has closed stories (status: Done)

## Calculation steps

### 1. Load configuration

```python
import yaml
with open('config/capacity.yaml') as f:
    config = yaml.safe_load(f)
with open('config/cw_heuristics.yaml') as f:
    heuristics = yaml.safe_load(f)
```

### 2. Gather delivery evidence

For each person P, identify relevant items:
- **Stories:** Done in iteration $ARGUMENTS, where P has evidence
- **Features:** Active in current PI, where P has evidence
- **Epics:** Active, where P has evidence

**Evidence sources (hybrid — MCP preferred, gh CLI fallback):**

```bash
# Get closed issues in iteration
gh issue list --label "iteration:$ARGUMENTS" --state closed --json number,title,assignees,labels,body

# Get merged PRs referencing iteration items
gh pr list --state merged --json number,title,author,reviews,commits,body

# Get commits with item references
git log --since="iteration_start" --until="iteration_end" --format="%H %an %s"
```

### 3. Score evidence per person per item

For each (person, item) pair:
```
evidence_score = Σ signal_weights for detected signals
```

Apply threshold: `evidence_score >= heuristics.evidence_threshold` → relevant.

Derive CW from highest signal:
```
assignee → owner (1.0)
contribute_command or pr_author → key (0.6)
commit_author or pr_reviewer → reviewer (0.25)
issue_comment → consulted (0.15)
```

Allow manual override: check issue body for `/contribute @person weight:X`.

### 4. Calculate EDPA scores

**Simple mode (default):**
```
Score[P, item] = JobSize[item] × CW[P, item]
```

**Full mode (if --full flag or user requests audit variant):**
```
Score[P, item] = JobSize[item] × CW[P, item] × RS[P, item]
RS = min(evidence_score / max_evidence_score_on_item, 1.0)
```

### 5. Derive hours

```
SumScores[P] = Σ Score[P, *]
DerivedHours[P, item] = (Score[P, item] / SumScores[P]) × Capacity[P]
```

### 6. Validate invariants

Run ALL checks — halt on failure:

| Check | Formula | Action on fail |
|-------|---------|----------------|
| Σ = capacity | Σ DerivedHours[P, *] = Capacity[P] ± 0.01 | HALT, report |
| Σ ratio = 1 | Σ (Score/ΣScores) = 1.0 ± 0.001 | HALT, report |
| No negative | DerivedHours ≥ 0 for all | HALT, report |
| Eligibility | In Progress items excluded | WARN if included |
| JS exists | All items have Job Size > 0 | WARN, skip item |

### 7. Output

Write results to `reports/iteration-{ID}/edpa_results.json`:
```json
{
  "iteration": "$ARGUMENTS",
  "mode": "simple|full",
  "computed_at": "ISO-8601",
  "people": [
    {
      "id": "person_id",
      "capacity": 40,
      "total_derived": 40.0,
      "items": [
        {"id": "S-200", "level": "Story", "js": 8, "cw": 1.0, "rs": 1.0, "score": 8.0, "ratio": 0.28, "hours": 11.2}
      ],
      "invariant_ok": true
    }
  ],
  "team_total": 380.0,
  "all_invariants_passed": true
}
```

Print summary table to stdout: person, capacity, derived total, items count, ok/fail.

## Error handling

- No items in iteration → "No closed items found for {iteration}. Check iteration label."
- Missing Job Size → warn per item, exclude from calculation
- Person with 0 relevant items → warn, derive 0h (process issue, not math issue)
- GitHub API unavailable → use `git log` as fallback evidence source
