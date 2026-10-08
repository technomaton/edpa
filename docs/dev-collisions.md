# EDPA ticket IDs — allocation, collisions and recovery

Every backlog item has an ID like `S-42`. Commit scopes, evidence and audit
all key on it, so two items must never share one. This guide covers how IDs
are handed out, what stops a collision, and what to do when one slips through.

There are two **ID authorities**. A project uses one of them:

| | `local` | `remote` |
|---|---|---|
| Who hands out the number | a counter in your checkout | a ledger on the shared git remote |
| Unique across worktrees of one clone | yes | yes |
| Unique across clones / developers | **no** — detected later, repaired by renumbering | **yes** — at the moment it is assigned |
| Needs the network to create a ticket | no | yes (or a pre-reserved block) |
| `id_counters.yaml` | rewritten by every new ticket | left alone |
| Good for | solo work, no shared remote | any team, any number of parallel worktrees / agents |

```bash
python3 .edpa/engine/scripts/id_counter.py status     # which one is active, and why
```

## Remote ID authority (ADR-014)

> One-page cut-over guide for the team (Czech, with a diagram):
> [id-ledger-prechod.md](id-ledger-prechod.md). How it works inside git:
> [id-ledger.md](id-ledger.md).

### How it works

The arbiter is the git remote you already push to — no forge API, no `gh`.

```
/edpa:add Story "Auth"
   │
   ├─ 1. read the ID ledger: a ref on origin (refs/edpa/ids) whose tip
   │     holds counters.yaml → Story: 284
   ├─ 2. build one commit: Story: 285, message "alloc S-285: Auth"
   ├─ 3. push it ONLY IF the ref still points where step 1 saw it
   │        ├─ accepted  → S-285 is yours, everywhere, right now
   │        └─ rejected  → someone else took 285; re-read, try 286
   └─ 4. write .edpa/backlog/stories/S-285.md and commit it on your branch
```

Step 3 is a compare-and-swap enforced by the git server: of any number of
people pushing at once, exactly one wins each round. The ticket **file** still
travels with your feature branch — only the **number** is reserved up front, so
there is no reason to merge a ticket through a PR just to "claim" its ID.

The ledger is ordinary git:

```bash
python3 .edpa/engine/scripts/id_counter.py status --refresh
git log refs/edpa/cache/ids --format='%s  [%an, %ar]' | head    # who reserved what
```

### Switching a project over (once per repository)

```bash
# 1. Everyone: update the EDPA plugin, restart sessions, push ticket branches.

# 2. One maintainer, from the fullest clone:
python3 .edpa/engine/scripts/id_counter.py init-remote --write-config
#    → fetches every branch, takes the highest ID per type across all
#      worktrees and branches, shows the plan, asks, then
#      creates the ledger and prepares the opt-in in edpa.yaml.

# 3. Commit the one-line opt-in through your normal review:
git add .edpa/config/edpa.yaml
git commit -m "chore(no-ticket): reserve ticket IDs in the shared ledger"
```

From step 2 on, every session of that clone reserves IDs in the ledger — also
in worktrees cut long before the opt-in commit. Every other clone switches as
soon as it **fetches** the opt-in (`git fetch` / `git pull`; the pre-push hook
fetches too) — it does not have to merge it first.

