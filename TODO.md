# EDPA — TODO

Forward-looking improvement backlog. Current shipped state: v1.3.0-beta.
Each entry has a target version, motivation, and rough effort estimate.

Items are roughly ordered by priority within each version. Move an entry
to CHANGELOG.md (`## Unreleased`) when picked up; delete it from here when
shipped.

---

## v1.4 — MCP & developer experience polish

### Skill-first E2E test plan — execute (P0, plan authored)

**Plan exists** at `docs/E2E-SKILLS-TEST-PLAN.md` (829 lines, 13
phases mirroring the script-level plan). Open item: actually run it
end-to-end inside a real Claude Code session and record the
walkthrough.

The kashealth onboarding (scheduled 2026-05-06) is the first natural
dogfood — run kashealth setup *through* this plan, not around it.
Phase 13 of the plan is reserved for capturing that run as a worked
example. Findings (skill prompts that read awkwardly, MCP tool calls
that fail, fallbacks the assistant takes when it shouldn't) feed back
as v1.4 fixes.

Why P0: customers experience EDPA through `/edpa:*` skills + MCP, not
by invoking `engine.py` / `sync.py` / `project_setup.py` directly.
The script-level plan keeps backend correctness; this plan keeps the
product surface honest. Both must pass for a release to be
production-ready.

**Acceptance:** complete one skill-driven run against the
`technomaton/edpa-e2e-test` sandbox, fill the ☐ checkboxes in the
plan's acceptance section; complete kashealth onboarding through
the plan and record it under § 13.5 as the first customer
walk-through.

### MCP integration tests in pytest (~ 50 lines)

Today the JSON-RPC stdio roundtrip is verified ad-hoc by spawning a
subprocess and feeding it `initialize` / `tools/list` / `tools/call`
manually. Make that a real pytest case so CI catches a regression where
e.g. the `Server(name, version=…)` constructor signature changes upstream
or the launcher entry point breaks.

**Acceptance:** `tests/test_mcp_integration.py` runs by default
(no e2e marker), spawns `python3 plugin/edpa/scripts/mcp_server.py`,
sends initialize → tools/list → tools/call edpa_status → tools/call
edpa_item("../etc/passwd"), asserts on stderr log lines. Skip on
Windows or when the `mcp` package is missing.

### ~~Resource caching with mtime invalidation~~ — done in `838e372`

Bounded LRU on `mcp_server.load_yaml`, keyed by `(path,
st_mtime_ns)`, capped at 64 entries via `OrderedDict`. Measured 50×
speedup on a 100-item backlog (28.17 ms cold → 0.56 ms warm). 6
tests pin the cache contract (hit/miss, mtime invalidation,
disappeared-file recovery, bounded eviction, LRU recency, handler
benefit). Filed in `## Unreleased`. Removing this entry next pickup.

(Note: `read_resource` for `edpa://config` / `edpa://people` /
`edpa://results/...` still calls `path.read_text()` directly and
does not benefit from this cache. Could extend caching there too if
those endpoints become hot — not measured today.)

### ~~Live "first 5 minutes" tutorial in README~~ — done

`README.md` now opens with a guided walkthrough: install → people
edit → toy iteration → close → reports, end-to-end in roughly five
minutes against zero pre-existing GitHub state. Verified live: a
fresh `/tmp` directory followed copy-paste from the README produces
exactly the output the README promises (invariants pass, 40h Alice,
80h Bob, 120h team total).

### `sync add-iteration <ID>` subcommand (~ 80 lines)

Right now adding a new iteration YAML locally doesn't propagate the
`Iteration` field option to the GitHub Project. The user has to either
re-run `project_setup.py` (heavy) or manually create the option in the
GH UI. Add a small subcommand that uses `updateProjectV2Field` with the
merged option list.

**Acceptance:** create `.edpa/iterations/PI-2026-1.5.yaml`, run
`sync add-iteration PI-2026-1.5`, then `sync push` of an item with
`iteration: PI-2026-1.5` succeeds without manual GH edits.

---

## v1.6.4 — hierarchy + views auto-creation (real-world feedback 2026-05-06)

### `/edpa:sync push` must create issues as sub-issues, not flat (~ 50 lines)

Live testing surfaced that `sync.py push` creates GitHub Issues
without linking them as sub-issues of their `parent:` field. The
infrastructure exists — `project_setup.py:469-517` STEP 8 already
calls GraphQL `addSubIssue` correctly during initial setup. But the
ongoing push path only writes `parent:` into the issue body and
returns. Every Story/Feature/Epic added after initial setup ends
up as a top-level issue.

**Acceptance:**
- After `sync.py push` completes, every newly-created issue with a
  non-null `parent:` is linked as a sub-issue of that parent on
  GitHub. Existing project_setup STEP 8 mutation logic should be
  factored out into a reusable helper called by both initial setup
  and ongoing push.
- `/edpa:sync` skill instruction adds: "Always preserve hierarchy.
  Never produce a flat issue list."

### `/edpa:setup` must call create_project_views.py automatically (~ 10 lines)

`project_setup.py:584` *suggests* `python .claude/edpa/scripts/
create_project_views.py` as a manual next step. Customers don't
read suggestions — the views never get created and the GitHub
Project shows only the default Table view.

**Acceptance:**
- New STEP 9 (or appended to STEP 7) runs `create_project_views.py`
  with the project number resolved from STEP 2.
- Wizard summary at the end prints the view URLs so the maintainer
  can verify them in one click.
- Failure to create views is non-fatal — emit a warning and continue
  (the rest of setup is still useful).

### `/edpa:setup` skill template forbids flat issue lists (~ 5 lines)

Update `plugin/skills/edpa-setup/SKILL.md` STEP 7 / "Output
confirmation" section: change the next-step suggestion from
> "Create work items using GitHub Issues with the hierarchy ..."

to an explicit instruction earlier in the flow:
> "Items in `.edpa/backlog/` MUST link to their parent via the
> `parent:` field. Skill must refuse to create top-level issues
> for non-Initiative items. /edpa:sync push will then enforce
> the parent-child sub-issue relationship on GitHub."

## v1.6.1 — collaborators-sync follow-ups

Surfaced by the live PR run on technomaton/edpa#20 (2026-05-06).

### ~~Workflow token scope — PAT fallback~~ — done in v1.6.2

`members: read` does NOT exist as a workflow permission (GitHub
rejects the file with HTTP 422 — surfaced by a workflow_dispatch
attempt right after v1.6.1 shipped, before any user could hit it).
The actual fix landed in v1.6.2: both copies of the workflow read
`GH_TOKEN` from `${{ secrets.COLLAB_SYNC_TOKEN || secrets.GITHUB_TOKEN }}`.
The PAT is optional — when unset the workflow falls back to the
default token and sees direct collaborators only. To cover org
members + pending invitations, set `COLLAB_SYNC_TOKEN` (PAT with
`repo` + `read:org` scopes) on the repo.

### ~~YAML round-trip preserves comments~~ — done in v1.6.1

Switched `sync_collaborators` to `ruamel.yaml` so people.yaml
comments survive the read-modify-write cycle.

### Auto-merge stubs onto existing entries (~ 50 lines, optional)

Both `martinturyna` and `mtury` are likely the same person
(`turyna` in the existing roster). The current logic doesn't
attempt a name-match merge — it appends two new stubs and leaves
the maintainer to delete them and set `github:` on the existing
entry instead.

This is intentional for v1.6.0 (explicit, predictable, no
false-positive merges). Revisit for v1.7 if the manual merge
becomes painful in practice — heuristic could be: if a new
collaborator's `name` (from `gh api users/{login}`) matches an
existing person's `name` ≥ 70 % via fuzzy match, surface in the
PR body with a "merge candidate" note rather than auto-applying.

## v1.5 — Operational tooling

### Skill side-effect testing via `claude -p` (P1, ~150 lines)

Today: skill flows are validated only by the live walkthrough during
release prep (and by manual kashealth onboarding). Layer 3 of the
strategy pyramid in `docs/E2E-SKILLS-TEST-PLAN.md` Příloha D is
unfilled — there is no automation that catches a regression where
`/edpa:setup` stops persisting `issue_map.yaml`, or where
`/edpa:sync push` silently dispatches to `--mock` mode.

Build it as **outcome assertions over `claude -p` subprocess**:

  1. New `tests/integration/` directory (kept separate from `tests/`
     so `pytest tests/` stays fast).
  2. Helper `claude_run(prompt, cwd, env)` that wraps
     `subprocess.run(["claude", "-p", prompt, "--no-interactive"])`
     with reasonable defaults and a timeout.
  3. Per-skill test module (`test_setup_skill.py`,
     `test_sync_skill.py`, `test_close_iteration_skill.py`) that
     drives the skill in a tmp workspace and asserts on:
       - filesystem state (`.edpa/config/issue_map.yaml` exists,
         expected keys present)
       - GitHub state (`gh project view N` returns expected fields)
       - MCP log lines (grep `INFO call_tool name=…` from
         `EDPA_LOG_FILE`) — proves the skill dispatched to MCP and
         not to `Bash + grep`
  4. Marker `@pytest.mark.skill_integration` so CI can run them
     opt-in (they spawn real Claude Code, real GitHub API, take
     time).
  5. CI workflow that runs them nightly against the sandbox repo,
     posts a status check on the latest release tag.

The kashealth onboarding (Phase 13 of the skills E2E plan) gives us
the first reference recordings — capture the actual prompts and
outcomes there, then write the assertions to match.

Why outcome-based, not transcript-based: LLM nondeterminism makes
exact-match brittle (the skill may ask "Project name?" one week and
"What's the project name?" the next). Asserting on filesystem +
GitHub + log effects is stable; asserting on stdout text is not.

**Acceptance:** at least three skill tests (`setup`, `sync push`,
`close-iteration`) pass against the sandbox; nightly CI runs them;
a deliberate regression (e.g. comment out the `issue_map.yaml`
write in `project_setup.py`) fails the right test with a clear
diff. Plus, layer 3 in the strategy pyramid in Příloha D moves from
❌ to ✅.

See `docs/E2E-SKILLS-TEST-PLAN.md` Příloha D for the full strategy
breakdown and the four observable surfaces (side-effects, prompts,
MCP dispatch, regression).

### Live integration smoke as a CI workflow (~ 1 file)

Add `.github/workflows/integration.yml` that runs the e2e suite against
`technomaton/edpa-e2e-test` on a schedule (nightly) and on release tags.
Today these tests are local-only via `EDPA_E2E_REPO`; the sandbox would
benefit from a known-good signal independent of the developer's machine.

**Acceptance:** workflow runs nightly, posts a status check on the latest
release tag.

### ~~Release pipeline as CI workflow~~ — done in `6f1c6e1`

`.github/workflows/release.yml` triggers on `v*` tag push and on
manual `workflow_dispatch` for back-fill. Builds `edpa-plugin.tar.gz`
with `__pycache__`/`*.pyc`/`.DS_Store` excluded, extracts the matching
CHANGELOG section into release notes, auto-detects prerelease via
`-alpha`/`-beta`/`-rc` suffix, then `gh release create` (or `gh
release upload --clobber` on existing tags).

Maintainer flow is now: bump versions, update CHANGELOG, commit
`release: vX.Y.Z`, then `git tag vX.Y.Z && git push --tags`.

Verified via `workflow_dispatch` against v1.5.0-beta on 2026-05-06
(run #25443979871, success): re-built asset has different gzip
metadata (BSD tar vs GNU tar, different file ordering) but the 53
files inside are byte-identical to the manual build — sorted-content
sha256 `73b336ff723a48433148841d4f348e486e7624fb4619c1e9e0ce49d3b3e5cf5d`
on both. install.sh extraction is indistinguishable.

### Rate limiting / DoS guard for MCP (~ 40 lines)

Less relevant for stdio (single client), but if we ever expose MCP over
HTTP/SSE the server needs a request budget. Track requests per minute
per client; refuse with `ERROR: rate limit exceeded` past threshold.
Pure read-only tool list means low risk today, but plan now while the
surface is small.

**Acceptance:** loop of 1000 calls in 1s gets throttled; normal usage
unaffected.

### Engine `--explain <person>` (~ 60 lines)

`engine.py` produces JSON results, but extracting "why does Alice have
40h on S-200?" requires reading the audit trail by hand. Add a
human-readable explanation mode that walks one person's allocation step
by step (item → role → CW source → ratio → hours), citing the
heuristic source for each CW value.

**Acceptance:** `engine --iteration PI-… --explain alice` prints a
narrative reproduction of the math, suitable for sharing with a
non-technical PM.

---

## v2.0 — MCP write tools

### `--mode write` permission model

Currently the MCP server is read-only by design. Some assistants would
benefit from `edpa_create_item`, `edpa_update_status`, `edpa_close_iteration`
tools — but exposing writes through MCP needs a real permission model:

- per-tool allowlist (explicit opt-in)
- audit log of all writes (who, what, when)
- dry-run mode default
- session token / signed claims for the writing client

This is a v2 feature because it changes the trust boundary materially.
Don't ship without a security review.

**Acceptance:** spec doc + threat model exist before any tool lands.

### MCP HTTP transport

Stdio is single-client. Multi-tenant scenarios (e.g. team-wide MCP
deployment) need HTTP/SSE. Wait until there's a real use case; don't
build for hypothetical demand.

---

## Cross-cutting / undated

### `tests/test_mcp_server.py` — add resource-listing tests

`list_resources` enumerates `edpa://config`, `edpa://people`, and one
entry per closed iteration's `edpa_results.json`. Currently only
`read_resource` is tested. Add tests that verify `list_resources`
returns the right URIs on a fresh fixture and updates when a new
iteration's results land.

### Document `EDPA_ROOT` env var in install.sh output

After install, the printed "Next steps" doesn't mention `EDPA_ROOT`.
Useful when a user clones the EDPA repo itself for hacking and wants
their MCP client to read the demo `.edpa/` data; or when a project
keeps `.edpa/` in a non-standard location.

### Audit `engine.py` for the same hardening pass MCP got

`mcp_server.py` got: stderr logging, version-aware identity, regex
input validation, crash-safe dispatch, `try`/`except` specificity.
`engine.py` is older and predates that pass — likely has bare except,
no structured logging, possibly unsafe path joins in custom backlog
locations. Run the same audit; backport what fits.

### Surface Vercel install.sh CDN cache TTL

`install.sh` is served via Vercel from `main`. After a fix-and-push,
how fast does `curl install.sh` see the new bytes? Document the
expected TTL (or set explicit `cache-control` on the deployment) so
hot-fix turnaround time is predictable.

### Make `install.sh` impossible to drift between repo root and web/public

Vercel deploys `https://edpa.technomaton.com/install.sh` from
`web/public/install.sh`, while every dev edits `./install.sh` at the
repo root and forgets the web copy exists. The two had drifted four
months apart before the v1.3 audit caught it. Three options:

1. **Symlink** `web/public/install.sh -> ../../install.sh` —
   simplest, works if Vercel build dereferences symlinks (verify).
2. **Vercel rewrite** for `/install.sh` to serve the repo-root file
   directly via a function or static rewrite — needs `vercel.json`
   tweak.
3. **Build step** in `web/` that copies `../install.sh` into
   `public/install.sh` on every deploy — robust, no Vercel magic.

Pick whichever survives a `vercel deploy` reliably. Add a smoke
check to `tests/test_consistency.py` that asserts byte-equality
between the two paths so a future drift fails CI.
