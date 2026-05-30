# EDPA ID Collision Handling — Developer Guide

When two developers parallel-allocate the same backlog item ID (e.g., both add `S-5` on different feature branches before either has merged), the second PR to land will conflict on the item file (`.edpa/backlog/stories/S-5.md`) and the counter file (`.edpa/config/id_counters.yaml`).

EDPA ships **four layers of defense** to detect early and recover semi-automatically.

## When does a collision happen?

```
T+0  alice  git pull main  →  last Story is S-4 (id_counters: Story=4)
T+0  bob    git pull main  →  last Story is S-4 (id_counters: Story=4)

T+1  alice  /edpa:add Story --title "Auth"     →  allocates S-5 (Auth)
T+1  bob    /edpa:add Story --title "Reports"  →  allocates S-5 (Reports)  ⚠ same ID!
            (both pulled before either's PR merged → id_counter was 4 for both)

T+2  alice  git push → PR #1 opens   ✓ no conflict yet (main still has no S-5)
T+2  bob    git push → PR #2 opens   ✓ no conflict yet

T+3  alice  /merge → main has S-5 (Auth), id_counters Story=5

T+4  bob    PR #2 status → CONFLICTING  ⚠
            (conflict on .edpa/backlog/stories/S-5.md and id_counters.yaml)

T+5  bob    Recovery: python3 .edpa/engine/scripts/renumber_collisions.py --apply
            → "Detected 1 collision: S-5 → S-6"
            → bob's local S-5.md renamed to S-6.md, id field rewritten
            → counter bumped to 6
            bob: git add . && git commit && git merge main && git push
            → bob's PR mergeable, squash-merge → main has S-5 (Auth) + S-6 (Reports)
```

## Four defense layers (cumulative)

```
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 5 — Pre-commit hook (local, before commit)                       │
│   Script: validate_ids.py --staged                                     │
│   Checks: filename ≡ id, id field present, counter ≥ max staged id,    │
│           parent refs valid, no duplicates in staged set               │
│   Blocks: commit, if any check fails                                   │
│   Bypass: git commit --no-verify (NOT recommended)                     │
└────────────────────────────────────────────────────────────────────────┘
                              ↓ commit OK
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 6 — Pre-push hook (local, before git push)                       │
│   Script: validate_ids.py --pre-push                                   │
│   Checks: fetch origin, compare local-added items against              │
│           refs/remotes/origin/HEAD (integration target tip).           │
│           Block push if local item ID exists upstream.                 │
│   Blocks: push, with message "run renumber_collisions.py to fix"      │
│   Bypass: git push --no-verify (NOT recommended)                       │
└────────────────────────────────────────────────────────────────────────┘
                              ↓ push OK
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 7 — CI workflow (server-side, on every PR)                       │
│   Trigger: pull_request opened/synchronize/reopened                    │
│            paths: .edpa/backlog/** OR .edpa/config/id_counters.yaml    │
│   Workflow: .github/workflows/edpa-collision-check.yml                 │
│   Action: run renumber_collisions.py --check                           │
│   Effect on collision:                                                 │
│     • Posts a comment on the PR with detection output + fix commands   │
│     • Fails the check (PR's merge button stays disabled)               │
│   Bypass: NONE (server-side, not skippable by --no-verify)             │
└────────────────────────────────────────────────────────────────────────┘
                              ↓ collision found OR not
┌────────────────────────────────────────────────────────────────────────┐
│ RECOVERY — Manual fix (local, semi-automatic)                          │
│   Script: renumber_collisions.py --apply                               │
│   Action:                                                              │
│     1. Fetch origin                                                    │
│     2. Detect collisions vs origin/main (or --target <branch>)         │
│     3. For each collision: rename file (S-5.md → S-6.md),              │
│        rewrite id field inside, update parent: refs in other files     │
│     4. Bump id_counters.yaml to highest new ID                         │
│   Dev then: git add . && git commit && git merge main &&               │
│             (resolve id_counters max) && git push                      │
└────────────────────────────────────────────────────────────────────────┘
```

## Decision tree — "I got a conflict, what do I do?"

