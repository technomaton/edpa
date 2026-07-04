# Audit Reference Taxonomy

Every evidence signal in an item's `evidence[]` block (and in the
aggregated `contributors[].signals[]`) carries a `ref` field that
**uniquely identifies its source**. This document is the canonical
spec for that reference format, intended for auditors who need to
verify EDPA's contribution-share computations against the underlying
evidence.

In the local-first pipeline the primary refs resolve **in any clone
of the repository** with plain `git` — no `gh` CLI, no API token, no
network. GitHub-side refs appear only when the optional CI complement
is installed (or legacy collectors were used; see the last section).

## Local git references (primary)

| Signal type | `ref` format | Example |
|-------------|--------------|---------|
| `commit_author` | `commit/<short>` | `commit/2fe43cb` |
| `agent_contribution` | `commit/<short>/agent/<agent>` | `commit/2fe43cb/agent/claude-sonnet-4-6` |
| `manual:commit_message` | `commit/<short>/contrib/<login>` | `commit/2fe43cb/contrib/alice` |
| `yaml_edit` | `commit/<short>/<id>.md` | `commit/9a1b2c3/S-8.md` |
| `state_transition` | `commit/<short>/<id>/<from>-><to>` | `commit/9a1b2c3/F-100/Backlog->Implementing` |

`<short>` is the **short SHA** (first 7 chars of the full commit ID);
git accepts short SHAs in all relevant commands. `<agent>` is the
normalized AI co-author name (`Claude Sonnet 4.6` →
`claude-sonnet-4-6`). The `manual:commit_message` ref keys on the
credited login, so one commit records at most one directive per
person. (The pre-V2 format `commit/<sha>/message` is superseded; it
may still appear in historical data.)

## Per-signal verification commands (git-local)

### `commit_author:commit/<short>` — commit author

```bash
git show -s --format='%an <%ae>%n%s' <short>
# → author name + email (map to the person via .edpa/config/people.yaml)
#   and the subject — its leading scope names the worked-on item (D-38)
```

### `agent_contribution:commit/<short>/agent/<agent>` — AI co-author

```bash
git show -s --format='%B' <short> | grep -i 'Co-Authored-By: Claude'
# → the trailer whose normalized name matches <agent> in the ref
```

### `manual:commit_message:commit/<short>/contrib/<login>` — /contribute

```bash
git show -s --format='%B' <short> | grep -i '/contribute'
# → "/contribute @<login> weight:<X>" — @<login> and weight must match
#   the signal's person and weight
```

### `yaml_edit:commit/<short>/<id>.md` — structural backlog edit

```bash
git show <short> -- '.edpa/backlog/*/<id>.md'
# → the actual diff. Compare against the signal's `delta` breakdown
#   (blocks / list items / scalars / lines ±) and `tags`
#   (e.g. create, block_add×2, bulk_discount).
```

### `state_transition:commit/<short>/<id>/<from>-><to>` — status flip

```bash
git show <short> -- '.edpa/backlog/*/<id>.md' | grep '^[-+]status:'
# → "-status: <from>" / "+status: <to>" matching the ref
```

Because git is content-addressed, the referenced evidence is
**immutable**: the commit message, diff, author, and dates cannot be
edited without changing the SHA the ref points to. That is why local
signals carry no `excerpt` field — the ref alone is tamper-evident.
(GitHub-side surfaces are mutable, which is what the `excerpt` field
below exists for.)

## Zero-weight audit records

A signal with `weight: 0` never enters `contribution_score` — it is
an audit/analytics record. The original value is preserved in
`raw_weight` and the reason is named in `tags`:

| Marker | Meaning |
|--------|---------|
| tag `referenced` | Item was merely mentioned in the commit message, not worked on (D-38) — full credit goes only to items in the commit's leading scope or whose backlog `.md` changed |
| tag `out_of_iteration` | Weighted signal on an item provably belonging to a different iteration than the commit's own (D-28/D-29), or timestamped provably outside the item's own iteration window when the commit sits in no window at all (D-63); for CI-side `pr_reviewer` / `issue_comment` the gate resolves per event `at:` timestamp (D-33) |
| type `state_transition` | Always weight 0 by design — analytics source, gate scoring derives engine-side |

An auditor seeing `weight: 0` + `raw_weight: 4.0` + a tag should read
it as "recorded, deliberately not credited" — not as missing data.

## CI complement references (optional, GitHub-side)

When `edpa-contribution-sync.yml` is installed, PR-thread events that
don't exist in git history are materialized after each PR merge:

| Signal type | `ref` format | Example |
|-------------|--------------|---------|
| `pr_reviewer` | `PR#<num>:review:<review_id>` | `PR#146:review:2845102347` |
| `issue_comment` | `PR#<num>:comment:<comment_id>` | `PR#146:comment:984712` |

Verification (needs `gh` CLI with access to the repo):

