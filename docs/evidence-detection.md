# Evidence Detection

EDPA derives per-person hours from delivery evidence in the project's
**local git history**. The primary collector is `local_evidence.py`, a
post-commit hook that materializes signals into each backlog item's
`evidence[]` block on every commit — no GitHub API and no CI required.
An optional CI workflow adds the two PR-thread signals that don't
exist in git. `detect_contributors.py` then aggregates `evidence[]`
into `contributors[]` with per-item-normalized `cw` shares; the engine
consumes those values directly.

```text
every commit ──▶ post-commit hook (local_evidence.py)
                   ├─ commit_author / agent_contribution / manual:commit_message
                   ├─ yaml_edit (structural diff over .edpa/backlog/)
                   └─ state_transition (weight 0, analytics)
                 ──▶ appended to the item's evidence[] (dedup by ref)
                 ──▶ follow-up commit "chore(evidence): …"

PR merged (opt.) ─▶ CI complement (sync_pr_contributions.py)
                   └─ pr_reviewer / issue_comment ──▶ evidence[]

close-iteration ─▶ /edpa:materialize (idempotent catch-up)
                 ─▶ detect_contributors.py --all-items
                     evidence[] ──▶ contributors[] (cw per item) ──▶ engine
```

## Signal taxonomy (local-first pipeline)

| Signal type | Default weight | Source | `ref` format |
|-------------|---------------:|--------|--------------|
| `commit_author` | **4.00** | Commit author, per item the commit *works on* | `commit/<short>` |
| `agent_contribution` | **1.00** | `Co-Authored-By: Claude … <…@anthropic.com>` trailer | `commit/<short>/agent/<agent>` |
| `manual:commit_message` | **explicit** | `/contribute @login weight:N` in the commit body | `commit/<short>/contrib/<login>` |
| `yaml_edit` | **structural** | Commit diff over `.edpa/backlog/<type>/<id>.md` | `commit/<short>/<id>.md` |
| `state_transition` | **0** (analytics) | `status:` change — who / when / from→to | `commit/<short>/<id>/<from>-><to>` |

`<short>` is the 7-char commit SHA. Two optional GH-side signals
complete the pool — `pr_reviewer` (**2.17**) and `issue_comment`
(**1.46**) — collected by the CI complement (see below), never by the
local hook.

Weights live in `.edpa/config/cw_heuristics.yaml` — the flat weights
under `signals:`, the structural family under `yaml_edit_weights:` —
and are tuned by `/edpa:autocalib`. The config file is the source of
truth; the numbers here are the shipped defaults. Manual `/contribute`
weights are operator-supplied verbatim and never re-weighted.

### `yaml_edit` — structural backlog-edit scoring

Every commit touching `.edpa/backlog/<type>/<id>.md` is evidence of
work on that item. Scoring is purely **structural** — count blocks,
bullets, scalars — never a semantic classification of content. One
`yaml_edit` signal is emitted per (commit, item); its weight is the
sum of the fired components, and the structural breakdown is persisted
on the signal as `delta` (blocks / list items / scalars / lines ±)
next to `raw_weight`, `discount`, and audit `tags`.

| Component (`yaml_edit_weights:`) | Default | Fires on |
|----------------------------------|--------:|----------|
| `yaml_edit:create` | 2.0 | New file with `+id` `+type` `+title` (item born) |
| `yaml_edit:block_add` | 1.0 | Per new top-level nested block |
| `yaml_edit:list_grow` | 0.5 | Per net `- ` bullet (cap 10 per commit) |
| `yaml_edit:scalar_change` | 0.25 | Per top-level scalar set or changed |
| `yaml_edit:lines_volume` | min(1.0, added/40) | Volume bonus for substantive edits |
| `yaml_edit:revert` | −0.5 | Per net-removed block (negative) |

Anti-gaming mitigations baked into the collector:

- **Bot authors** (`*[bot]@*`, `github-actions@*`, the EDPA sync bot) → 0
- **Tool-generated commits** (`EDPA sync …`, `chore(evidence):`,
  `chore(ci-materialization):`, `Auto-commit`) → 0
- **Whitespace-only, rename-only, status-only** diffs → 0
  (status changes are owned by `state_transition`)
- **Edits to derived blocks** (`evidence[]`, `contributors[]`) → not scored
- **Bulk migration / backfill** commits, or one commit touching more
  than `bulk_item_threshold` items (default 5) → ×0.1 discount

### `state_transition` — weight-0 analytics