```
You see a conflict on .edpa/backlog/ or id_counters.yaml in your PR or push.
│
├── Did pre-push hook block the push?
│   ├── YES → Hook message points to renumber_collisions.py.
│   │        Go to RECOVERY FLOW below.
│   │
│   └── NO (push succeeded, conflict shown on PR) →
│       ├── Does CI workflow comment exist on the PR?
│       │   ├── YES → Follow the comment instructions (= RECOVERY FLOW).
│       │   └── NO → CI workflow not installed; run RECOVERY FLOW manually.
│       │
│       └── Go to RECOVERY FLOW.
│
└── Was the conflict on something OTHER than .edpa/backlog/ or id_counters.yaml?
    → That's a normal merge conflict, not an EDPA ID collision.
      Resolve via standard git merge/rebase. renumber_collisions doesn't apply.
```

## Recovery flow (the canonical recipe)

```bash
# 1. Refresh local view of the integration target (main)
git fetch origin

# 2. Run the auto-resolver
python3 .edpa/engine/scripts/renumber_collisions.py --apply

#    For Git Flow projects integrating to `develop`:
#    python3 .edpa/engine/scripts/renumber_collisions.py --apply --target develop

# 3. Review the output. You should see something like:
#    Fetching origin (target: main)...
#    Detected 1 collision:
#      S-5 → S-6
#        Local:    .edpa/backlog/stories/S-5.md
#        Upstream: .edpa/backlog/stories/S-5.md
#    Done.
#      Files renamed:    1
#      parent: refs:     0
#      Counters bumped:  {'Story': 6}

# 4. Stage and commit the renumber
git add .
git commit -m "renumber(S-5→S-6): collision with main"

# 5. Merge the integration target into your branch
git merge origin/main

#    Expect a conflict on .edpa/config/id_counters.yaml — both branches
#    bumped the same line from a common base. Git cannot auto-merge
#    a single-line counter. Resolve manually by taking the MAX value:
#
#      <<<<<<< HEAD
#      counters:
#        Story: 6           ← your branch (post-renumber)
#      =======
#      counters:
#        Story: 5           ← main's value (before your renumber)
#      >>>>>>> origin/main
#
#    Pick: counters:\n  Story: 6 (the higher value).

git add .edpa/config/id_counters.yaml
git commit --no-edit

# 6. Push the resolved branch
git push origin <your-branch>
```

GitHub re-computes mergeability within ~30s. The PR's CI check re-runs and the merge button enables.

## What `renumber_collisions.py` does internally

1. **Fetches remote** to refresh the upstream view.
2. **Resolves integration target** — auto-detects via `refs/remotes/<remote>/HEAD` (typically `main`). Override with `--target <branch>` for Git Flow with `develop`.
3. **Computes merge-base** between your branch HEAD and the target.
4. **Lists files added on your branch since merge-base** under `.edpa/backlog/` (`git diff --diff-filter=A`).
5. **For each added file**: checks if the same ID exists on the target branch. If yes → renumber candidate.
6. **For multiple collisions in one call**: assigns sequentially incremented new IDs. Two Story collisions → `S-N+1` + `S-N+2`, not both `S-N+1`.
7. **Applies renames**:
   - Renames file `.../S-5.md` → `.../S-6.md`
   - Rewrites `id:` field inside the file
   - Updates `parent: S-5` references in any other local file → `parent: S-6` (direct children only)
   - Bumps `.edpa/config/id_counters.yaml` to highest new ID

## What it does NOT do

- **Does not merge.** You still run `git merge` (or `git rebase`) after the renumber commit. The script just rewrites IDs, it doesn't pull integration target history.
- **Does not push.** You stage + commit + push manually after review.
- **Does not auto-resolve `id_counters.yaml` merge conflicts.** That file is a single-line counter that both branches mutate; git's 3-way merge sees a real conflict. Resolve by taking the max value (always safe — counter is monotonic).
- **Does not modify already-merged items.** Only "files added on your branch since merge-base" are renumber candidates. Modifying an existing item (changing title/status/etc.) is resolved via normal merge.
- **Does not touch grandchildren outside the direct parent chain.** If you renumber `F-3 → F-4`, the script updates `parent: F-3 → F-4` in any file directly referencing F-3. Grandchildren whose chain goes via another item (e.g., `S-10` with `parent: S-9`) are correctly left untouched.

## Common collision shapes

### Single collision (the standard case)

Two devs both create `S-5` on parallel branches. First to merge keeps `S-5`. Second runs the recovery flow above; their `S-5` → `S-6`.

### Multi-collision

Both branches added `S-5` AND `S-6`. After the other dev merges, your branch's `S-5` → `S-7`, your `S-6` → `S-8` (sequential, no duplicates).