- **Numbering simply continues** — the first new Story is the one after the
  highest existing. That is why step 1 matters: a session still on an outdated
  plugin mints a number the ledger gives to someone else, and the hooks stop
  it. If you cannot get everyone updated first, leave room for them with
  `--headroom N` (about a tenth of a type's size, at most N).
- **`id_counters.yaml` is left as it is.** Branches that created a ticket
  before the switch carry a bump of it; the file keeps merging as before until
  they are gone, and nothing new writes it. Delete it later if you like.
- Tickets created *before* the switch on two branches with the same number
  still collide — see [Recovery](#recovery-flow-the-canonical-recipe). The
  replacement ID then comes from the ledger.

### What the hooks check

| Hook | Check under the remote authority |
|---|---|
| pre-commit (`validate_ids.py --staged`) | every **new** item is backed by the ledger: its number is at or below the ledger's *floor* (it predates the ledger), or the ledger holds a reservation whose `created_at` equals the item's |
| pre-push (`validate_ids.py --pre-push`) | the same, online — this is what catches `--no-verify` commits and outdated allocators — plus the same-ID-different-item check against the integration branch |
| CI (`renumber_collisions.py --check`) | the same for the whole pull request |

An item you did not create with `/edpa:add` (`backlog.py add`) has no
reservation and is blocked. That is intended: hand-picked numbers are exactly
what collides.

### Working offline

No reservation, no ID — the allocator never guesses a number and "registers it
later" (that is how two diverging ID series start). Take a block while you are
online instead:

```bash
python3 .edpa/engine/scripts/id_counter.py reserve --type Story --count 5
```

Those numbers are yours. `/edpa:add` uses them only when the remote cannot be
reached; unused ones simply stay unused.

### When it says no

| Message | Meaning | Do |
|---|---|---|
| `the ID ledger … does not exist yet` | the project opted in but nobody created the ledger | `id_counter.py init-remote` |
| `cannot reach the ID ledger … only reserved online` | network / credentials; nothing was written | fix the connection (`git fetch` must work), retry, or use a reserved block |
| `the remote does not let this environment update the ID ledger` | this environment may not push that ref (a sandbox limited to its own branch, a fork, a read-only token) | create the ticket from a clone that can push |
| `S-41 has no reservation in the ID ledger` | the item was not created by the allocator, or by an outdated plugin | update the plugin, re-create the item with `/edpa:add` |
| `S-41 is reserved in the ID ledger for a different item` | someone else holds that number (possibly unmerged) | same — your item needs its own ID |
| `this checkout holds S-9999, … above the shared ledger` | a stray file would inflate everyone's sequence | remove it; if it is real, `id_counter.py doctor --raise` |

`id_counter.py doctor` checks a checkout against the ledger and names every
item that is not backed.

### Good to know

- The push that reserves an ID carries one metadata commit and skips your
  `pre-push` hook on purpose (it would otherwise run your test suite for every
  ticket). It never pushes source code.
- The ledger ref cannot be protected by branch rules on GitHub. It does not
  need to be: every clone caches it, the counters only ever go up, and a
  deleted, rewound or force-pushed ledger is repaired by the next reservation
  from any clone that remembers more.
- A forge that refuses custom ref namespaces: host it on a branch —
  `ids: {ref: refs/heads/edpa-ids}` in `edpa.yaml`. Same code.
- `git log --all` shows the ledger's commits. They are small and unrelated to
  your history.
- `EDPA_ID_AUTHORITY=local|remote` overrides the mode for one command. In a
  remote-mode project an ID minted under `local` is not backed by the ledger
  and the hooks will reject it.

## Local ID authority

`next = max(id_counters.yaml, highest item file, clone high-water mark) + 1`,
under a file lock. All worktrees of one clone share the lock and the
high-water mark (they live in the git directory), so they never hand out the
same number. **Two clones do** — the counter is per checkout, and each
developer's checkout only knows what it has pulled.

### When does a collision happen?

```
T+0  alice  git pull main  →  last Story is S-4 (id_counters: Story=4)
T+0  bob    git pull main  →  last Story is S-4 (id_counters: Story=4)

T+1  alice  /edpa:add Story --title "Auth"     →  allocates S-5 (Auth)
T+1  bob    /edpa:add Story --title "Reports"  →  allocates S-5 (Reports)  ⚠ same ID!

T+2  alice  merges → main has S-5 (Auth)

T+3  bob    git push  →  pre-push hook: "S-5 already exists on origin/main
                          as a different item — yours: Reports, upstream: Auth"
T+4  bob    python3 .edpa/engine/scripts/renumber_collisions.py --apply
            → S-5 → S-6, references updated, counter bumped
```

### Defense layers

| Layer | Where | What it does |
|---|---|---|
| pre-commit (`validate_ids.py --staged`) | local | filename ≡ `id:`, no duplicate in the staged set, new ID not already at HEAD, counter grew with the new items |
| pre-push (`validate_ids.py --pre-push`) | local | blocks when an item you add already exists on the integration branch **as a different item** — also when both sit at the same path, which is the usual case. Your own item that already landed there (e.g. squash-merged) is recognised and passes |
| CI (`edpa-collision-check.yml`) | server | `renumber_collisions.py --check` on pull requests touching `.edpa/backlog/**` |
| git itself | server | two branches adding the same file conflict on merge — the backstop when hooks were skipped |
| recovery | local | `renumber_collisions.py --apply` |

A same-path collision makes the pull request *conflicting*, and GitHub does
not run `pull_request` workflows on conflicting PRs — so do not expect the CI
check to be the one that tells you. The pre-push hook is.

## Decision tree — "I got a conflict, what do I do?"

```
You see a conflict on .edpa/backlog/ or id_counters.yaml in your PR or push.
│
├── Is the conflict INSIDE the evidence[] list of an EXISTING item
│   (machine-generated entries on both sides, from chore(evidence): commits)?
│   → NOT an ID collision — renumber_collisions.py correctly reports
│     "No collisions detected" here. Resolve by UNION (keep both sides).
│     See "evidence[] merge conflicts on an existing item" below.
│
├── Is it only id_counters.yaml (both sides bumped the counter)?
│   → Take the HIGHER value. (Under the remote authority this only happens
│     between branches that created tickets before the switch.)
│
├── Is it a NEW item file (same ID added on both branches)? → ID collision:
│   → Go to RECOVERY FLOW below.
│
└── Something OTHER than .edpa/backlog/ or id_counters.yaml?
    → A normal merge conflict. renumber_collisions doesn't apply.
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
#
#    Under the remote authority the new ID is a fresh reservation from the
#    ledger ("S-5 → (next free ID, reserved from the ledger on apply)") and
#    no counter is bumped.

# 4. Stage and commit the renumber
git add .
git commit -m "chore(S-6): renumber from S-5 — collision with main"

# 5. Merge the integration target into your branch
git merge origin/main

#    Local authority: expect a conflict on .edpa/config/id_counters.yaml —
#    both branches bumped the same line. Take the MAX value:
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

Commits you made before the renumber still carry the old ID in their message.
If the branch is squash-merged, fix the PR title; otherwise the evidence
already recorded in the item file moved with it and stays correct.

## evidence[] merge conflicts on an existing item

The everyday team conflict is **not** the parallel-new-ID case above — it is two
developers committing against the **same existing item** on different branches.
The post-commit hook (`local_evidence.py`) appends machine-generated entries to
the touched item's `evidence[]` frontmatter list and auto-commits them
(`chore(evidence): …`) on each developer's machine. Both branches therefore
edit the same YAML list, and the merge can conflict inside it. (`evidence[]`
is kept sorted by `ref`, so insertion points scatter across the list —
short/young lists conflict most often.)

**This is not an ID collision.** `renumber_collisions.py` reports
"No collisions detected" for it — correctly. Do not renumber anything.

### Resolution: UNION — keep every entry from both sides

```text
<<<<<<< HEAD
- ref: "a1b2c3d"            ← your branch's entries
  type: commit_author
  ...
=======
- ref: "e4f5a6b"            ← their branch's entries
  type: commit_author
  ...
>>>>>>> origin/main
```

Delete the conflict markers and keep **all** entries from both sides. Unioning
is always safe:

- signal `ref`s are unique per source commit, so the union holds no logical
  duplicates;
- `local_evidence.py` (`_apply_to_item`) re-dedups by `ref` and re-sorts the
  list on its next write, so ordering and any accidental duplicate self-heal.

Afterwards, optionally reconcile transition/yaml-edit signals for the
iteration (idempotent — dedup by `ref`):

```bash
python3 .edpa/engine/scripts/local_evidence.py --materialize --iteration <ITER-ID>
```

### Never resolve by taking one side

Taking "ours" or "theirs" **silently and permanently discards the other
developer's `commit_author` / `agent_contribution` entries**. Those signals are
emitted only by the post-commit hook at commit time; `--materialize` back-fills
**only** `state_transition` and `yaml_edit` signals and has no replay path for
commit-time signals at arbitrary SHAs. A dropped `commit_author` entry (weight
4.0 — the dominant contribution-weight signal) skews the derived-hours
allocation this tool exists to guarantee, with nothing left behind to detect
the loss.

## What `renumber_collisions.py` does internally

1. **Fetches remote** to refresh the upstream view.
2. **Resolves integration target** — auto-detects via `refs/remotes/<remote>/HEAD` (typically `main`). Override with `--target <branch>` for Git Flow with `develop`.
3. **Computes merge-base** between your branch HEAD and the target.
4. **Lists files added on your branch since merge-base** under `.edpa/backlog/` (`git diff --diff-filter=A`).
5. **For each added file**: checks if the same ID exists on the target branch **as a different item**. An item of your branch that already landed there (same `created_at`; for older items, same content lineage) is not a collision.
6. **Picks the new ID**: local authority — one above the highest known number, sequentially for several collisions; remote authority — a fresh reservation from the ledger, made on `--apply`, never during detection.
7. **Applies renames**:
   - Renames file `.../S-5.md` → `.../S-6.md`
   - Rewrites `id:` field inside the file
   - Updates references to it: `parent:` and `depends_on:` in other local items, item lists in `.edpa/iterations/*.yaml`
   - Local authority: bumps `.edpa/config/id_counters.yaml` to the highest new ID

`--check` (CI) never modifies anything. Under the remote authority it also
reports items the branch adds without a reservation.

## What it does NOT do

- **Does not merge.** You still run `git merge` (or `git rebase`) after the renumber commit.
- **Does not push.** You stage + commit + push manually after review.
- **Does not auto-resolve `id_counters.yaml` merge conflicts.** Both branches mutated one line; take the max (always safe — the counter is monotonic).
- **Does not modify already-merged items.** Only "files added on your branch since merge-base" are candidates.
- **Does not rewrite history or prose.** Commit messages, evidence refs (`commit/<sha>/S-5.md`) and body text keep the ID they were written with.
- **Does not touch grandchildren outside the direct parent chain.** If you renumber `F-3 → F-4`, files referencing F-3 are updated; `S-10` with `parent: S-9` is correctly left alone.

## Common collision shapes

### Single collision (the standard case)

Two devs both create `S-5` on parallel branches. First to merge keeps `S-5`. Second runs the recovery flow above; their `S-5` → `S-6`.

### Multi-collision

Both branches added `S-5` AND `S-6`. After the other dev merges, your branch's `S-5` → `S-7`, your `S-6` → `S-8` (sequential, no duplicates).

### Parent chain

You created `F-3` plus `S-9`, `EV-1` as children of `F-3`. Another dev's `F-3` merged first. Your `F-3` → `F-4`, and `S-9` + `EV-1` automatically get `parent: F-4`.

### Cross-type collision (rare)

Both branches added `S-5` AND `F-3`. Separate counters per type → both renumber independently: `S-5 → S-6`, `F-3 → F-4`.

### Cascading (3+ devs)

Dev A merges `S-5`. Dev B (also had `S-5`) renumbers to `S-6` and merges. Dev C (had `S-5` AND `S-6` from before any merge) faces both — script detects both, renumbers to `S-7` + `S-8`.

## Installation

### Pre-commit + pre-push hooks

Installed by `/edpa:setup --with-hooks`:

```bash
python3 .edpa/engine/scripts/project_setup.py --with-hooks
# → pre-commit  (validate_ids --staged)
# → pre-push    (validate_ids --pre-push)
# → commit-msg  (ticket-attached check)
# → post-commit (local evidence emitter)
```

Idempotent; lefthook-aware (one `extends:` line instead of `.git/hooks/`).

### CI workflow

`/edpa:setup --with-ci` copies `edpa-collision-check.yml` (and the
contribution-sync workflow) to `.github/workflows/`. It runs on every PR
touching `.edpa/backlog/**` or `id_counters.yaml`. It only reads the
repository (under the remote authority that includes fetching the ID ledger)
and comments on the PR.

## Bypass (NOT recommended)

```bash
git commit --no-verify   # bypass pre-commit
git push --no-verify     # bypass pre-push
```

The CI workflow is server-side and cannot be bypassed that way; a reviewer can
still override it with an admin merge, which is worth raising in the retro.

## Troubleshooting

### "Pre-push hook installed but doesn't fire on push"

Check that `.git/hooks/pre-push` is executable:
```bash
ls -la .git/hooks/pre-push
chmod +x .git/hooks/pre-push   # if not -rwxr-xr-x
```

### "warning: cannot tell which branch of origin work lands on"

The clone has no `origin/HEAD` and neither `origin/main` nor `origin/master`.
Run `git remote set-head origin --auto`, or pass `--target` to
`renumber_collisions.py`.

### "renumber_collisions says 'No collisions detected' but PR shows conflict"

**First check where the conflict actually is.** If it sits inside the
`evidence[]` list of an item that exists on both branches, this is not an ID
collision and "No collisions detected" is the correct answer — resolve by
union, see [evidence[] merge conflicts on an existing
item](#evidence-merge-conflicts-on-an-existing-item). If it is only
`id_counters.yaml`, take the higher value.

### "I want to use a branch other than main as integration target"

```bash
python3 .edpa/engine/scripts/renumber_collisions.py --apply --target develop
```

The pre-push hook uses `origin/HEAD` — if the remote's default branch is
`develop`, it is picked up automatically (`git remote show origin | grep "HEAD branch"`;
fix with `git remote set-head origin --auto`).

### "Counter file `id_counters.yaml` is missing or behind the item files" (local authority)

```bash
python3 .edpa/engine/scripts/id_counter.py doctor --rebuild
```

Re-seeds each counter from the item files. It never lowers one — a counter
above the files means the highest item was deleted, and its number must not be
handed out again.

### "The ledger looks wrong / I want to start over locally" (remote authority)

```bash
python3 .edpa/engine/scripts/id_counter.py status --refresh   # what the remote says
python3 .edpa/engine/scripts/id_counter.py doctor             # what does not match
python3 .edpa/engine/scripts/id_counter.py doctor --forget    # drop the local cache
```

## Related

- [ADR-014 — remote-coordinated identity](v2/decisions.md#adr-014-remote-coordinated-identity--id-ledger-na-git-refu)
- [Methodology — EDPA architecture overview](methodology.md)
- [`/edpa:setup` skill — installs hooks](../plugin/skills/setup/SKILL.md)
- [`/edpa:add` skill — allocates IDs](../plugin/skills/add/SKILL.md)
- [Hermetic E2E: cut-over to the ledger](../tests/e2e_collision/scenario_b_ledger.sh)
- [E2E against GitHub: collision + renumber under the local authority](../tests/e2e_collision/scenario_a.sh)
