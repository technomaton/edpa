# The ID ledger — how ticket IDs are reserved on the git remote

Technical reference for the remote ID authority (ADR-014). For the
operational side — switching a project over, error messages, recovery —
see [dev-collisions.md](dev-collisions.md); for a one-page team hand-out
(Czech) see [id-ledger-prechod.md](id-ledger-prechod.md).

## The idea

Numbers are unique when one place hands them out. Before 2.23.0 every
working tree had its own counter file and knew nothing about the others,
so two worktrees, two clones or two people got the same `S-285`. The
ledger makes the git remote the team already pushes to that one place —
like a ticket dispenser at an office counter. No forge API, no `gh`:
only `git fetch` and `git push`, so it works on any git server.

## What it is built on in git

Git has two layers:

- **objects** — commits, trees, file contents, each named by its hash and
  immutable;
- **refs** — named pointers to a commit. A ref is a name and one hash.

A branch is the ref `refs/heads/main`, a tag is `refs/tags/v2.23.0`,
GitHub keeps `refs/pull/94/head` for a pull request. Names under `refs/`
form a tree and git allows any others.

`refs/edpa/ids` is a ref of exactly that kind, only outside
`refs/heads/`. Consequences:

- `git clone` / `git pull` do not fetch it on their own (they take
  branches and tags);
- it is not listed among branches in the forge UI;
- branch rules and CI triggers do not apply to it.

Git itself stores data in such refs (`refs/notes/`), and so do Gerrit
and git-bug.

## What the ref holds

The ref points at the newest commit of a chain. Every commit has

- a **parent** — the previous reservation;
- a **tree with one file**, `counters.yaml`:

  ```yaml
  schema: 1
  counters:        # highest number handed out, per type
    Defect: 93
    Story: 290
  floors:          # highest number that may exist WITHOUT a reservation
    Defect: 92     # record: items older than the ledger, plus the
    Story: 289     # optional headroom left at cut-over
  ```

- a **message** — the audit record of the reservation:

  ```
  alloc S-290: Website (CZ/EN): describe the remote ID authority

  EDPA-Id: S-290
  EDPA-Type: Story
  EDPA-Title: Website (CZ/EN): describe the remote ID authority
  EDPA-Parent: F-129
  EDPA-Branch: main
  EDPA-Created-At: 2026-10-08T07:52:11Z
  EDPA-Nonce: 5f0c…
  ```

It is ordinary git history without any of your code:

```bash
git fetch origin refs/edpa/ids
git log FETCH_HEAD --format='%s  [%an, %ar]'
git show FETCH_HEAD:counters.yaml
```

## One reservation, step by step

`/edpa:add Story "Auth"` → `id_counter.next_id` → `_id_ledger.reserve`:

1. **Read.** Fetch the tip of `refs/edpa/ids` into a private temporary
   ref; read `counters.yaml` → `Story: 290`.
2. **Build.** Create the next commit with plumbing commands — no working
   tree, no index, your checkout is untouched:

   ```bash
   git hash-object -w --stdin          # counters.yaml with Story: 291 → blob
   git mktree                          # tree with that one file
   git commit-tree <tree> -p <tip>     # commit, message = audit record
   ```

3. **Push with a condition.**

   ```bash
   git push --no-verify --porcelain \
     --force-with-lease=refs/edpa/ids:<tip read in step 1> \
     origin <new commit>:refs/edpa/ids
   ```

4. **The server decides.** Accepted → `S-291` is yours. Rejected because
   the ref moved → somebody was faster; go back to step 1 and try the
   next number (bounded retries with jitter).
5. **Only now** the item file is written and committed on your branch.

## Where atomicity comes from

From the git push protocol. For every ref the client sends a triple:

```
<old hash>  <new hash>  refs/edpa/ids
```

The server locks the ref, checks that it currently holds `<old hash>`,
and only then writes the new one — a compare-and-swap. It is the same
mechanism that makes a plain `git push` to `main` fail when someone
pushed before you. `--force-with-lease=<ref>:<hash>` states the expected
old value explicitly; with an empty value after the colon it means
"only if the ref does not exist yet", which is how the ledger is created.

Two rejections can be observed:

- `[rejected] (stale info)` — the client saw at connection time that the
  ref is elsewhere;
- `[remote rejected] (incorrect old value provided)` — two clients got
  past that at once and the server's ref lock decided.

The outcome is never read from such text. After any push that is not a
clean success the client re-reads the remote: the ref contains my commit
→ reserved (even if the acknowledgement was lost in a timeout); the ref
moved without it → lost the race, retry; the ref did not move → the
server refuses this environment (permissions), fail.

Two details that matter:

- **Nonce.** Two worktrees of one person can build a byte-identical
  commit (same tree, parent, author, second, text). Git would answer the
  second push "up to date" and both would own the number. Every message
  therefore carries a random `EDPA-Nonce`, and "up to date" is never
  treated as success.