Every `status:` flip in a backlog file becomes a `state_transition`
record: who changed it, when, `from→to`. Its weight is **always 0** —
it never moves `cw`. It exists for delivery-lead-time / time-in-state
analytics, and gate scoring derives from the transition record
engine-side (`gate_weights:` × Job Size), not from a signal weight.

### `agent_contribution` — AI co-author attribution

Commits carrying a `Co-Authored-By: Claude … <…@anthropic.com>`
trailer emit one `agent_contribution` signal per distinct agent,
credited to the synthetic `_claude` person with the agent name
normalized into the ref (`Claude Sonnet 4.6` →
`commit/<short>/agent/claude-sonnet-4-6`). It participates in per-item
cw normalization like any other weighted signal, and it feeds the
human-vs-AI delivery ratio (`/edpa:ai-attribution`). Derived hours
flow only to people in `.edpa/config/people.yaml`, so `_claude` never
receives hours.

## Which items a commit credits (D-38)

Credit follows **work, not mention**. A commit's candidate items are
all EDPA IDs (`[A-Z]{1,3}-\d+`) in its subject and body, plus the IDs
of any `.edpa/backlog/<type>/<id>.md` files it changed. Of those, an
item earns full `commit_author` / `agent_contribution` / `/contribute`
weight only if it is **worked on**:

- it appears in the commit's *leading scope* — the part of the subject
  before the first `:`, i.e. `fix(D-31): …` or the bare `S-1: …` — or
- its backlog `.md` file was changed by the commit.

IDs merely mentioned elsewhere in the message (a "see also",
"supersedes", "renumbered from X" reference) are recorded audit-only:
a `commit_author` record with `weight: 0`, tag `referenced`, and the
original weight kept in `raw_weight`. They never inflate anyone's
credit — otherwise naming N items would credit all N at full weight
(gameable, and a proven source of accidental cross-crediting).

The hook skips entirely: merge commits, its own `chore(evidence):`
commits (self-recursion guard), commits authored by the EDPA sync bot,
and everything when `EDPA_NO_LOCAL_EVIDENCE=1` is set (bulk imports,
rebases). The
companion commit-msg hook (`check_ticket_attached.py`) blocks
unattributed commits *before* this hook would silently emit nothing.

## Zero-weight audit records

Three idioms share one shape — `weight: 0`, original in `raw_weight`,
a `tags` entry naming the reason — so the audit trail stays complete
and the gate stays reversible. Aggregation skips zero-weight signals,
so they never touch `contribution_score` or `cw`:

| Tag / type | Meaning |
|------------|---------|
| `referenced` | Item was mentioned in the commit message but not worked on (D-38) |
| `out_of_iteration` | Weighted signal (`commit_author`, `yaml_edit`, `agent_contribution`, `manual:commit_message`) on an item that provably belongs to a *different* iteration than the commit's own (D-28/D-29); D-33 applies the same gate to CI-side `pr_reviewer` / `issue_comment` per each event's own `at:` timestamp |
| `state_transition` | Always weight 0 — analytics record by design |

## Who gets credited (person resolution)

The commit author's git identity is resolved against
`.edpa/config/people.yaml`: exact `email:` match, then exact `name:`
match, then the email local-part against `id:` / `github:`. An
unresolved author is skipped with a stderr note — the commit succeeds,
the signal is simply not emitted (add the person's email/github to
attribute future commits). `/contribute` tokens resolve github handle
or canonical person id; unknown tokens are credited as-is and warned
(the engine awards them 0h, so typos don't vanish silently).

## Aggregation algorithm

`detect_contributors.py` reads each item's `evidence[]` (legacy
`ci_signals[]` is read transparently) and rebuilds `contributors[]`:

```text
for each item:
  for each person:
    contribution_score[P, item] = Σ signal_weight × signal_fired(P, item)
    # zero-weight signals are skipped (audit/analytics-only)
    # multiple firings of the same signal type stack additively

  if Σ contribution_score[*, item] > 0:
    for each person:
      cw[P, item] = contribution_score[P, item]
                  / Σ contribution_score[*, item]
    # Σ_persons cw[*, item] = 1.0  per-item invariant
  else:
    # 0 signals detected — leave existing contributors[] untouched
    # and emit a warning. Engine skips the item.
```

`detect_contributors.py --all-items` refreshes `contributors[]` for
every item with evidence; `/edpa:close-iteration` runs it before the
engine so allocations always reflect the latest `evidence[]`.

## All commits are delivery evidence

EDPA measures **contribution to project delivery**, not "lines of
code".

