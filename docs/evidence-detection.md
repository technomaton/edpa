# Evidence Detection (v1.11)

EDPA derives per-person hours from delivery evidence captured in
GitHub. v1.11 consolidates evidence detection and CW computation into a
single pipeline in `detect_contributors.py`; the engine consumes the
resulting per-item-normalized `cw` values directly.

## GitHub Signals → contribution_score → cw

| Signal type | Default weight | Source on GitHub | Reference format |
|-------------|---------------|------------------|------------------|
| `commit_author` | **4.00** | Commit authors (PR author + co-authors) | `pr#<num>/commit/<sha>` |
| `pr_reviewer` | **2.17** | PR reviews submitted | `pr#<num>/review/<id>` |
| `issue_comment` | **1.46** | Issue / PR comments (excluding bots) | `issue#<num>/comment/<id>` |
| `manual:pr_body` | **explicit** | `/contribute @X weight:Y` in PR description | `pr#<num>/body` |
| `manual:commit_message` | **explicit** | `/contribute` in commit message | `commit/<sha>/message` |
| `manual:issue_body` | **explicit** | `/contribute` in issue description | `issue#<num>/body` |
| `manual:issue_comment` | **explicit** | `/contribute` in issue comment | `issue#<num>/comment/<id>` |
| `manual:pr_comment` | **explicit** | `/contribute` in PR-level comment | `pr#<num>/comment/<id>` |

The 3 auto-detected signal weights live in
`.edpa/config/cw_heuristics.yaml` under the `signals:` block. They are
calibrated by `/edpa:calibrate` against ground-truth CW records;
manual `/contribute` weights are user-supplied per directive.

## Aggregation algorithm

```
for each item:
  for each person:
    contribution_score[P, item] = Σ signal_weight × signal_fired(P, item)
    # Multiple firings of the same signal type stack additively
    # (e.g., 3 separate /contribute lines in the same PR body).

  if Σ contribution_score[*, item] > 0:
    for each person:
      cw[P, item] = contribution_score[P, item]
                  / Σ contribution_score[*, item]
    # Σ_persons cw[*, item] = 1.0  per-item invariant
  else:
    # Edge case: 0 signals detected — leave existing contributors[]
    # untouched and emit a warning. Engine skips the item.
```

## All commits are delivery evidence

EDPA measures **contribution to project delivery**, not "lines of
code".

| Activity | Evidence? | How it shows up |
|----------|-----------|-----------------|
| Dev commits code (`src/`) | **YES** | `commit_author` |
| PM updates backlog (`.edpa/`) | **YES** | `commit_author` on planning commits |
| Arch edits config (`.edpa/config/`) | **YES** | `commit_author` + `pr_reviewer` on related items |
| BO comments on Epic | **YES** | `issue_comment` + maybe `manual:issue_comment` |
| QA writes tests (`tests/`) | **YES** | `commit_author` |

Analytical and preparatory work (planning, specification,
prioritization) is the **majority of project work**. A PM who spends 4
hours defining acceptance criteria and updating the backlog
contributes as much as a Dev who spends 4 hours coding — both flow
through the same signal aggregation; signal weights determine each
activity's translation to cw share.

## Branch naming → item detection

PR branch `feature/S-200-omop-parser` → extract `S-200` → match to
issue. Regex: `[SFEITD]-\d+`. Also extracted from PR title, PR body,
and commit messages.

## Role labels are derived, not stored

EDPA's data store carries `cw` and `signals[]` only — there is no
per-person `as: owner/key/reviewer/consulted` field. Role labels are
**derived at display time** from the highest-priority signal type:

| Signal type | Derived role |
|-------------|--------------|
| `commit_author` | owner |
| `manual:*` | key (default for /contribute attributions) |
| `pr_reviewer` | reviewer |
| `issue_comment` | consulted |

A person who fires multiple signal types gets the **highest-priority
role** for display (timesheets, reports). The math doesn't see roles —
only `cw` × `JS` proportional allocation.

## Manual `/contribute` directive

Add `/contribute @<person> weight:<float>` anywhere in:

- PR description (body)
- PR-level comment
- Commit message body
- Issue description (body)
- Issue comment

Each directive contributes **additively** to the person's
`contribution_score`. Multiple directives for the same person on the
same surface stack (e.g., three lines in one commit message → three
signals).

```
/contribute @alice weight:1.5
/contribute @bob weight:0.5
```

The `weight:` value is the signal's contribution to
`contribution_score`, not the final cw. After per-item normalization,
the resulting cw share depends on what other signals fired for other
people on the same item. See [`docs/contribute-directive.md`](contribute-directive.md)
for usage patterns and best practices.

## Auditor verification

Every signal in a contributor's `signals[]` array carries a `ref`
that resolves to an exact location on GitHub:

```yaml
signals:
  - type: commit_author
    ref: pr#146/commit/fa9f4401a2b
    weight: 1.0
    detected_at: 2026-05-08T15:23:11Z
```

To verify: `gh api repos/<org>/<repo>/commits/fa9f4401a2b` returns the
commit with author info. See
[`docs/audit-references.md`](audit-references.md) for the canonical
reference format per signal type and verification commands.
