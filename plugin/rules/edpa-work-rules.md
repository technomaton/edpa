# EDPA Work Attribution Rules

> Auto-loaded when copied to `.claude/rules/edpa-work-rules.md` by
> `project_setup.py --with-rules`. These are the architectural rules
> for any agent (Claude Code, IDE assistants, automation scripts) that
> writes code in an EDPA-governed project.

## Core invariant

**Every commit attributes to an EDPA backlog item, in [Conventional Commits](https://www.conventionalcommits.org/) format.**

If the work doesn't have a ticket, create one first — then commit.

## Commit message format

EDPA uses Conventional Commits with the **ticket ID as scope**:

```
<type>(<ticket-id>): <subject>

[optional body]
[optional footer]
```

Concrete examples:

```
feat(S-42): implement OAuth callback handler
fix(S-215): validate upload file size before parsing
test(S-201): add unit tests for OMOP CDM parser
docs(E-10): update epic hypothesis with pilot feedback
refactor(F-100)!: replace legacy auth shim with new flow
```

Accepted types (Angular convention): `feat`, `fix`, `docs`, `style`,
`refactor`, `perf`, `test`, `build`, `ci`, `chore`. Use `!` after the
scope for breaking changes. The ticket ID in the scope is what the
commit-msg hook + `local_evidence.py` parse to attribute work.

## Before making any code change

1. **Check the backlog** for an existing ticket that covers the work:
   ```
   /edpa:backlog status                        # MCP read tool
   python3 .edpa/engine/scripts/backlog.py tree
   ```
   (Or look directly at `.edpa/backlog/{type}/*.md`.)

2. **If a ticket exists**, put its ID in the CC scope:
   ```
   git commit -m "feat(S-42): implement OAuth callback"
   ```

3. **If no ticket exists**, create one first via the MCP write tool:
   ```
   /edpa:add Story "OAuth callback handler" --parent F-100 --js 5
   ```
   Note the assigned ID from the output, then commit referencing it.

4. **If the work is genuinely out-of-scope** (typo fix in a comment,
   doc reformat, build config bump), use the `no-ticket:` escape
   prefix — the commit-msg hook accepts it and the reason stays in the
   commit log as audit trail:
   ```
   git commit -m "no-ticket: fix typo in README"
   ```
   (Escape prefixes intentionally bypass CC scope to make opt-outs
   visible in `git log --oneline`.)

## What gets blocked (and why)

The `commit-msg-ticket-attached` hook fails commits that:
- modify non-operational code paths AND
- have no EDPA item ID anywhere in the subject/body AND
- don't use an escape prefix (`no-ticket:`, `WIP:`, `[no-ticket]`) AND
- don't use an auto-prefix (`chore(evidence):`, `chore(ci-materialization):`, `Merge`, `Revert`, `Initial commit`, `fixup!`, `squash!`)

The CC scope (`feat(S-42):`) is the canonical way to satisfy the
ticket-ID requirement, but the hook is format-tolerant: any `S-42`
anywhere in the subject or body counts. Stick with CC for consistency
across human and agent commits — `local_evidence.py` also walks the
body looking for `/contribute @login weight:N` directives, so a clean
CC subject keeps the audit trail readable.

This catches the "did real work but forgot to attribute it" case
before `local_evidence.py` would silently emit nothing — leaving the
work unattributed in next iteration's `edpa-engine` allocation.

## What passes automatically

- **Operational changes only:** `README.md`, `LICENSE`, `.gitignore`,
  `package.json` bumps, `.github/` workflow tweaks, etc.
- **Auto-generated commits:** `chore(evidence):` (from
  `local_evidence.py`), `chore(ci-materialization):` (from CI),
  `Merge …`, `Revert …`, `fixup!`/`squash!`.
- **Empty diff** (e.g. `git commit --amend --no-edit`).

## For Claude Code / agent operators

When working in this repo, treat ticket-attribution as **part of the
work**, not a chore:

1. Read the user's request.
2. Identify or create the matching backlog item.
3. Reference its ID in the commit message.
4. Don't bypass the hooks with `--no-verify` unless the user
   explicitly authorises it.

This guarantees that the next `edpa-engine` run accounts for AI-driven
work the same way it accounts for human-driven work — through the
local evidence pipeline (`commit_author` → `evidence[]` → `contributors[]`
→ derived hours).

## Escape hatches (for emergencies only)

| Scenario | Action |
|---|---|
| Truly trivial change, no ticket worth opening | `no-ticket:` prefix |
| In-progress series, will squash later | `WIP:` prefix |
| Hot fix, ticket coming retroactively | `git commit --no-verify` + open ticket immediately after |
| Bulk migration, automation | Set `EDPA_NO_TICKET_CHECK=1` for the session |

Each escape is **logged either in the commit message or the user's
shell history**. Use them sparingly; their cumulative use signals that
the team is drifting from evidence-based allocation.

## Where this rule comes from

EDPA's invariant is `derived_hours == capacity` per person per
iteration. That invariant only holds if every unit of work the team
does becomes a signal that flows into `contributors[]`. Untracked work
isn't billable, isn't measurable, and isn't auditable. Tickets +
ticket-referenced commits are the contract.

See also:
- `docs/methodology.md` — EDPA scoring model
- `docs/v2/concept.md` — why local-first emit
- `plugin/edpa/scripts/local_evidence.py` — implementation
- `plugin/edpa/scripts/check_ticket_attached.py` — enforcement