### Parent chain

You created `F-3` plus `S-9`, `EV-1` as children of `F-3`. Another dev's `F-3` merged first. Your `F-3` → `F-4`, and `S-9` + `EV-1` automatically get `parent: F-4`. Grandchildren (e.g., `S-10` with `parent: S-9`) are correctly left at `parent: S-9`.

### Cross-type collision (rare)

Both branches added `S-5` AND `F-3`. Separate counters per type → both renumber independently: `S-5 → S-6`, `F-3 → F-4`.

### Cascading (3+ devs)

Dev A merges `S-5`. Dev B (also had `S-5`) renumbers to `S-6` and merges. Dev C (had `S-5` AND `S-6` from before any merge) faces both — script detects both, renumbers to `S-7` + `S-8`.

## Installation

### Pre-commit + pre-push hooks (Layers 5 + 6)

Installed automatically by `/edpa:setup --with-hooks`:

```bash
python3 .edpa/engine/scripts/project_setup.py --with-hooks
# → installs .git/hooks/pre-commit (validate_ids --staged)
# → installs .git/hooks/pre-push   (validate_ids --pre-push)
# → installs .git/hooks/commit-msg (ticket-attached check)
# → installs .git/hooks/post-commit (local evidence emitter)
```

If you skipped `--with-hooks` initially, re-run with it later — the install is idempotent (existing hooks preserved unless missing).

### CI workflow (Layer 7)

Copy the template into your project's workflows directory:

```bash
cp .edpa/engine/templates/github-workflows/edpa-collision-check.yml \
   .github/workflows/edpa-collision-check.yml

git add .github/workflows/edpa-collision-check.yml
git commit -m "ci: add EDPA collision check"
git push origin main
```

The workflow runs on every PR touching `.edpa/backlog/**` or `id_counters.yaml`. No further configuration needed — it uses `GITHUB_TOKEN` for the PR comment.

## Bypass (NOT recommended)

```bash
git commit --no-verify   # bypass pre-commit hook (Layer 5)
git push --no-verify     # bypass pre-push hook (Layer 6)
```

The CI workflow (Layer 7) is server-side and **cannot be bypassed**. Your PR check will fail; reviewer can override with `--admin` merge, but that's a flag worth flagging in retro.

## Troubleshooting

### "Pre-push hook installed but doesn't fire on push"

Check that `.git/hooks/pre-push` is executable:
```bash
ls -la .git/hooks/pre-push
chmod +x .git/hooks/pre-push   # if not -rwxr-xr-x
```

### "renumber_collisions says 'No collisions detected' but PR shows conflict"

Verify the script is **v2.1.5 or later**. Earlier versions had a bug where the script compared against `origin/<your-branch>` instead of `origin/main`, producing false negatives. Update:

```bash
python3 .edpa/engine/scripts/renumber_collisions.py --help | grep target
# Should show: --target ... (default: remote's default branch, typically main)
```

If not, update EDPA:
```bash
bash <(curl -fsSL https://edpa.technomaton.com/install.sh)
```

### "I want to use a branch other than main as integration target"

Pass `--target <branch>` to all three tools:

```bash
python3 .edpa/engine/scripts/renumber_collisions.py --apply --target develop
```

Pre-push hook uses `origin/HEAD` symbolic ref — if your repo's default branch is correctly set to `develop` on the remote, the hook auto-detects it. Check:

```bash
git remote show origin | grep "HEAD branch"
# HEAD branch: develop   ← good
```

If wrong:
```bash
git remote set-head origin --auto
```

### "Counter file `id_counters.yaml` is desynced after renumber"

If the script reports `Counters bumped: {}` but you expected a bump, check that the counter file exists:
```bash
ls -la .edpa/config/id_counters.yaml
# If missing: python3 .edpa/engine/scripts/id_counter.py --rebuild
```

The script bumps the counter only if the new max ID exceeds the existing counter value. If you've already manually bumped, no change is needed.

## Related

- [Methodology — EDPA architecture overview](methodology.md)
- [`/edpa:setup` skill — installs hooks](../plugin/skills/edpa-setup/SKILL.md)
- [`/edpa:add` skill — allocates IDs](../plugin/skills/edpa-add/SKILL.md)
- [E2E test reproducing collision workflow](../tests/e2e_collision/scenario_a.sh)
- [CHANGELOG v2.1.5 — collision detection fix](../CHANGELOG.md)
