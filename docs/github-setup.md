# Optional GitHub Integration

> **V2.1 positioning:** EDPA V2 is **local-first**. Its evidence
> collection runs against `git log` alone — you can produce derived
> timesheets, reports, and snapshots without ever touching GitHub.
> EDPA does **not** provision or manage a GitHub Project: there are no
> org-level Issue Types, no custom fields, no typed status fields, and
> no GitHub Projects automations owned by EDPA. (All of that was the V1
> path and was **removed in 2.0.0**.)
>
> There is exactly **one** optional GitHub integration: a CI workflow
> that, after a PR referencing an item (e.g. `feat(S-1): ...`) merges,
> materializes PR-thread signals (`pr_reviewer`, `issue_comment`) into
> that item's `evidence[]`. Everything else below describes **local**
> concepts that live in your `.edpa/backlog/` item files — not in
> GitHub. See [PR-signal sync (optional)](#pr-signal-sync-optional) for
> the only piece that touches GitHub.

## Item ID convention

Each work item has a unique ID with a type prefix and sequential number, starting from 1 per type:

| Type | Prefix | Example IDs |
|------|--------|-------------|
| Initiative | `I-` | I-1, I-2, I-3 |
| Epic | `E-` | E-1, E-2, E-3 |
| Feature | `F-` | F-1, F-2, F-3 |
| Story | `S-` | S-1, S-2, S-3 |
| Defect | `D-` | D-1, D-2, D-3 |
| Task | `T-` | T-1, T-2, T-3 |

- IDs are sequential per type (not globally unique across types)
- The prefix makes IDs globally unique: `S-1` and `F-1` are different items
- IDs are **stable once merged to main** — parallel-branch collisions are resolved automatically by `renumber_collisions.py` before merge (see [dev-collisions.md](dev-collisions.md))
- Markdown filename matches the ID: `.edpa/backlog/stories/S-1.md`
- Branch naming uses the ID: `feature/S-1-login-endpoint`
- Commit messages reference the ID: `feat(S-1): implement login`

## Status workflow

Status is a **local** concept: it lives in the `status:` field of each
item's `.md` frontmatter, not in any GitHub status field. The workflow
steps are SAFe-aligned:

- **Portfolio** (Initiative + Epic): Funnel → Reviewing → Analyzing → Ready → Implementing → Done
- **Delivery** (Feature + Story): Funnel → Analyzing → Backlog → Implementing → Validating → Deploying → Releasing → Done

**Engine logic:** the engine treats `status: Done` as finished; every
other value is in-work. There are no Blocked/Spillover labels.

## Granularity guardrails

- Story: max Job Size 8 (classic 2/10) or 5 (AI-native 1/5)
- Feature: max Job Size 13
- Epic: max Job Size 20
- Over limit → break down into smaller items

## Want a board?

You have two options, and EDPA only owns the first:

1. **Local HTML board (recommended)** — run `/edpa:board` to generate a
   self-contained Kanban view straight from your `.edpa/backlog/` item
   files. No GitHub, no setup, nothing to provision.
2. **Your own GitHub Project (manual)** — if you prefer a GitHub-native
   board, create a GitHub Project yourself and point it at the repo.
   This is entirely yours: EDPA will not create, configure, or touch it,
   and it is not required for any EDPA functionality.

## PR-signal sync (optional)

If you installed EDPA with `--with-ci`, the engine ships an optional CI
workflow at `.github/workflows/edpa-contribution-sync.yml`. After a pull
request that references an item (e.g. a commit/PR title like
`feat(S-1): ...`) is merged, the workflow runs
`.edpa/engine/scripts/sync_pr_contributions.py` to materialize PR-thread
signals — `pr_reviewer` and `issue_comment` — into that item's
`evidence[]`. This layers review/comment evidence on top of the
local-first `git log` evidence.

The workflow needs an `EDPA_TOKEN` repository secret. See
[edpa-token-setup.md](edpa-token-setup.md) for how to create and store
it.

---

_EDPA 2.1.8 — 2026-05-31_