- **`--no-verify`** on this one push: projects run their test suite in
  `pre-push`, and this push carries one metadata commit, never code.

## Why a hand-written ticket cannot slip in

The dispenser alone would not help if a ticket could be written by hand
with an invented number. The hooks (`validate_ids.py`) check every *new*
item:

| Number | Requirement |
|---|---|
| at or below the type's `floor` | none — the item predates the ledger |
| above the `floor` | a reservation record for that ID must exist, and its `EDPA-Created-At` must equal the item's `created_at` |

"Number ≤ highest reserved" would not be enough: an ID minted by an
outdated plugin passes that whenever someone holds an unmerged
reservation above it. Records of blocks reserved ahead carry no
`created_at` and accept any item.

pre-commit works from the local cache (one refresh if a record is
missing; a warning, not a block, when offline). pre-push and the CI
check verify online — that is what catches `--no-verify` commits.

## Local state of a clone

| Where | What |
|---|---|
| `refs/edpa/cache/ids` | newest ledger state this clone knows; only ever moves forward |
| git config `edpa.idLedgerRemote` / `edpa.idLedgerRef` | where this clone last reached the ledger |
| `<git common dir>/edpa/` | lock, high-water mark, pool of numbers reserved ahead |

All of it lives in the shared `.git`, so **every worktree of a clone
sees the same state** — and nothing appears in a checkout.

## Branches, worktrees, clones, agents

- **Branches:** the number is reserved on the remote, not on a branch.
  Whatever branch you are on, the item file is committed there; two
  branches cannot get the same ID.
- **Worktrees of one clone:** share the cache, the lock and the mode.
  They switch together, including ones cut before the opt-in commit.
- **Other clones, other people:** coordinated by the server.
- **Agent sessions:** like a person, provided they may push to the
  repository. A sandbox restricted to its own branch cannot reserve and
  says so.

What stays as before: the *content* of a ticket is visible to other
branches only after merge. A Feature created in one worktree cannot be
a parent from another until it is on the integration branch.

## Which mode applies (`id_counter.resolve_authority`)

1. `EDPA_ID_AUTHORITY=local|remote` — override for one command.
2. `ids.authority` in this checkout's `.edpa/config/edpa.yaml`.
3. `auto` (default): `remote` once this clone has seen the ledger, or
   once the integration branch on the remote opted in (as of the last
   fetch); otherwise `local`.

Step 3 is why a cut-over does not need every branch to merge the opt-in
commit first.

## Failure behaviour

| Situation | Behaviour |
|---|---|
| No network | no ID, nothing written. Never a guessed number — use-then-register is how two ID series start. Offline work: `id_counter.py reserve --type Story --count 5` beforehand |
| Ledger ref deleted or rewound on the server | every clone has the chain cached and the counters are maxima, so the next reservation from any clone that remembers more restores it |
| Ledger force-pushed to something unrelated | both histories are merged, per-type maximum |
| Process dies between reservation and file write | the number is burned; a gap in the sequence is harmless |
| A stray file like `S-9999.md` in one checkout | refused (it would lift everyone's sequence); adopt on purpose with `id_counter.py doctor --raise` |
| Lost race | automatic retry, about 2 s each |

## One ref, not one per type

A ref per type (`refs/edpa/story/ids`, …) would let a Story and a Defect
reserved in the same second avoid one retry. It was not done because:

- the gain is small — a retry costs about 2 s and needs a same-instant
  collision; under a stress of 16 concurrent processes the average was
  1.6 attempts per reservation;
- the bottleneck is the network round trip (reservations from one clone
  queue up regardless of type), which sharding does not shorten;
- seven refs mean seven reads for hooks and status, a non-atomic
  bootstrap, seven audit logs instead of one timeline, and per-type
  self-healing.

Revisit if `other writers kept winning` errors appear in practice. The
file carries `schema: 1`, so a later split does not change ticket IDs.

## Measured

- GitHub: push to `refs/edpa/*` accepted; about 2.4 s per reservation;
  24 concurrent reservations from two clones, no duplicate.
- Local bare repository: 2 × 128 concurrent reservations from 3 clones
  and 8 worktrees, contiguous, no duplicate.
- Not verified: forges other than GitHub, Windows.

## Code

| File | Role |
|---|---|
| `plugin/edpa/scripts/_id_ledger.py` | the protocol (this document) |
| `plugin/edpa/scripts/id_counter.py` | mode resolution, per-clone state, CLI (`status`, `init-remote`, `next`, `reserve`, `doctor`) |
| `plugin/edpa/scripts/validate_ids.py` | hooks: reservation check, same-ID-different-item check |
| `plugin/edpa/scripts/renumber_collisions.py` | repair of pre-ledger collisions |
| `tests/test_id_ledger.py`, `tests/e2e_collision/scenario_b_ledger.sh` | hermetic tests against a bare repository |