```bash
gh api repos/<org>/<repo>/pulls/<num>/reviews/<review_id> | jq '.user.login, .state'
# → expected login + state ("APPROVED", "COMMENTED", "CHANGES_REQUESTED")
gh api repos/<org>/<repo>/issues/comments/<comment_id> | jq '.user.login, .body'
# → expected login + comment body
```

URLs:
`https://github.com/<org>/<repo>/pull/<num>#pullrequestreview-<review_id>`
and `https://github.com/<org>/<repo>/issues/<num>#issuecomment-<comment_id>`.

The CI complement does **not** emit a `pr_author` signal (the local
hook already credited the author's commits — emitting it here would
double-count) and does **not** parse `/contribute`.

## Common audit workflow

Verifying a person's claimed share on an item (say `turyna` on S-8):

1. Open `.edpa/backlog/stories/S-8.md`. Read the `evidence[]` block —
   each entry is one piece of evidence with a resolvable `ref`.
2. For each signal, run the matching verification command above.
   Confirm the resolved author/login maps to the expected person via
   `.edpa/config/people.yaml`.
3. Sum the `weight:` values per person across all signals, **skipping
   zero-weight entries** → `contribution_score`.
4. Compare against the `contributors[]` block: per-person
   `contribution_score` should match (±0.01 rounding), and
   `cw = person_score / Σ_persons score`.
5. Cross-check `Σ cw[*, S-8] ≈ 1.0` — engine invariant.
6. For a frozen iteration, compare the item's `contributors[]` against
   the snapshot in `.edpa/snapshots/` (see
   [`docs/audit-trail.md`](audit-trail.md)).

If a ref does not resolve (`git show` fails in a full clone, or the
`gh` command 404s), the audit trail has been **broken** — either
history was rewritten post-detection or there is a detector bug.
Either case is a finding to escalate. Note that `git show <short>`
requires full history — use a non-shallow clone for audits.

## The `excerpt` field (GitHub surfaces)

Signals parsed from **mutable** GitHub surfaces (the legacy
`manual:pr_body`, `manual:issue_*`, `manual:pr_comment` types) also
carry an `excerpt` with the literal `/contribute` line as it appeared
at detection time:

```yaml
- type: manual:pr_body
  ref: pr#146/body
  excerpt: "/contribute @turyna weight:1.5"
  weight: 1.50
  detected_at: 2026-05-08T15:23:11Z
```

GitHub does not preserve edit history of PR descriptions by default.
Without `excerpt`, an auditor verifying months later might see a
modified PR body that no longer contains the directive — and have no
way to know whether EDPA's record was bogus or the PR was edited
post-merge. With `excerpt`, the auditor sees what EDPA actually
matched; `detected_at` (or `at` on local signals) pins when. Local git
refs don't need this — see the immutability note above.

## Legacy v1.11 reference formats (historical data)

Projects with evidence collected before the local-first pipeline (or
via the `EDPA_USE_GH=1` debugging escape hatch, which re-enables the
old live GitHub collectors) may carry these refs:

| Signal type | `ref` format | Verify with |
|-------------|--------------|-------------|
| `commit_author` | `pr#<num>/commit/<sha>` | `gh api repos/<org>/<repo>/commits/<sha>` |
| `pr_reviewer` | `pr#<num>/review/<review_id>` | `gh api repos/<org>/<repo>/pulls/<num>/reviews/<review_id>` |
| `issue_comment` | `issue#<num>/comment/<comment_id>` | `gh api repos/<org>/<repo>/issues/comments/<comment_id>` |
| `manual:pr_body` | `pr#<num>/body` | `gh pr view <num> --json body \| jq -r .body \| grep -i /contribute` |
| `manual:commit_message` | `commit/<sha>/message` | `git show -s --format='%B' <sha> \| grep -i /contribute` |
| `manual:issue_body` | `issue#<num>/body` | `gh issue view <num> --json body \| jq -r .body \| grep -i /contribute` |
| `manual:issue_comment` | `issue#<num>/comment/<comment_id>` | as `issue_comment` |
| `manual:pr_comment` | `pr#<num>/comment/<comment_id>` | `gh api repos/<org>/<repo>/issues/<num>/comments` |

These remain valid audit targets for the data that carries them; new
evidence is emitted in the local git formats above.

## Bot and tool exclusion

Signals are never credited to automation: commits authored by bot
identities (`*[bot]@*`, `github-actions@*`, the EDPA sync bot) and
tool-generated commits (`chore(evidence):`, `chore(ci-materialization):`,
`EDPA sync …`) produce no weight, and comments authored by `<login>[bot]`
or known service accounts are excluded from `issue_comment`
collection. This prevents EDPA's own materialization commits or CI
status updates from crediting "the bot" as a contributor. Manual
`/contribute` directives written by a human remain explicit operator
intent and are respected under the appropriate `manual:*` type.
