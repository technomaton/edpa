# `/contribute` Directive

Manual contribution attribution for cases where automatic detection
doesn't capture the full picture: pair programming, silent reviewers,
consultants, retroactive credit corrections.

## Syntax

```
/contribute @<github-login> weight:<float>
```

- `@<github-login>` — GitHub username, must match the `github:` field of
  someone in `.edpa/config/people.yaml`. Detect resolves the login to
  the canonical person id.
- `@<person-id>` — alternatively, the canonical EDPA person id from
  `people.yaml` (e.g. `@bob-pm`). An id always resolves to itself and takes
  precedence over a github-handle collision. **Use this for multi-contract
  people who share a github handle** (e.g. `bob-arch` and `bob-pm` both
  `github: bob-arch-e2e`): the shared handle is ambiguous and credits only
  one contract, so address the intended one by id. A token matching neither
  a github handle nor a person id is credited as-is and earns 0h —
  `detect_contributors` warns on stderr so typos don't vanish silently.
- `weight:<float>` — non-negative number; this becomes the signal's
  contribution to that person's `contribution_score` on the item.
  Recommended range: 0.5 to 5.0 (in line with auto-detected signal
  weights in heuristics).

**No `as:role` clause.** Roles are derived at display time from signal
type — manual directives map to "key" by default. The pre-v1.11
`as:owner/key/reviewer/consulted` syntax is parsed by the regex but
ignored at output (kept for backward read compatibility only).

## Where it works

The directive is parsed on these surfaces — the **commit message
body** by `local_evidence.py` (the local-first primary path), the
GitHub surfaces by `detect_contributors.py`:

| Surface | Signal type emitted | Example use case |
|---------|--------------------|--------------------------|
| Commit message body | `manual:commit_message` | Mid-commit attribution by author |
| PR description (body) | `manual:pr_body` | Crediting a co-author who didn't commit |
| PR-level comment | `manual:pr_comment` | Post-merge correction by reviewer |
| Issue description (body) | `manual:issue_body` | Initial scope, who's responsible |
| Issue / PR comment | `manual:issue_comment` | Discussion-time attribution |

**Pipeline note.** In the default local-first pipeline only the
commit-message surface fires: the post-commit hook emits
`manual:commit_message` (ref `commit/<short>/contrib/<login>`)
automatically. The optional CI complement
(`sync_pr_contributions.py`) does **not** parse `/contribute` — the
four GitHub surfaces are collected only by the legacy live collectors
in `detect_contributors.py`, which require `EDPA_USE_GH=1` (debugging
escape hatch). If your team runs the default setup, put directives in
commit messages.

**Scope rule (D-38).** A commit-message directive credits the person
only on the items the commit actually **works on** — items in the
commit's leading Conventional-Commit scope (`fix(S-42): …` or the bare
`S-1: …` prefix) or items whose backlog `.md` file the commit changed.
Items merely mentioned elsewhere in the message get no manual signal
(their `commit_author` record is kept audit-only at `weight: 0`,
tagged `referenced`).

**Stacking semantics:** multiple directives for the same person on
the same surface stack additively.

```
/contribute @alice weight:1.0
/contribute @alice weight:0.5
```

→ alice gets a single `manual:<surface>` signal with weight 1.5
(merged at parse time) on the GitHub surfaces. The commit-message
path records at most **one** `manual:commit_message` signal per
person per commit (evidence is deduplicated by `ref`, which keys on
the login) — the first directive wins, so put the person's whole
credit in a single line.

Multiple directives across **different** surfaces are independent
signals with their own `ref`:

- `/contribute @alice weight:1.0` in PR body → `manual:pr_body` with
  weight 1.0
- `/contribute @alice weight:0.5` in commit msg → `manual:commit_message`
  with weight 0.5

Both flow through to alice's `contribution_score` and contribute
0.5 + 1.0 = 1.5 to her aggregate.

## Use cases

The examples below show the directive on the surface where the
situation naturally arises. On a default local-first setup, put the
same line in a commit message that works on the item instead (see the
pipeline note above).

### Pair programming

Bob is the PR author — his commits give him `commit_author` signals
automatically. Alice pair-programmed but didn't commit. In the PR body:

```
Closes #137. Pair-programmed with @alice.

/contribute @alice weight:2.0
```

Alice gets `manual:pr_body` weight 2.0, giving her a share alongside
bob's auto-detected `commit_author` credit.

### Silent reviewer

