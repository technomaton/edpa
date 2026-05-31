# Proposal: Multi-contract person attribution via EDPA `id` (R-2 mitigation)

**Status:** proposal · **Surfaced by:** real-GitHub E2E run 2026-05-31 (`docs/v2/e2e-real-github-run-2026-05-31.md`) · **Tracks:** Risk R-2 ("multi-role person attribution edge cases")

## Problem

A person who holds two EDPA contracts (e.g. `bob-arch` + `bob-pm`, same human "Bob") shares a single GitHub handle in `people.yaml`:

```yaml
- id: bob-arch
  github: bob-arch-e2e
- id: bob-pm
  github: bob-arch-e2e      # same login
```

All identity resolution is **GitHub-login-based**:
- `detect_contributors.load_people_map` builds a `login → id` map; with a shared login the **first contract wins**, so `bob-pm` is unreachable.
- `/contribute @<login>` resolves through that same map (verified: `/contribute @bob-arch-e2e` credits `bob-arch`, never `bob-pm`).
- `local_evidence` commit-author resolution matches `email`/`name`/`github` — also shared.

Consequence: the second contract can **never receive distinct credit**. In the E2E run `bob-pm` derived 0h despite a real PM workload, and there is no directive that can fix it.

## Proposal

Make manual attribution addressable by canonical **EDPA `id`**, in addition to GitHub login.

1. **`/contribute @<id>` support.** When resolving a `/contribute @X` target, match `X` against `people.yaml` `id` values **first**; fall back to the `github` login map only if no `id` matches. `id`s and GitHub logins rarely collide; document the precedence (id wins). This lets a commit/PR/comment body credit `bob-pm` explicitly:
   ```
   /contribute @bob-pm weight:2.0      # PM coordination, distinct from bob-arch
   ```
2. **Resolver change points** (single helper, reused everywhere):
   - `detect_contributors.py` — `load_people_map` / the `/contribute` resolver.
   - `local_evidence.py` — `_resolve_person` + the `/contribute` commit-body parser.
   - Factor the "token → canonical id" resolution into one shared function (`resolve_attribution_target(token, people)`) so all surfaces behave identically.
3. **Automatic signals (commit/review) on a shared handle** still can't be disambiguated from GitHub data alone. Document that: auto-signals attribute to the **primary** contract (define primary = first entry, or add an optional `primary: true` field), and distinct credit for the other contract requires an explicit `/contribute @<id>`.
4. **Optional schema aid:** allow `aliases: [<id>, ...]` or surface `contract:` in reports so the dual-view can split a shared-handle human into per-contract lines.

## Backward compatibility

`@<login>` keeps working unchanged; `@<id>` is purely additive. Existing backlogs are unaffected (no `id`/`login` collisions in current fixtures).

## Tests to add

- `/contribute @bob-pm` credits `bob-pm` even though `bob-pm.github == bob-arch.github` (the exact R-2 case).
- Precedence: a token that is both a valid `id` and someone's `github` resolves to the `id`.
- Regression: `/contribute @<login>` for a unique handle still resolves to that person.

## Effort

Small–medium: one shared resolver + 3 call-site updates + docs (`docs/contribute-directive.md`) + tests. No data migration.
