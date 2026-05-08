# Audit Reference Taxonomy (v1.11)

Every evidence signal in a contributor's `signals[]` block carries a
`ref` field that **uniquely identifies the source on GitHub** and is
resolvable by `gh` CLI or an HTTPS URL. This document is the
canonical spec for that reference format, intended for auditors who
need to verify EDPA's contribution-share computations against the
underlying GitHub state.

## Reference format per signal type

| Signal type | `ref` format | Required IDs | Example |
|-------------|--------------|--------------|---------|
| `assignee` | `issue#<num>` | issue number | `issue#137` |
| `pr_author` | `pr#<num>` | PR number | `pr#146` |
| `commit_author` | `pr#<num>/commit/<sha>` | PR number, commit short-sha | `pr#146/commit/fa9f440` |
| `pr_reviewer` | `pr#<num>/review/<review_id>` | PR number, review API id | `pr#146/review/2845102347` |
| `issue_comment` | `issue#<num>/comment/<comment_id>` | issue number, comment API id | `issue#137/comment/c984712` |
| `manual:pr_body` | `pr#<num>/body` | PR number | `pr#146/body` |
| `manual:commit_message` | `commit/<sha>/message` | commit short-sha | `commit/fa9f440/message` |
| `manual:issue_body` | `issue#<num>/body` | issue number | `issue#137/body` |
| `manual:issue_comment` | `issue#<num>/comment/<comment_id>` | issue number, comment id | `issue#137/comment/c123456` |
| `manual:pr_comment` | `pr#<num>/comment/<comment_id>` | PR number, comment id | `pr#146/comment/c456789` |

The `<sha>` in commit refs is the **short SHA** (first 7 chars of the
full git commit ID); `gh` CLI accepts short SHAs in all relevant API
calls.

## Per-signal verification commands

### `assignee:#<num>` — issue assignee

```bash
gh issue view <num> --repo <org>/<repo> --json assignees
# → { "assignees": [{ "login": "<expected_login>", ... }] }
```

URL: `https://github.com/<org>/<repo>/issues/<num>` (Assignees panel
on right side)

### `pr_author:pr#<num>` — PR author

```bash
gh pr view <num> --repo <org>/<repo> --json author
# → { "author": { "login": "<expected_login>" } }
```

URL: `https://github.com/<org>/<repo>/pull/<num>` (header)

### `commit_author:pr#<num>/commit/<sha>` — commit author

```bash
gh api repos/<org>/<repo>/commits/<sha> | jq '.author.login, .commit.author'
# → expected login + commit author email
```

URL: `https://github.com/<org>/<repo>/pull/<num>/commits/<sha>`

### `pr_reviewer:pr#<num>/review/<review_id>` — PR review

```bash
gh api repos/<org>/<repo>/pulls/<num>/reviews/<review_id> | jq '.user.login, .state'
# → expected login + state ("APPROVED", "COMMENTED", "CHANGES_REQUESTED")
```

URL:
`https://github.com/<org>/<repo>/pull/<num>#pullrequestreview-<review_id>`

### `issue_comment:issue#<num>/comment/<comment_id>` — issue/PR comment

```bash
gh api repos/<org>/<repo>/issues/comments/<comment_id> | jq '.user.login, .body'
# → expected login + comment body
```

URL: `https://github.com/<org>/<repo>/issues/<num>#issuecomment-<comment_id>`

### `manual:pr_body:pr#<num>/body` — /contribute in PR description

```bash
gh pr view <num> --repo <org>/<repo> --json body | jq -r .body | grep -i '/contribute'
# → expected line(s) like "/contribute @<person> weight:<X>"
```

URL: `https://github.com/<org>/<repo>/pull/<num>` (PR description on
top)

### `manual:commit_message:commit/<sha>/message` — /contribute in commit message

```bash
git -C <repo_clone> show <sha> --format='%B' --no-patch | grep -i '/contribute'
# OR via gh API:
gh api repos/<org>/<repo>/commits/<sha> | jq -r '.commit.message' | grep -i '/contribute'
```

URL: `https://github.com/<org>/<repo>/commit/<sha>` (commit message
shown above the diff)

### `manual:issue_body:issue#<num>/body` — /contribute in issue description

```bash
gh issue view <num> --repo <org>/<repo> --json body | jq -r .body | grep -i '/contribute'
```

URL: `https://github.com/<org>/<repo>/issues/<num>` (issue description
on top)

### `manual:issue_comment` / `manual:pr_comment` — /contribute in any comment

Same verification commands as `issue_comment` (the comment is fetched
the same way; the `manual:` prefix just means EDPA's parser found a
`/contribute` directive inside).

## The `excerpt` field

For all `manual:*` signal types, the entry also carries an `excerpt`
field with the **literal /contribute line** as it appeared at
detection time:

```yaml
- type: manual:pr_body
  ref: pr#146/body
  excerpt: "/contribute @turyna weight:1.5"
  weight: 1.5
  detected_at: 2026-05-08T15:23:11Z
```

This is load-bearing for audit because GitHub does **not** preserve
edit history of PR descriptions or commit messages by default.
Without `excerpt`, an auditor verifying months later might see a
modified PR body that no longer contains the directive — and have no
way to know whether EDPA's signal record was bogus or whether the PR
was edited post-merge. With `excerpt`, the auditor sees what EDPA
actually matched and can compare against the current state.

The `detected_at` timestamp pins when EDPA captured the signal, so
discrepancies between excerpt and current GitHub state can be
attributed to post-detection edits rather than EDPA misreading.

## Common audit workflow

Given a snapshot file `.edpa/snapshots/iteration-PI-2026-1.4.json`,
verifying turyna's claim of 51% share on S-8:

1. Open `.edpa/backlog/stories/S-8.yaml`, find the `contributors`
   block where `person: turyna`.
2. Read the `signals[]` list — each entry is one piece of evidence.
3. For each signal: run the corresponding `gh` command from the
   table above using the `ref`. Compare result against the expected
   login (turyna's GitHub handle from `.edpa/config/people.yaml`).
4. Sum the `weight:` values across all of turyna's signals →
   `contribution_score`.
5. Sum `contribution_score` across **all contributors** on S-8 → item
   total.
6. Compute turyna's cw = turyna_score / item_total. Compare with the
   stored `cw:` value (should match within ~0.001 rounding).
7. Cross-check that `Σ cw[*, S-8] ≈ 1.0` — engine invariant.

If any signal's `gh` command returns a different login than expected
(or returns 404), the audit trail has been **broken**. Either the
GitHub data was modified post-detection (compare `detected_at`
against PR/issue updated_at), or there's a bug in the detector.
Either case is a finding to escalate.

## Bot exclusion

Comments authored by `<login>[bot]` (or known service accounts like
`edpa-bot`, `github-actions`) are **excluded** from `issue_comment`
signal collection. This prevents EDPA's own auto-commit messages or
GitHub Actions' status updates from accidentally crediting "the bot"
as a contributor. Manual `/contribute` directives in such comments
are still respected (they're explicit operator intent), just under
the appropriate `manual:` signal type, not `issue_comment`.