| Activity | Evidence? | How it shows up |
|----------|-----------|-----------------|
| Dev commits code (`src/`) | **YES** | `commit_author` |
| PM updates backlog (`.edpa/backlog/`) | **YES** | `commit_author` + `yaml_edit` |
| Arch moves a Feature to Implementing | **YES** | `state_transition` (gate credit engine-side) |
| AI agent co-authors a commit | **YES** | `agent_contribution` |
| Consultant credited by the author | **YES** | `manual:commit_message` |
| Reviewer approves a PR (GH, optional) | **YES** | `pr_reviewer` via CI complement |

Analytical and preparatory work (planning, specification,
prioritization) is the **majority of project work**. A PM who spends 4
hours defining acceptance criteria and updating the backlog
contributes as much as a Dev who spends 4 hours coding — both flow
through the same signal aggregation; signal weights determine each
activity's translation to cw share.

## Collectors and when they run

**Post-commit hook (primary, live).** `local_evidence.py` is installed
by `project_setup.py --with-hooks` (chained from
`.git/hooks/post-commit`). It emits all five local signal types for
the commit it just saw and commits the evidence update as
`chore(evidence): …` — an auto-commit that is itself excluded from
scoring.

**`/edpa:materialize` (catch-up, idempotent).** The MCP tool
`edpa_materialize` / CLI `local_evidence.py --materialize
--iteration <id>` (or `--all-iterations`) re-scans git for the
iteration window and back-fills `state_transition` + `yaml_edit`
signals — commits the hook never saw (hook disabled, history predating
the hook, commits from another machine). Dedup is by signal `ref`, so
re-running is a no-op. It ignores `EDPA_NO_LOCAL_EVIDENCE` (that flag
gates only the live hook). Note: `commit_author` /
`agent_contribution` / `manual:commit_message` are emitted at
hook-time only and are not back-filled by materialize.

**CI complement (optional).** The `edpa-contribution-sync.yml`
workflow runs `sync_pr_contributions.py` after a PR merges and emits
**only** the PR-thread events that don't exist in git history:
`pr_reviewer` (ref `PR#<num>:review:<id>`) and `issue_comment` (ref
`PR#<num>:comment:<id>`). Item matching *here* is mention-based — IDs
extracted from the PR title, branch name, and body. It deliberately
does not emit a `pr_author` signal (the local hook already credited
the author's commits) and does not parse `/contribute`. Skip this
workflow entirely if your team is single-dev, review-light, or off
GitHub.

**Legacy GH collectors (escape hatch).** `detect_contributors.py`
still contains the v1.11 live GitHub collectors (PR/issue API
surfaces, `manual:pr_body` / `manual:issue_*` / `manual:pr_comment`,
refs like `pr#<num>/commit/<sha>`). They are no-ops unless
`EDPA_USE_GH=1` is set — a debugging escape hatch, not a supported
attribution path.

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

`yaml_edit`, `agent_contribution`, and `state_transition` map to no
role label. A person who fires multiple signal types gets the
highest-priority role for display (timesheets, reports). The math
doesn't see roles — only `cw` × `JS` proportional allocation.

## Manual `/contribute` directive

`/contribute @<person> weight:<float>` in a **commit message body** is
the local-first manual surface: the hook emits `manual:commit_message`
for every item the commit works on (D-38 scope rule above). One
directive per person per commit is recorded — the signal `ref` is
`commit/<short>/contrib/<login>`, so put the person's whole credit in
a single line. The `weight:` value is the signal's contribution to
`contribution_score`, not the final cw; per-item normalization decides
the resulting share. See
[`docs/contribute-directive.md`](contribute-directive.md) for syntax,
surfaces, and usage patterns.

## Auditor verification

Every signal carries a `ref` that resolves in **any clone of the
repository** — no API access needed. On the item:

```yaml
evidence:
  - type: commit_author
    person: jurby
    weight: 4.0
    raw_weight: 4.0
    ref: commit/2fe43cb
    at: "2026-06-28T15:23:11+02:00"
```

To verify: `git show 2fe43cb` shows the commit, its author, its
subject scope, and the diff. Git's content-addressing makes the
referenced evidence immutable — rewriting it would change the SHA.
See [`docs/audit-references.md`](audit-references.md) for the full
reference taxonomy and per-signal verification commands, and
[`docs/audit-trail.md`](audit-trail.md) for freeze rules. The
detection model itself is specified in
[`docs/methodology.md`](methodology.md) §5.3–5.5.