Carol reviewed the design in a meeting but didn't submit a GitHub PR
review. In the PR body:

```
Design reviewed in 5/8 architecture sync — thanks @carol.

/contribute @carol weight:1.0
```

### Domain consultant

Dave answered a question in a Slack thread but never touched the PR
or issue. In an issue comment after merge:

```
@dave provided the OMOP schema reference — credit on this story.

/contribute @dave weight:0.5
```

### Retroactive credit correction

A contributor was missed by auto-detection (e.g. their work never
produced a commit). While the item's iteration window is still open,
add the directive in a commit that works on the item — an empty commit
is enough:

```
git commit --allow-empty -m "docs(S-8): credit off-repo review" \
           -m "/contribute @alice weight:1.0"
```

Timing matters: the out-of-iteration gate (D-28/D-29) zeroes weighted
signals — `manual:commit_message` included — when the commit's own
iteration differs from the item's, so a correction committed after the
item's window closes is recorded **audit-only** (`weight: 0`,
`out_of_iteration`). Corrections to an already-frozen snapshot go
through the revision process in
[`docs/audit-trail.md`](audit-trail.md) instead. (In `EDPA_USE_GH=1`
mode, a `/contribute` line in a follow-up issue comment plus a re-run
of `detect_contributors.py --pr <N>` still works.)

## Anti-patterns

### Don't write `as:` clauses

```
# WRONG — pre-v1.11 syntax, the as: clause is silently dropped
/contribute @alice weight:0.7 as:owner
```

The role label is not stored. To express "alice is the primary
contributor", just give her a higher weight relative to others on
the same item:

```
# RIGHT — relative weight expresses dominance
/contribute @alice weight:3.0
/contribute @bob weight:0.5
```

After per-item normalization, alice gets ~86% share, bob gets ~14%.

### Don't try to "override" auto-detection

Manual directives **stack** with auto-detection — they don't
override. If alice is already credited as `commit_author` (weight
4.0) and you write `/contribute @alice weight:0.5`, she gets 4.0 +
0.5 = 4.5 contribution_score, not 0.5.

If you genuinely need to **suppress** alice's auto-detected
contribution (rare, audit-corrective), edit the YAML directly and
remove her from `contributors[]`. Re-running `detect_contributors`
will repopulate `contributors[]` from the recorded `evidence[]`, so
direct edits are not durable across detection runs.

### Don't use `/contribute` for status comments

```
# WRONG — comment doesn't actually credit anyone, just confuses parser
/contribute @alice weight:0    # she didn't help on this one
```

Use plain text for non-attribution comments. EDPA's regex matches
`weight:0` as a valid (zero-weight) signal — harmless but noise in
the audit trail. To explicitly note non-contribution, just don't
mention `/contribute` at all.

## Audit trail

Each recorded directive becomes one entry in the item's `evidence[]`
(and, aggregated, in `contributors[].signals[]`). On the primary
commit-message surface:

```yaml
- type: manual:commit_message
  person: alice
  weight: 2.0
  ref: commit/9a1b2c3/contrib/alice
  at: "2026-06-28T15:23:11+02:00"
```

Auditor verifies in any clone — no API access needed:

```bash
git show -s --format='%B' 9a1b2c3 | grep -i '/contribute'
# → "/contribute @alice weight:2.0"
```

The commit is content-addressed, so the directive text is immutable —
no `excerpt` field is needed. Signals from the mutable GitHub surfaces
(`manual:pr_body` etc., `EDPA_USE_GH=1` mode) do carry an `excerpt`
with the literal line as matched at detection time, because a PR body
can be edited after the fact:

```yaml
- type: manual:pr_body
  ref: pr#146/body
  excerpt: "/contribute @alice weight:2.0"
  weight: 2.0
  detected_at: 2026-05-08T15:23:11Z
```

See [`docs/audit-references.md`](audit-references.md) for the full
verification taxonomy.

## What about `/contribute` in EDPA's own engine output?

EDPA does **not** post `/contribute` comments back to GitHub on
behalf of detected contributors. Auto-detected signals
(`commit_author`, `yaml_edit`, `agent_contribution`, and the optional
`pr_reviewer` / `issue_comment`) flow directly into `evidence[]` →
`contributors[]` without round-tripping through GitHub. Only
operator-written directives become `manual:*` signals.

This keeps the data flow one-way (git/GitHub → local YAML), so EDPA
can operate on private repos without write permission to issues/PRs.
