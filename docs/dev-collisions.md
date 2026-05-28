# Developer guide — Resolving EDPA ID collisions

When two developers parallel-allocate the same backlog item ID (e.g., both add `S-5` on different feature branches), the second PR to merge will conflict on the file (`.edpa/backlog/stories/S-5.md`) and on `.edpa/config/id_counters.yaml`.

EDPA ships three layers of defense to detect and resolve this:

| Layer | When | Tool | Effect |
|---|---|---|---|
| **5 — pre-commit hook** | local commit | `validate_ids.py --staged` | Blocks commit if local-only IDs are inconsistent (filename≡id, missing fields, etc.) |
| **6 — pre-push hook** | local push | `validate_ids.py --pre-push` | Blocks push if local item IDs already exist on the integration target (typically `origin/main`) |
| **7 — CI workflow** | PR open / sync | `edpa-collision-check.yml` | Detects collision on PR, comments fix instructions, fails the check |
| **Manual recovery** | after conflict | `renumber_collisions.py --apply` | Renames local IDs to next free, updates parent references, bumps counter |

## Standard recovery flow

When your PR shows a conflict in `.edpa/backlog/` or `id_counters.yaml`:

```bash
# 1. Refresh local view of the integration target
git fetch origin

# 2. Run the auto-resolver (defaults to comparing against origin's default branch)
python3 .edpa/engine/scripts/renumber_collisions.py --apply

#    For Git Flow projects integrating to `develop`, use:
#    python3 .edpa/engine/scripts/renumber_collisions.py --apply --target develop

# 3. Review the output. You should see something like:
#    Detected 1 collision:
#      S-5 → S-6
#        Local:    .edpa/backlog/stories/S-5.md
#        Upstream: .edpa/backlog/stories/S-5.md
#    Files renamed:    1
#    parent: refs:     0
#    Counters bumped:  {'Story': 6}

# 4. Stage and commit the renumber
git add .
git commit -m "renumber(S-5→S-6): collision with main"

# 5. Merge the integration target into your branch
git merge origin/main

#    If id_counters.yaml conflicts here (common — both branches changed it):
#    Open the file, take the MAX of both counter values, save.
#      <<<<<<< HEAD
#      counters:
#        Story: 6
#      =======
#      counters:
#        Story: 5
#      >>>>>>> origin/main
#    Resolve to: counters:\n  Story: 6
git add .edpa/config/id_counters.yaml
git commit --no-edit

# 6. Push the resolved branch
git push origin <your-branch>
```

The PR will re-run CI within seconds and become MERGEABLE.

## What renumber_collisions.py does

1. **Fetches remote** to refresh upstream view.
2. **Resolves integration target** — defaults to `refs/remotes/<remote>/HEAD` (typically `main`). Override with `--target <branch>`.
3. **Computes the merge-base** between your HEAD and the target.
4. **Lists files added on your branch since merge-base** under `.edpa/backlog/`.
5. **For each added file**: checks if the same ID exists on the target branch. If yes → renumber candidate.
6. **For multiple collisions**: assigns sequentially incremented new IDs (e.g., two Story collisions → `S-5` + `S-6`, not both `S-5`).
7. **Applies renames**:
   - Renames file `.../S-5.md` → `.../S-6.md`
   - Rewrites `id:` field inside the file
   - Updates `parent: S-5` references in any other local file → `parent: S-6` (direct children only; grandchildren via different parent are untouched)
   - Bumps `.edpa/config/id_counters.yaml` to highest new ID

## What it does NOT do

- **Does not merge.** You still need `git merge` (or `git rebase`) after renumber to integrate the target branch.
- **Does not push.** You stage + commit + push manually after review.
- **Does not handle id_counters.yaml merge conflicts.** That file is a single-line counter that both branches mutate; git can't auto-resolve. Manually take the max value.
- **Does not modify already-merged items.** Only "files added since merge-base on this branch" are renumber candidates.

## Common cases

### Single collision (the standard case)

Two developers both create `S-5` on parallel branches. First to merge keeps `S-5`. Second runs the recovery flow above; their `S-5` becomes `S-6`.

### Multi-collision

Both branches added `S-5` AND `S-6`. After other dev merges, your branch's `S-5` → `S-7`, your `S-6` → `S-8` (sequential, no duplicate IDs).

### Parent chain

You created `F-3` plus `S-9`, `EV-1` as children of `F-3`. Another dev's `F-3` merged first. Your `F-3` becomes `F-4`, and `S-9` + `EV-1` automatically get `parent: F-4`. Grandchildren (e.g., `S-10` with `parent: S-9`) are untouched — their parent chain is via `S-9`, not directly via `F-3`.

### Cascading (3+ devs)

Dev A merges `S-5`. Dev B (also had `S-5`) renumbers to `S-6` and merges. Dev C (also had `S-5` AND `S-6` from before any merge) faces both — script detects both, renumbers to `S-7` + `S-8`.

## Bypass (NOT recommended)

```bash
git push --no-verify    # bypass pre-push hook
```

The PR-side CI workflow check will still fail. Don't bypass.
