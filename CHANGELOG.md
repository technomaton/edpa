# Changelog

## 2.2.0 — 2026-06-01 — Create PI: edpa_pi_create tool + /edpa:create-pi command & skill

Adds a first-class way to create the **PI-level metadata file**
`.edpa/iterations/<PI-YYYY-N>.yaml` (top-level `pi:` block). Previously only
per-iteration files had tooling (`edpa_iteration_create`); the PI parent had to
be hand-written, which was error-prone — most notably the loader globs `*.yaml`
only, so a `PI-2026-1.yml` (short extension) is silently ignored and the PI
metadata (status, `pi_iterations`, dates) silently falls back to values derived
from the child iterations.

Built **script-first**, matching the rest of EDPA: behavior lives in one script
and every interface delegates to it.

### feat(pi): `create_pi.py` — single source of behavior
New `plugin/edpa/scripts/create_pi.py` with an importable `create_pi()` core
(validates a PI-level id, refuses to overwrite, atomic write of the `pi:` block)
plus a CLI (`--start/--end/--weeks/--iterations/--status/--no-commit`) that runs
continuity validation and auto-commits. Self-contained — no dependency on the
MCP layer, so it runs as a plain CLI and is importable by the server.

### feat(mcp): `edpa_pi_create` tool
Thin delegate that imports `create_pi()` — no business logic in the handler
(write only; no commit, like the other MCP write tools). Inputs: `id` (required,
PI-level), `start_date`, `end_date`, `iteration_weeks`, `pi_iterations`,
`status`. Rejects an iteration-level id (`PI-YYYY-N.M`) and duplicates. The tool
surface is now 7 read + 8 write.

### feat(skill+command): `/edpa:create-pi` and `edpa:create-pi`
Both shell out to `create_pi.py` (like `/edpa:capacity` → `capacity_override.py`).
The command takes explicit args; the skill auto-triggers on "create / start a
PI". Neither scaffolds the child iterations — those are added with
`edpa_iteration_create` (`<PI>.1 … .N`, last `type: IP`).

### tests + docs
New `tests/test_create_pi.py` (core + CLI + loader round-trip); `edpa_pi_create`
added to the MCP write-tool and idempotency suites and the advertised-tool
assertions. `docs/mcp.md` gains a write-tools note (and the stale "read-only"
claim is corrected); `docs/playbook.md` §1.5, `docs/RUNBOOK.md`, and
`plugin/README.md` list the new tool / command / skill.

## 2.1.9 — 2026-06-01 — Windows onboarding fixes (filelock, UTF-8 console + file I/O)

`/edpa:edpa-setup` crashed on a fresh Windows box, surfaced by colleagues running
2.1.8. Two reported failures, plus two more that would have hit immediately after
(masked by the first crash). All four are fixed; the engine now behaves identically
on Linux, macOS, and Windows.

### fix(setup): bootstrap no longer crashes on `ModuleNotFoundError: filelock`
`id_counter.py` imported `filelock` unconditionally, but the SessionStart dep hook
(`install_deps.sh`) skipped `pip install` whenever its cheap import probe passed —
and the probe never listed `filelock`. On a machine that already had PyYAML/mcp/
openpyxl system-wide, the hook marked deps "installed" (and wrote its marker) while
`filelock` was absent, so the bootstrap died. Two-part fix:
- The probe now includes `filelock`. A new `test_install_deps_probe.py` cross-checks
  the probe against `requirements.txt` so this drift can't recur.
- `id_counter.py` falls back to a new pure-stdlib lock (`_fallback_lock.py` —
  `O_CREAT|O_EXCL` with a stale-lock sweep) when `filelock` can't be imported, so ID
  allocation keeps its cross-process mutual-exclusion contract even without the
  package. (Existing installs ride the fallback until `requirements.txt` next changes
  and busts the dep-marker — fully functional in the meantime.)

### fix(cli): UTF-8 console output — glyphs no longer crash legacy Windows consoles
25 CLI entry points print progress glyphs (`✓ ✗ → ·`); `print("✓")` raises
`UnicodeEncodeError` on a cp1250/cp1252 console and aborts the command — the reported
`/edpa:edpa-setup` failure. A shared `_console.py` reconfigures stdout/stderr to UTF-8
(`errors="replace"`, idempotent, best-effort); each entry point opts in with a guarded
`import _console` (`try/except ImportError`, so a partially-vendored engine degrades to
plain output rather than crashing). `mcp_server.py` is intentionally excluded — its
glyphs live in JSON-RPC tool descriptions the MCP SDK already frames as UTF-8.

### fix(io): all text-mode file I/O pins `encoding="utf-8"`
`open()`/`read_text()`/`write_text()`/`os.fdopen()` defaulted to the locale encoding —
cp1250 on a Czech/German Windows box. After the console fix the next crash would have
been `_stamp_methodology` reading the freshly seeded UTF-8 `edpa.yaml` (`←`, `×`) →
`UnicodeDecodeError`; writing an item with diacritics in its title would corrupt or
crash too. All 28 text-mode handles now pin UTF-8 (`os.open` raw fds and binary modes
excluded). A new `test_encoding_hygiene.py` AST guard fails CI if any text handle drops
the kwarg.

### Tests
- New: `test_install_deps_probe.py`, `test_fallback_lock.py`, `test_console.py`,
  `test_encoding_hygiene.py`. Full suite 565 → 577 (+12); 0 failures.

## 2.1.8 — 2026-05-31 — Fresh-install onboarding fixes (engine vendoring on /edpa:setup) + V1→V2 docs/website sweep

Three fresh-install friction points on the Claude-Code-only path (install the
plugin, run `/edpa:setup` on a bare repo), found via a new deterministic E2E
onboarding harness (`tests/onboarding/`).

### fix(setup): `/edpa:setup` now vendors the engine into `.edpa/engine/`
`project_setup.py` vendors `scripts`+`schemas`+`templates`+`rules`+`VERSION` as
step 1 of `main()` (mirrors `install.sh`). The Claude Code path had silently lost
vendoring when the engine moved from `.claude/edpa/` to `.edpa/engine/` (only
`install.sh` was rewired), so `/edpa:setup` produced a project referencing a
`.edpa/engine/scripts/` that never existed — the `--with-ci` workflow it installs
plus the documented CLI broke, masked by the MCP server running from the plugin
cache. Rules are vendored from `plugin/rules` (not `plugin/edpa/rules`), fixing a
parallel `--with-rules` failure.

### fix(install): V2 local-first "Next steps" + stamped methodology version
`install.sh` no longer prints stale V1 guidance ("provision GitHub Project …
push to GitHub Projects") or the removed `--org/--repo/--project-title` args; it
now shows the correct `--with-ci/--with-hooks/--with-rules` flow with `filelock`
in the dependency hint. Both `install.sh` and `project_setup.py` stamp
`governance.methodology` in a freshly seeded `edpa.yaml` to the live plugin
version (was frozen at the template's `EDPA 1.22.1`).

### Tests
- New `tests/onboarding/` harness (pexpect + tmux) + `test_project_setup_vendor.py`
  + `test_install_sh_hygiene.py`. Full suite 553 → 564 (+11); 0 failures.

### docs: V1→V2 sweep of user-facing docs + website (PR #52)
Swept the documentation and marketing site of the removed V1 GitHub-Project flow
(`project_setup.py --org/--repo/--project-title`, org Issue Types, `project_views.py`,
bidirectional `sync.py`, `issue_map.yaml`, `.claude/edpa/` paths, `project.yaml`/
`heuristics.yaml`, `.yaml` backlog). Everything now reads V2 local-first: `/edpa:setup`
vendors the engine, items are local `.edpa/backlog/**/*.md` via `backlog.py add`, the
only optional GitHub integration is the `--with-ci` contribution-sync workflow, and the
calibration loop is `calibrate_signals.py` (Monte Carlo). Covers **31 files** — repo docs
(`RUNBOOK`, `playbook`, `E2E-TEST-PLAN`, `E2E-SKILLS-TEST-PLAN`, `github-setup`,
`edpa-token-setup`, `kashealth-pilot/*`, `methodology`, `auto-calibration`, `mcp`,
`org-lookup`) + the Astro website (playbook/methodology/guide/setup CZ+EN, tutorial, docs
pages, landing + pitch decks reframed to "EDPA needs only git, GitHub optional").
`astro build` green (28 pages). Historical design records (`docs/v2/*`, `docs/proposals/*`)
left as-is.

## 2.1.7 — 2026-05-31 — E2E findings: cross-layer fixes + /contribute @id + /edpa:capacity

Fixes and conveniences surfaced by a full real-GitHub end-to-end re-validation
(2 PIs × 5 iterations, 24 PRs, 24/24 real CI runs, 560h derived, all invariants
green). See `docs/v2/e2e-real-github-run-2026-05-31.md`.

### fix(engine): iteration close sets the top-level lifecycle status key
`edpa_iteration_close` wrote only the nested `iteration.status`; `pi_close.py`,
the board lifecycle view, and the e2e verifier read the top-level `status`. It
now sets both, so an iteration closed via the MCP tool is seen as closed by all
consumers.

### fix(backlog): `backlog.py add` is ANSI-safe for non-TTY output
`color()`/`bold()` honor `NO_COLOR` and non-TTY (piped/captured) output, so the
allocated item ID parsed by tooling/CI no longer contains escape codes.

### feat(reports): iteration/PI story-point rollup derived from item `js`
New `_sp_rollup.iteration_sp` derives `planned_sp`/`delivered_sp` from
Story/Defect `js`; `velocity.py` and `pi_close.py` fall back to it. Velocity and
PI predictability now populate (were 0 / None).

### feat(contribute): `/contribute @<id>` targets a specific contract (R-2)
`detect_contributors.load_people_map` maps each person id to itself (id wins over
github/email/name collisions), so multi-contract people who share a GitHub handle
are addressable by id. `aggregate_signals` warns on unknown tokens (a typo no
longer silently earns 0h). Docs: `docs/contribute-directive.md`.

### feat(commands): new `/edpa:capacity` command + capacity-override docs
First-class `/edpa:capacity` (wraps `capacity_override.py`: `--list`/`--add`/
`--remove`) for per-iteration per-person capacity overrides. New RUNBOOK §3b plus
capacity notes in the web playbook + methodology (CZ + EN).

### docs/chore
- E2E run report (`docs/v2/e2e-real-github-run-2026-05-31.md`) + R-2 attribution
  proposal (`docs/proposals/v2-multi-contract-id-attribution.md`).
- `plugin/README.md` skills/commands tree refreshed to the V2 layout.

### Tests
- Full suite 546 → 553 (+7 regression tests); 0 failures.

## 2.1.6 — 2026-05-30 — Full collision documentation + methodology page section

Documentation release. Following user feedback, expanded the collision
documentation across all developer-facing surfaces. No code changes.

### docs(collisions): expand dev-collisions.md to comprehensive guide

`docs/dev-collisions.md` grew from 108 to ~290 lines with:
- ASCII timeline diagram showing how a collision happens (T+0 → T+5)
- ASCII flow diagram of the four defense layers (cumulative)
- Decision tree — "I got a conflict, what do I do?"
- Recovery flow with annotated comments for each step
- Common collision shapes (single, multi, parent chain, cross-type, cascading)
- Installation section for hooks + CI workflow
- Troubleshooting section (3 common gotchas)
- Bypass disclaimer

### docs(integration): collision section in RUNBOOK + quick-start

- `docs/RUNBOOK.md` — new "## ID collision handling" section with operator
  reference table + setup checklist + recovery commands.
- `docs/quick-start.md` — new "Multi-developer setup" section as part of
  "What's Next?" — covers setup + recovery in ~20 lines, links to full guide.
- `docs/github-setup.md` — fixed outdated claim "IDs are immutable — never
  renumber after creation" (replaced with stable-after-merge framing +
  link to dev-collisions.md).

### docs(plugin): collision section in plugin README + skill docs

- `plugin/README.md` — new "Multi-developer setup" section between
  installation and cross-tool compat. Table of 4 layers + quick setup.
- `plugin/skills/edpa-add/SKILL.md` — new "Parallel ID allocation" section
  explaining what happens when two devs `/edpa:add Story` from same main.
- `plugin/skills/edpa-setup/SKILL.md` — `--with-hooks` description now
  cross-references layer numbers + explicit note that Layer 7 (CI workflow)
  is a separate manual copy step.

### docs(web): methodology page — section 9b on both CZ + EN

- `web/src/pages/methodology.astro` — new section 9b "ID kolize a
  renumbering (multi-developer setup)" with 4-layer table + recovery flow
  + setup commands + link to GitHub guide.
- `web/src/pages/en/methodology.astro` — same as 9b "ID collisions and
  renumbering" in English.
- TOC updated on both pages.

### feat(dashboard): effective capacity bar

`/tmp/edpa-e2e-recovered/dashboard.html` regenerator now computes
**effective capacity** per iteration (sum of capacities of people with
derived > 0) and displays it as a third bar in the per-iteration chart.
Reveals the planning-vs-actual gap explicitly:
- Blue = planning capacity (deklarovaná — always 144h for the E2E test)
- Yellow = effective capacity (only active people)
- Green = derived (signal-based allocation)

Tooltip now shows utilization % (vs both planning and effective) and
"X/Y active people" count. Resolves user feedback that the previous
"Capacity vs Derived" view was confusing when some people were idle.

## 2.1.5 — 2026-05-28 — Collision detection fix + CI workflow + dev docs

Bug fixes + new layer of collision prevention. The previous releases of
`renumber_collisions.py` and `validate_ids.py --pre-push` both compared local
backlog state against the **matching remote branch** instead of the
**integration target** (`origin/main`). This meant that in the standard
feature-branch + PR workflow — once you push your branch — the collision
detector saw no diff (`origin/<your-branch>` matches `HEAD`) and returned
zero collisions, even when your local IDs genuinely clashed with `main`.

The end-to-end test scenario (`tests/e2e_collision/scenario_a.sh`) reproduces
the issue against a real GitHub sandbox: two devs both allocate `S-5` on
parallel feature branches; previously, after Alice's PR merged, Bob's
collision was undetected by the tooling. Post-fix, `renumber_collisions.py`
correctly identifies `S-5` as colliding with `main` and renumbers Bob's to
`S-6`.

### fix(renumber_collisions): compare against integration target, not matching remote branch

- `find_collisions(repo_root, remote, target_branch=None)` — new `target_branch`
  arg. `None` (default) auto-detects the remote's default branch via
  `refs/remotes/<remote>/HEAD`; defaults to `main` if symbolic ref is missing.
- New CLI flag `--target <branch>` — override for Git Flow projects integrating
  to `develop` etc.
- New CLI flag `--check` — CI mode, detects + reports without prompting or
  modifying. Exit 0 if no collisions, exit 1 if collisions found.

### fix(validate_ids --pre-push): same semantics

`cmd_pre_push` now lists upstream items at the integration target tip
(`refs/remotes/<remote>/HEAD`), not at the merge-base. Previously, items
added to `main` after your branch forked were invisible to the check.

### test(renumber): three new unit tests + one regression test

- `test_multi_collision_both_renumbered_sequentially` — two Story collisions
  get sequential IDs (`S-5` + `S-6`), no duplicates.
- `test_parent_chain_renumber_propagates_to_children_only` — `F-3 → F-4`
  updates direct children's `parent:` refs; grandchildren (parent chain via
  another item) untouched.
- `test_three_dev_cascading_collisions` — Dev A merges S-2, Dev B (collision)
  renumbers to S-3 and merges, Dev C (had S-2 AND S-3) faces 2 collisions
  → S-4 + S-5.
- `test_collision_detected_when_on_feature_branch_against_main` — regression
  test for the `--target` fix; would fail with the pre-fix logic.
- `test_collision_target_branch_arg_overrides_default` — verifies explicit
  `--target develop` works for Git Flow projects.

### test(e2e_collision): real GitHub sandbox test

New `tests/e2e_collision/scenario_a.sh` — executable script that creates a
throwaway sandbox repo under `technomaton/`, simulates two devs both creating
`S-5`, walks through the recovery workflow (Alice merges → Bob's PR conflict
→ Bob runs `renumber_collisions.py --apply` → Bob merges main → Bob's PR
mergeable → squash merge), and verifies the final state on main has both
`S-5` and `S-6`. Cleans up GH repo (archive) and `/tmp` sandbox on success.

### feat(workflow): edpa-collision-check.yml CI template

New `plugin/edpa/templates/github-workflows/edpa-collision-check.yml`. Runs
on every PR touching `.edpa/backlog/` or `id_counters.yaml`. Detects
collisions via `renumber_collisions.py --check`; on detection, posts a
comment on the PR with the detected collisions + fix instructions, and
fails the check (so the PR's merge button stays disabled).

### docs(dev-collisions): full developer guide

New `docs/dev-collisions.md` — describes the three defense layers
(pre-commit, pre-push, CI workflow), the manual recovery workflow with
exact commands, common collision shapes (single / multi / parent-chain /
cascading), and the `id_counters.yaml` merge-resolution trick (take max).

## 2.1.4 — 2026-05-27 — V2.1 local-first narrative parity in plugin metadata

Patch release sweeping the last customer-facing texts still describing EDPA
as a GitHub-coupled system with "bidirectional sync" as the headline value
prop. The 2.1.2 cleanup pass fixed the web hero, README, FAQ, and several
docs but missed four customer-facing surfaces:

- `plugin/.claude-plugin/plugin.json` description — visible in Claude Code
  plugin marketplace listings.
- `.claude-plugin/marketplace.json` plugins[] description — visible to
  users running `/plugin marketplace add technomaton/edpa`.
- `plugin/README.md` file tree comment for `sync.py` — readers were not
  signalled that sync is now an optional UI.
- `web/src/pages/en/index.astro` "GitHub-native" feature card — CZ
  equivalent was renamed to "Git-native, GitHub-friendly" in 2.1.2 but
  the EN page was missed.

All four now align with the V2.1 local-first narrative: `.edpa/backlog/`
YAML as source of truth, git as the audit trail, GitHub Projects sync
explicitly optional.

No engine, schema, or behavior changes.

## 2.1.3 — 2026-05-27 — E2E findings + verify scripts parameterized

Patch release applying the 5 actionable findings surfaced by the V2 full
end-to-end test, plus a verification run that exercised every fix against
a fresh GitHub sandbox. The verification itself uncovered 4 more bugs in
the verify + cleanup scripts (stale hard-coded constants from the previous
run); those are fixed in the same release.

No engine math or schema changes. Engine behavior is unchanged; only CLI
surface, close-iteration workflow, fixture, and test-infrastructure tweaks.

### fix(backlog): `backlog add --type` accepts all 7 types

`backlog.py add --type` CLI choices were limited to
`Initiative|Epic|Feature|Story`, while the MCP `edpa_item_create` handler
supported all 7 (the missing 3 being Defect, Event, Risk). Users adding
these types via CLI had to fall back to manual YAML writes + manual
`id_counters.yaml` bumps. The CLI now mirrors MCP's TYPE_DIRS surface.

### fix(close-iteration): Stage 2b (`detect_contributors.py --all-items`) explicitly mandatory

V1.11+ engine reads per-item `contributors[]` blocks for derived-hours
allocation. Without them, all derived hours = 0 with no error — a silent
failure mode. `sync_pr_contributions.py` writes only `evidence[]`;
`contributors[]` must be materialized by `detect_contributors.py
--all-items`. The close-iteration command + skill now mark this as a
REQUIRED Stage 2b (was implicit), with an explicit warning about the
silent-0h failure mode if skipped.

### fix(e2e fixture): Initiative/Epic gate transitions use portfolio ladder

`tests/e2e_v2_full/fixtures/work_plan.yaml` had Initiative/Epic gate
transitions hitting `Validating`, which is a delivery-only enum value
(Feature/Story/Defect). The schema correctly rejected these transitions,
breaking the E2E run. Fixed: portfolio items now use `Implementing` per
the portfolio ladder. Added a header comment with both ladders so future
fixture authors don't repeat the mistake.

### docs(mcp): document single-project scope limitation

The EDPA MCP server resolves `.edpa/` from the calling agent's host
project root (fixed at session start), NOT from the agent's current
working directory. Agents invoking `mcp__plugin_edpa_edpa__*` against
sandbox/temp projects get host-project results. Documented the
limitation + 3 workarounds (call vendored scripts directly, run a
separate Claude session per project, run the MCP server from the
sandbox cwd).

### docs(e2e): Skill-tool subagent gotcha

The `Skill` tool may return doc/instruction text rather than executing.
Subagents working on E2E phases should use direct `python3
.edpa/engine/scripts/*.py` invocations as the fallback. Captured as
limitation #4 in the E2E docs + cross-linked from `09_close_engine_reports.md`.

### test(e2e): hybrid E2E verification run + parameterize verify scripts

Ran the full 2 PI × 5 iter E2E in hybrid mode (PI-1 real CI, PI-2 synthetic)
against `technomaton/edpa-e2e-20260527-181051-2c56a6a0` (now archived).
Verified each fix holds end-to-end:

- 14/14 PRs merged + 14/14 CI workflow runs success
- 10/10 iterations closed with `all_invariants_passed=true` on FIRST
  engine pass (zero `_rev2` snapshots — previous run had 2)
- `backlog.py validate` exits 0 (previously 3 errors)
- All Defect/Event/Risk items created via CLI path (no manual YAML)
- 33 backlog items in expected end-states; 50 per-person timesheets,
  10 XLSX, 10 frozen snapshots

The verification exposed 4 stale-constant bugs in `phases/{10,11,12}_*.py`
+ `99_cleanup.sh` (hard-coded paths from previous run, `EXPECTED_MERGED_PRS=24`
assumed full-real CI, `EXPECTED_COUNTS` predated `3cb8ff1`, wrong YAML key
for iteration lifecycle status). All four scripts are now parameterized via
env vars + `/tmp/edpa-e2e-current-run-tag` fallback + `EDPA_E2E_CI_MODE`-aware
constants (`EXPECTED_MERGED_PRS` returns 24 / 14 / 0 for real / hybrid /
synthetic).

Phase run logs in `tests/e2e_v2_full/phases/01..12_*.md` refreshed with the
hybrid-mode results, timestamps, sandbox SHAs, and script-fix findings.

## 2.1.2 — 2026-05-27 — Docs + web reposition to V2.1 local-first narrative

Patch release that sweeps the customer-facing positioning to match what
V2.0/V2.1 actually do. The engine has been local-first since the
`feat(v2)!: V2 local-first hard cut, GH only via CI` commit, but the
web hero, README, and several docs still described EDPA as a
GitHub-coupled system with "bidirectional sync" as the headline value
prop. No engine behavior changed.

### fix(web): reposition V2.1 narrative — local-first evidence, GH optional

- Hero copy: "GitHub delivery evidence" → "lokální git evidence (commity,
  yaml edits, status přechody)"; "Bidirectional sync mezi GitHub Projects
  a lokálními YAMLy" → soft note that sync is an optional PM/BO UI.
- "Sync: Bidirectional" stat card → "Evidence: Local-first".
- What's-new "GitHub Projects sync" card → "In-flight Story credit (C7.5)".
- Signály z gitu table: added `yaml_edit:*`, `gate_event`, `story_activity`
  rows and a `Zdroj` column distinguishing `local hook` / `engine + git log`
  / `optional CI`.
- Solution layer source: `GitHub Issues + Projects` → `.edpa/backlog/ YAML · Git`.
- "GitHub-native" feature card → "Git-native, GitHub-friendly".
- Test count 127 → 541 (was stale).
- methodology.astro audit pillars + EDPA vs alternatives.
- journey.astro Slide 6 SoT clarification.

### docs: reposition V2.1 narrative — local-first evidence, GH optional

- README.md Key Features bullets (zero-input source, in-flight Story
  credit, sync now "Optional", "Git-native, GitHub-friendly").
- plugin/README.md skills table positioning note + per-row `(optional GH)`.
- docs/faq.md — Toggl comparison, Jira/no-GitHub Q rewritten as
  git-native; evidence detection section rewritten for yaml_edit /
  gate_event / story_activity sources; audit pillar updated.
- docs/methodology.md § 10.3 audit pillar → git-native.
- docs/RUNBOOK.md `/edpa:sync` section + V2.1 note that sync is optional.
- docs/playbook.md § 2.3 + Architektura ASCII diagram (.edpa/ as SoT,
  GH Projects as optional sync); path fix `.claude/edpa → plugin/edpa`.
- docs/quick-start.md — prereqs (gh CLI now conditional), Step 4 reframed
  as optional, Step 6 V2.1 engine signature, template names updated
  (`heuristics → cw_heuristics`, `project → edpa`).
- docs/github-setup.md — V2.1 banner clarifying entire guide is optional;
  path fix `.claude/edpa → plugin/edpa`.
- Removed 6 historical E2E run reports (`E2E-REPORT-2026-05-06*`,
  `-05-07-v1100-beta-full-pilot`, `-05-08-v1100-rc1-real-evidence`)
  — snapshots of one-time test sessions, recoverable from git history.
  Kept the two living docs: `E2E-TEST-PLAN.md`, `E2E-SKILLS-TEST-PLAN.md`.

### docs: standardize on Conventional Commits across all guidance

- `plugin/rules/edpa-work-rules.md` — added explicit "Commit message
  format" section specifying CC + ticket-id scope (`feat(S-42): subject`);
  all examples rewritten to CC; clarified that the commit-msg hook stays
  format-tolerant but CC is the recommended path. Escape prefixes
  (`no-ticket:`, `WIP:`) remain as intentional CC bypass so opt-outs
  stay visible in `git log --oneline`.
- `plugin/edpa/scripts/check_ticket_attached.py` — module docstring +
  user-facing error message both show the `feat(S-5):` form as the
  recommended fix.
- `docs/kashealth-pilot/KASHEALTH-PILOT.md` — single non-CC commit
  example converted (`EDPA pilot: …` → `chore(edpa): …`).
- `CONTRIBUTING.md` — new "Commit Conventions" section linking to the
  rules file with the full type palette + examples.

Hook behavior is unchanged — it still accepts any subject containing
an EDPA item ID, plus escape and auto prefixes — so projects that
don't yet use CC keep working.

## 2.1.1 — 2026-05-27 — Expose story_activity audit in results JSON

Patch release follow-up to C7.5. `load_story_activity_events()` already
computed a per-Story audit log (item_id, credit_factor, story_js,
effective_js, n_yaml_edit_signals) but the data was captured into a
local variable and dropped before `edpa_results.json` was written.

This release wires the audit into the output JSON next to `gate_events`,
so post-iteration inspection can see which in-flight Stories received
credit and with what multiplier without grepping git history.

### feat(v2.1): expose story_activity audit in edpa_results.json

Two-line wiring in `engine.py`'s `main()`:

```json
"story_activity_events": [
  {
    "item_id": "S-501",
    "type": "story_activity",
    "credit_factor": 0.4,
    "story_js": 8,
    "effective_js": 3.2,
    "n_yaml_edit_signals": 3
  }
]
```

Empty list ⇒ key omitted (truthy check) so clean iterations don't carry
empty arrays in their snapshots.

No schema change, no test broken — 541 tests still pass.

## 2.1.0 — 2026-05-26 — Local-first attribution complete

V2.0 closed the GH-coupling architectural gap. V2.1 closes the local
attribution gaps that were exposed once V2.0's CI-only signal source
was demoted: local git hooks now emit commit attribution signals, all
item types get fresh contributors[] before engine scoring, and
in-flight Stories get partial credit instead of all-or-nothing-at-Done.

The release also includes the architectural rule file that ships in
the plugin for Claude Code / agent consumers.

### feat(v2.1): WSJF strict defaults (krok C1)

`_handle_item_create` always writes `js:0, bv:0, tc:0, rr_oe:0,
wsjf:0.0` to YAML. V2.0 omitted these when unspecified, letting the
engine silently coerce None → 0. V2.1 makes the "this item hasn't
been WSJF-scored yet" state visible to humans reading the YAML.

`_handle_item_update` zero-fills missing WSJF fields on legacy items
so reads remain deterministic.

New migration helper: `migrate_wsjf_defaults.py` backfills existing
V2.0 projects.

### refactor(v2.1)!: rename `ci_signals[]` → `evidence[]` (krok C2)

The raw signal log in each item's frontmatter is now `evidence[]`,
matching EDPA's "Evidence-Driven Proportional Allocation" vocabulary
(the V2.0 name `ci_signals[]` implied CI-only, which V2.1 broadened).

Backward compatible: `detect_contributors.read_evidence()` reads
either block; writes always go to `evidence[]` and drop any
`ci_signals[]` entry. `read_ci_signals` is preserved as an alias for
V2.0 callers (slated for removal in V3.0).

New migration helper: `migrate_evidence_rename.py` for bulk on-disk
conversion (idempotent, `--dry-run`).

### feat(v2.1): local evidence emitter — post-commit hook (krok C3)

`plugin/edpa/scripts/local_evidence.py` runs as a `post-commit` git
hook. For every commit referencing an EDPA item ID (in subject/body
or via changed `.edpa/backlog/{type}/{ID}.md` paths) it emits:

- `commit_author` — author of the commit (resolved via people.yaml
  email/name/github lookup) — weight 2.78
- `manual:commit_message` — parsed from `/contribute @login weight:N`
  directives in commit body — weight per directive

Self-recursion guarded by the `chore(evidence):` subject prefix on
its own follow-up commits.

Skip rules: env opt-out (`EDPA_NO_LOCAL_EVIDENCE=1`), merge commits,
bot commits, unknown authors (logged to stderr, doesn't block commit).

This closes the V2.0 hole where projects without GH CI got NO
PR-style attribution at all — local commit_author signals now flow
into every project, regardless of GH Actions availability.

### feat(v2.1): commit-msg ticket-attached hook (krok C4)

`plugin/edpa/scripts/check_ticket_attached.py` runs as a `commit-msg`
git hook. Blocks commits that have non-trivial diffs but no EDPA item
ID, with helpful fix instructions (use existing ID, `/edpa:add` to
create one, `no-ticket:` escape prefix, or `--no-verify` bypass).

Auto-passes: auto-generated prefixes (chore(evidence):, Merge…,
Revert…, Initial commit, fixup!/squash!), operational paths only
(LICENSE, README, .gitignore, package.json, .github/, .vscode/), and
empty diffs.

### feat(v2.1): architectural rules for Claude Code / agents (krok C5)

`plugin/rules/edpa-work-rules.md` ships in the plugin as the
canonical rule file. `project_setup.py --with-rules` copies it to
`.claude/rules/` so Claude Code auto-loads it into every agent
session in the repo. Non-CC tooling can read the markdown directly.

Rule core: "every commit attributes to an EDPA backlog item; create
one first if it doesn't exist." Plus the C4 hook escape hatches and
operator guidance.

### refactor(v2.1)!: demote CI workflow — drop pr_author (krok C6)

`sync_pr_contributions.py` no longer emits `pr_author`. After C3,
`local_evidence.py` already credits the PR author as `commit_author`
locally — emitting `pr_author` from CI would double-count the same
human action.

The CI workflow is now strictly the optional source for PR-thread
signals that don't exist in git: `pr_reviewer` and `issue_comment`.
Updated workflow template comment explains when to install (review-
heavy GH teams) vs. skip (single-dev, off-GitHub, review-light).

### fix(v2.1): cw_heuristics.yaml wired end-to-end (krok C7)

Two latent bugs found during C6 investigation:

1. `project_setup.seed_configs` did NOT seed `cw_heuristics.yaml` to
   `.edpa/config/`. Typical install had no config file.
2. `engine.load_heuristics` fallback chain pointed at the V1 location
   (`.claude/edpa/templates/`), not the V2 vendored location
   (`.edpa/engine/templates/`). So when (1) hit, the engine fell all
   the way through to a hardcoded minimal lacking `gate_weights`.

Combined effect: `gate_events` was ALWAYS empty for V2.0 projects —
PM/Arch credit from multi-iteration Feature/Epic gate transitions
was silently dropped. With C7, the typical install now uses the
documented gate_weights from the template.

### feat(v2.1): in-flight Story credit via activity events (krok C7.5)

`engine.load_story_activity_events()` emits synthetic items for
in-flight Stories with `yaml_edit_signals` in the iteration window:

```
id        = "{story_id}@activity"
level     = "Story"
job_size  = story.js * credit_factor    (default 0.40)
contributors = []  (filled by _enrich_items_with_yaml_edit_signals)
```

The credit_factor reserves a fraction of Story.js for "in-progress
activity" — refinement-heavy iterations now credit prep work
instead of giving 0 hours until Done lands.

Configure via `story_activity.credit_factor` in cw_heuristics.yaml
(set to 0 to disable, matching V2.0 Done-only behaviour).

### feat(v2.1): refresh contributors[] for all types at close (krok C7.6)

`detect_contributors.py --all-items` (new CLI flag) walks every
backlog type and refreshes contributors[] from accumulated
evidence[]. Run before engine at close-iteration so gate events
on Feature/Epic/Initiative inherit fresh contributors[] reflecting
the latest evidence aggregation — not the stale snapshot from
whenever someone last edited the item.

Bug it fixes: V2.0 stored contributors[] on Feature/Epic/Initiative
ONCE when the LBC was first written. Gate events inherited that
snapshot forever, so the LBC author dominated all gate-event credit
even when other people did all subsequent transitions and delivery.

Wired into `close-iteration` SKILL as Stage 2b (between mid-flight
PR sync and engine run).

### Tests

541 passing (vs. 484 in V2.0 baseline). New suites:

- `test_migrate_wsjf_defaults` (8) — C1 backfill
- `test_migrate_evidence_rename` (13) — C2 rename + backward-compat
- `test_local_evidence` (16) — C3 post-commit emitter
- `test_check_ticket_attached` (16) — C4 commit-msg hook
- `test_project_setup_rules` (4) — C5 rule installation
- `test_heuristics_wiring` (6) — C7 lookup chain
- `test_story_activity_events` (10) — C7.5 in-flight Story credit
- `test_refresh_all_contributors` (6) — C7.6 all-types refresh

### Migration from V2.0

Run these once per project after upgrading the engine:

```bash
python3 .edpa/engine/scripts/migrate_wsjf_defaults.py    # C1: add 0 defaults
python3 .edpa/engine/scripts/migrate_evidence_rename.py  # C2: rename block
python3 .edpa/engine/scripts/project_setup.py \
  --with-ci --with-hooks --with-rules                    # C5/C7: re-seed
```

The hooks installed by `--with-hooks` now include `commit-msg`
(ticket-required) and `post-commit` (local_evidence) on top of the
existing `pre-commit` (ID-safety) and `pre-push` (collision check).
`--with-rules` installs the architectural rules into `.claude/rules/`.

## 2.0.0 — 2026-05-26 — V2 local-first hard cut (BREAKING)

The V2 local-first architecture is now the only supported path. All
runtime `gh` dependencies in the engine, MCP server, and CLI have been
removed; PR-derived signals arrive exclusively via the CI materialization
layer (workflow + `sync_pr_contributions.py` from `1.24.0-rc1`).

For V1 → V2 migration, run `migrate_v1_to_v2.py` first. The V1 codebase
remains available at the `v1-github-coupled` git tag for projects that
need it.

### BREAKING — files removed

- `plugin/edpa/scripts/sync.py` (~1800 lines)
- `plugin/edpa/scripts/_gh_issue_factory.py`
- `plugin/edpa/scripts/_sub_issue_linker.py`
- `plugin/edpa/scripts/sync_collaborators.py`
- `plugin/edpa/scripts/create_project_views.py`
- `plugin/edpa/scripts/project_views.py`
- `plugin/edpa/scripts/lookup_org.py`
- `plugin/skills/edpa-sync/`
- `plugin/skills/edpa-sync-people/`
- MCP tool `edpa_sync_people` (handler + dispatch)
- `backlog.py cmd_add` — V1 GH-first path (the `--local` flag is gone;
  the V2 local path is the only path)

### BREAKING — behavior changes

- `backlog.py add` is now V2 local-first by default. No `gh` calls,
  no `issue_map.yaml` write. The CLI flag `--local` was removed —
  V2 behavior is the default and only behavior.
- `project_setup.py` rewritten from ~1050 lines to ~250 lines. It no
  longer creates a GitHub Project, custom fields, or labels. New
  flags: `--with-ci` (copy contribution-sync workflow), `--with-hooks`
  (install pre-commit + pre-push ID safety hooks).
- `detect_contributors.run_gh()` now returns `None` by default — the
  engine is fully local. Escape hatch: `EDPA_USE_GH=1` env var
  re-enables direct gh calls for local debugging (inverse of the
  `EDPA_NO_GH=1` flag introduced in 1.24.0-rc1).
- Engine now reads `ci_signals[]` from each item's YAML via the new
  `detect_contributors.read_ci_signals()` and mixes them with
  git-native signals during aggregation. CI commits are the only
  source of PR-derived signals.

### Removed tests

13 sync-related test files deleted (1× e2e, 11× unit, 1× conflict). See
git history at the 2.0.0 commit for the list. Total test count dropped
580 → 447; all 447 remaining pass.

### Skill updates

- `edpa-add` skill rewritten — V1 dual-mode docs removed, V2-only.
- `edpa-setup` skill rewritten — describes V2 bootstrap flow (no GH
  Project provisioning, optional `--with-ci` + `--with-hooks`).
- `edpa-sync` and `edpa-sync-people` skills removed.

### Migration

1. `python3 .edpa/engine/scripts/migrate_v1_to_v2.py --dry-run` to preview.
2. `python3 .edpa/engine/scripts/migrate_v1_to_v2.py` to apply.
3. `python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks`
   to opt into the new CI workflow and git hooks.
4. Archive (don't delete) the GitHub Project board for audit history.

If you need to stay on V1 indefinitely, pin to `v1-github-coupled`:

```bash
git checkout v1-github-coupled
```

## 1.24.0-rc1 — 2026-05-26 — V2 local-first staging

Release candidate for the V2 local-first architecture. **All changes are
additive** — V1 GH-coupled flows still work unchanged. V2 paths are
opt-in (`--local` flag, `EDPA_NO_GH=1` env, `--with-server`). The hard
cut that deletes GH code is scheduled for the next major (2.0.0).

Plan: [docs/v2/concept.md](docs/v2/concept.md), [docs/v2/plan.md](docs/v2/plan.md).

### feat(v2): local-first ID allocation (krok 3)

- `plugin/edpa/scripts/id_counter.py` — atomic `next_id(type, root)` with
  file lock and `max(counter, fs_scan)` resolution. Counter file lives
  at `.edpa/config/id_counters.yaml`.
- `plugin/edpa/scripts/_git_timestamps.py` — `created_at`/`updated_at`/
  `closed_at` derived from `git log` (replaces GH Issue API metadata).
- New runtime dep: `filelock>=3.12` (cross-platform).

### feat(v2): MCP write tools — 7 new (krok 1)

- `edpa_item_create`, `edpa_item_update`, `edpa_item_transition`,
  `edpa_item_link_parent`, `edpa_iteration_create`, `edpa_iteration_close`,
  `edpa_people_upsert`.
- Each handler does atomic write (tmp + rename), validates the SAFe
  parent hierarchy (Story→Feature→Epic→Initiative) and status workflow.
- `ITEM_ID_RE` extended to `^[A-Z]{1,3}-\d{1,9}$` (Event uses 2-letter
  `EV-`).

### feat(v2): MCP write tool idempotency (krok 1.5)

- `@_idempotent("tool_name")` wraps all 7 write handlers; passing
  `idempotency_key` short-circuits to the cached response within 24h
  TTL. JSONL log at `.edpa/.idempotency.log` (gitignored).
- ERROR responses are not cached — user can fix + retry.

### feat(v2): `edpa-add --local` dual mode (krok 2)

- `backlog.py cmd_add --local` calls `mcp_server._handle_item_create`
  in-process; no `gh issue create`, no `issue_map.yaml` update.
- Default still GH-first when sync config exists (V1 behavior).
- `edpa-add` skill updated to explain mode selection.

### feat(v2): ID safety hooks + collision renumber (krok 4)

- `plugin/edpa/scripts/validate_ids.py` — pre-commit and pre-push
  validator. Catches filename≡frontmatter id mismatches, duplicate IDs
  in staged set, counter monotonicity, and HEAD/upstream collisions.
- `plugin/edpa/scripts/renumber_collisions.py` — semi-auto resolution
  (fetch upstream, find ADDED files with colliding IDs, rename file,
  rewrite `id:`, propagate `parent:` refs, bump counter).
- Hook wrappers `plugin/edpa/scripts/hooks/{pre-commit,pre-push}-id-safety`
  delegate to validator. Opt-in install via symlink.

### feat(v2): CI materialization layer (krok 4.5, ADR-012 + ADR-013)

- `plugin/edpa/scripts/sync_pr_contributions.py` — platform-agnostic
  deterministic script. Pulls PR data (gh in Action or `--event`
  JSON), extracts EDPA item refs from title/body/branch, emits signals
  (pr_author, pr_reviewer, issue_comment) into `ci_signals[]` block.
  Idempotent via dedupe on `signals[].ref`. 3× race retry with
  `git pull --rebase --strategy-option=ours`.
- `plugin/edpa/templates/github-workflows/edpa-contribution-sync.yml`
  — workflow template. Default mode: merge-only (1 commit/PR). Live
  mode opt-in via commented-out triggers.
- `detect_contributors.py:run_gh()` honors `EDPA_NO_GH=1` env →
  suppresses all gh calls. V2 opt-in. Safer than removing gh code now.
- `commands/close-iteration.md` Stage 2a — mid-flight PR sync for open
  PRs at iteration close.

### feat(v2): migration script (krok 5)

- `plugin/edpa/scripts/migrate_v1_to_v2.py` — idempotent 6-step
  conversion of a V1 GH-coupled project to V2 local-first: final
  sync pull → seed counter → backfill timestamps → archive
  `issue_map.yaml` → strip `sync:` from `edpa.yaml` → single
  migration commit. `--dry-run` and `--skip-pull` flags supported.
- `id_counter.seed_counters_from_fs()` — public helper used by
  migration and as recovery for lost counter files.

### feat(v2): edpa-server skill scaffold (krok 7)

- `plugin/skills/edpa-server/SKILL.md` — start/stop/status of an
  optional Node HTTP server serving the React PI planning UI from
  `.claude/edpa/server/`. Localhost-only, per-developer, single-user.
- `plugin/commands/server.md` — thin command wrapper.
- `install.sh --with-server` flag vendors `tools/pi-planning/`. Build
  pipeline (npm install + dist) is follow-up work.

### Open gates (not in rc1)

- **E2E migration test on a real V1 project.** `migrate_v1_to_v2.py`
  is unit-tested against a sandbox repo. Plan requires one real-world
  smoke before the GH-removal hard cut in 2.0.0.
- **GH code removal (Krok 6).** `sync.py` (~1800 lines),
  `_gh_issue_factory.py`, `_sub_issue_linker.py`, `sync_collaborators.py`,
  `plugin/skills/edpa-sync/`, `plugin/skills/edpa-sync-people/` remain
  in tree. 2.0.0 will delete them.
- **PI planning server build pipeline.** `tools/pi-planning/` ships as
  source; `--with-server` vendors source, user runs `npm install &&
  npm run build` manually.

### Tests

580 pytest tests pass. New suites: `test_id_counter` (17),
`test_git_timestamps` (11), `test_mcp_write_tools` (40),
`test_backlog_add_local` (12), `test_validate_ids` (8),
`test_renumber_collisions` (3), `test_sync_pr_contributions` (11),
`test_migrate_v1_to_v2` (9), `test_mcp_idempotency` (13).

## 1.23.1 — 2026-05-25

Bugfix: sync pull now actually populates GitHub Issue timestamps.

### fix(sync): enrich project items with issue timestamps

`gh project item-list --format json` does **not** expose issue-level `createdAt`/`closedAt`/`updatedAt` in the `content` block (only `body`, `number`, `repository`, `title`, `type`, `url`). The 1.23.0 extractor in `map_gh_items_to_edpa` read those fields from `content` but they were never present, so local backlog YAML never received timestamps and `edpa_flow_metrics` always returned `n/a`.

`gh_fetch_project_items` now post-processes the project item list by issuing one `gh issue list --repo <X> --json number,createdAt,closedAt,updatedAt --state all --limit 500` call per unique repository and merging the timestamps back into each item's `content`. Multi-repo projects are batched per repo. Failures (missing repo info, gh errors) degrade silently — items still return without timestamps.

Existing tests were green because the fixtures injected timestamps directly into `content`, bypassing the real CLI output shape. Added regression tests in `tests/test_sync_timestamps.py` that monkey-patch `subprocess.run` with the realistic empty-timestamp shape to prevent recurrence.

## 1.23.0 — 2026-05-25

Timestamp extraction, flow metrics, and improved conflict detection.

### feat(sync): extract and store GitHub issue timestamps as read-only fields

`sync pull` now reads `created_at`, `closed_at`, and `updated_at` from each GitHub issue and writes them as read-only frontmatter fields in the local backlog item. These fields are never modified by `sync push` -- they flow one-way from GitHub. Used by the new `edpa_flow_metrics` MCP tool and the improved conflict detection.

### feat(sync): timestamp-based conflict detection via `updated_at`

`_detect_remote_modifications()` compares the locally stored `updated_at` against the GitHub-side value. When the remote timestamp is newer, the item is flagged as remotely modified -- catching direct GitHub UI edits that bypass the `sync push` changelog. `sync conflicts` surfaces these alongside existing changelog-based checks.

### feat(mcp): `edpa_flow_metrics` tool for cycle time, throughput, item age metrics

New MCP tool computing delivery flow analytics from synced timestamps:
- **cycle_time** (mean, median, p85) -- `created_at` to `closed_at` for Done items
- **open_items_age** (mean, median, p85) -- elapsed since `created_at` for open items
- **throughput** -- count of closed items in the period
- **items_detail** -- per-item breakdown with status and timestamps

Both `iteration` and `level` inputs are optional filters.

### docs(setup): hint for GitHub timestamp project fields

Updated `docs/mcp.md`, `docs/RUNBOOK.md`, `docs/quick-start.md`, and `README.md` to document the new timestamp fields, flow metrics tool, and conflict detection improvements.

## 1.22.1 — 2026-05-25

Same-day patch: two sync bugs surfaced by a full end-to-end run against `technomaton/edpa-e2e-test-{ts}` (install → `project_setup` → `backlog add I/E/F/S` → 2× PI cycle → close). Both fixes pinned by new regression tests; full suite 420 passing.

### fix(sync): correct off-by-one in EDPA ID parser (sync push duplicate-create regression)

Commit `5363149` (the 1.22.0 "strict GH-first add" PR) generalized the 2-char prefix check in `map_gh_items_to_edpa` to also accept `D-` and `EV-` by parameterizing `plen` — but wrote `plen = len(prefix) - 1` instead of `plen = len(prefix)`. The dash stayed inside `candidate[plen:]`, so `.isdigit()` always returned `False` and the function silently returned `{}` for every real GH issue.

End-to-end consequence: after `backlog add` (which is GH-first and uses server-assigned issue numbers as the EDPA ID), the very next `sync push` saw `Remote items: 0` and re-created the same 5 items as fresh GH issues #6–#10 — duplicating the project on every push and rewriting `issue_map.yaml` to point at the wrong numbers. The contract that EDPA ID equals `{prefix}-{GH issue #}` was broken.

Fix: drop the `- 1`. `tests/test_sync_id_parser.py` adds 7 cases covering all six supported prefixes (`I-`, `E-`, `F-`, `S-`, `D-`, `EV-`) and edge cases (unprefixed titles, duplicate-ID collision); without the fix 6 of 7 fail.

### fix(sync): preserve local assignee/owner on pull when GH-side is empty

`gh project item-list --format json` does not expose user-picker fields — `assignee` and `owner` always come back empty even when the GH issue has assignees set. Without a guard, `compute_diff` proposed wiping the local `assignee:` value on every pull, so the loop `push → pull` immediately undid the push. The push side is fine: `cmd_push` calls `gh issue edit --add-assignee` and the native GH assignee is set correctly; only the pull-side deserialization is blind.

Fix: extend the existing iteration-empty guard at `compute_diff` to also cover `assignee` and `owner` — empty-remote no longer overwrites non-empty local for these three fields. Real remote values still propagate (pinned by `test_pull_still_applies_remote_assignee_when_remote_has_value`), other fields (status, js, …) still propagate empty values as before.

A richer pull path (GraphQL `ProjectV2ItemFieldUserValue` or `gh issue list --json number,assignees` joined into `remote_items`) is the longer-term fix and would let pull actually mirror manual GH-side reassignments instead of silently ignoring them — tracked as a follow-up. The guard is the conservative choice today: never lose work.

`tests/test_sync_pull_preserves_local.py` adds 6 cases pinning the guarded behaviour and the unchanged status/js behaviour.

## 1.22.0 — 2026-05-25

Pilot-feedback release: strict GH-first `backlog.py add` (title mirror, sub-issue linking, single ID series), shared GH issue factory, full test+docs sweep, plus housekeeping (Vercel auto-build off, mcp-server date-flake fix, `.lean-ctx/` ignored).

### fix(tests): align `test_mcp_server` iteration date asserts with 1-week cadence

`test_handle_status` and `test_handle_iterations_all` had hardcoded iteration dates from the original 2×2-week PI-2026-1 cadence. Commit `0417727` restructured PI-2026-1 to 5×1-week iterations, but the asserts didn't move — they sat red on `main` for three days. Fixed three numbers (`active_iteration_start/end`, `iters[0].end_date`) and added inline comments pointing at the source YAML files so the next cadence shuffle is a 30-second update.

### chore: disable Vercel auto-build on git push

Vercel auto-detection saw `requirements.txt` in the root, decided EDPA was a Python service, and failed to find an entry point on every commit — spamming red checks on PRs. `vercel.json` now sets `git.deploymentEnabled: false`. The `web/` Astro site is built and deployed manually via `vercel deploy --prebuilt web/dist` (cheaper than burning Vercel build minutes on every commit).

### chore: ignore `.lean-ctx/` cache files

Per-machine MCP knowledge-graph cache no longer gets staged. Two stale entries removed from the index (already absent from disk).

### test+docs: cover `_gh_issue_factory` and `cmd_add`; sweep stale docs

**29 new tests** locking in the PR1+PR2 behaviour so future regressions surface immediately:

- `tests/test_gh_issue_factory.py` (23 tests) — pure-function coverage of `create_gh_issue` and `edpa_id_for`. Mocks subprocess at the `_gh` entry point. Asserts: known-id mode (single create with full title), new-id mode (create + edit), hard failures (create / title edit / subprocess OSError) raise `RuntimeError`, soft failures (Issue Type assign, project add, sub-issue link, node_id resolve) populate `warnings`, conditional pipeline steps (no `parent_node_id` → no link, no `project_num` → no item-add), `assignee_login` and `extra_labels` propagation, full happy-path return dict.

- `tests/test_backlog_add_gh_first.py` (6 tests) — `cmd_add` orchestration with factory mocked. Asserts: fail-fast with exit code 1 + actionable message when sync config missing, Initiative writes `.md` + `issue_map.yaml` with `node_id`, child item forwards parent `node_id` from `issue_map.yaml`, parent without `node_id` warns but continues (older pre-PR1 maps), GH hard failure aborts without writing local state, derived `edpa_id` from factory wins over any local sequential scan (the PR1 invariant).

**Docs sweep** — stale instructions removed/updated:

- `plugin/skills/edpa-setup/SKILL.md`: removed the "run `sync push` after add to link sub-issues" instruction (now happens inside `add`), forbade `backlog.py add --local` (removed in PR1), updated example to reflect the unified add flow.
- `docs/E2E-SKILLS-TEST-PLAN.md`: explicit expectation that bulk setup uses single `gh issue create` (full title) and `addSubIssue` GraphQL mutation, distinguishing it from the interactive `add` path's two-phase create+edit.
- `docs/playbook.md`: corrected Epic example (missing `--parent I-1`) and added a paragraph explaining the strict GH-first contract and the title format mirror.
- `docs/kashealth-pilot/KASHEALTH-PILOT.md`: rewrote section 2 — old positional syntax (`add Initiative "name"`) replaced with the current `--type X --title Y` form, dropped now-redundant `sync.py push` after add, added a preamble explaining the GH-first requirement.
- `plugin/edpa/templates/edpa.yaml.tmpl`: added `event: "EV"` to `naming.item_prefixes` (Event type was introduced in 1.21.1 but the template still listed only Initiative/Epic/Feature/Story/Task/Defect).

404 tests pass (the 2 preexisting `test_mcp_server.py` date-flakes remain deselected — they fail on `main` too, tracked separately).

### refactor: extract `_gh_issue_factory` shared by backlog.py / sync.py / project_setup.py

The three call sites that create GH issues (`backlog.py cmd_add`, `sync.py gh_create_issue`, `project_setup.py` STEP 6) had drifted copies of the same six-step pipeline (create → resolve node_id → rewrite title → assign Issue Type → add to project → link sub-issue). PR1 fixed the symptoms in `backlog.py` but left the duplication; this PR collapses all three into one `create_gh_issue` helper in `_gh_issue_factory.py`.

The factory exposes two creation modes:
- **known-id** (sync.py push, project_setup.py): caller passes `edpa_id`, factory does a single `gh issue create` with the final `"{ID}: {title}"` — saves one API round-trip per item.
- **new-id** (backlog.py add): caller omits `edpa_id`, factory creates with the raw title, derives `"{prefix}-{num}"` from the server-assigned number, then `gh issue edit --title` to the canonical form.

Hard failures (create, title rewrite) raise `RuntimeError`. Soft failures (Issue Type assign, project add, sub-issue link) populate a `warnings` list so each caller surfaces them in its own UX (`cmd_add` colored line, `sync.py push` inline `[failed]`, `project_setup.py` `info()` banner).

Idempotency stays at the call site (`project_setup.py`'s `existing_issue_lookup` per-title cache is unchanged) because the three callers have incompatible idempotency models.

Net diff: `backlog.py` −85 lines, `sync.py` −60 lines, `project_setup.py` −35 lines, factory +250 lines. Single source of truth for title format, node_id resolution, and Issue Type assignment — a future change to the pipeline now lands in one file.

### feat(backlog)!: strict GH-first `backlog.py add` with mirrored title and sub-issue linking

Three pilot-user findings about `backlog.py add`, all rooted in `cmd_add` having drifted from the `sync.py push` implementation:

**1. Sub-issue links were never created.** `_gh_create_issue` returned `(num, url)` and `cmd_add` never called `_sub_issue_linker.link_sub_issue`, so every Epic/Feature/Story added through the CLI landed as a top-level issue in GH regardless of the local `parent:` field. The GH UI's "Sub-issues" panel stayed empty even though local `tree` rendered correctly.

`_gh_create_issue` now resolves the child's `node_id` via GraphQL and returns `(num, url, node_id)`. `cmd_add` reads the parent's `node_id` from `issue_map.yaml` (falling back to a GraphQL lookup for entries created before this version) and calls `link_sub_issue`. Successes and failures are logged inline.

**2. GH issue titles lacked the EDPA ID prefix.** `cmd_add` sent the raw title to `gh issue create`, so the GH UI showed `OAuth flow` while the local repo showed `F-8`. A search for `F-8` only landed on the local item, not on the GH issue.

`_gh_create_issue` now does a two-phase create + `gh issue edit --title` so the GH title is always `"{prefix}-{num}: {title}"` (e.g. `S-42: OMOP parser impl.`). This matches what `sync.py push` and `project_setup.py` already did for bulk creation.

**3. Two divergent ID series when `--local` was used.** The `--local` fallback (or auto-fallback on GH error) called `next_id_for_type` to assign a sequential local ID. If the GH project already had higher issue numbers, a later `sync push` couldn't reconcile the local `S-3` with `gh issue #47`. Pilot users reported "ghost items" that synced as duplicates.

The `--local` flag is removed. `cmd_add` now requires sync config and fails fast with an explicit hint to run `/edpa:setup`. On any GH error (issue create, title edit) the add aborts without writing a local file — no drift to clean up. The single source of truth for IDs is now the GH issue number.

Collateral cleanup:
- `TYPE_DIRS` / `PREFIX_TO_DIR` / new `TYPE_PREFIX` constants include `Defect` (`D-`) and `Event` (`EV-`), previously missing from `cmd_add`'s prefix map.
- `next_id_for_type` migrated to the shared `TYPE_PREFIX` constant (kept for migration tooling and tests).
- `sync.py` GH-title parser (`map_gh_items_to_edpa`) now accepts `D-` and `EV-` prefixes so pulling these types back from GH works.
- `_update_issue_map` persists `node_id` alongside `issue_number` and `project_item_id`.
- `plugin/skills/edpa-add/SKILL.md` rewritten to reflect strict GH-first flow and the title format mirror; the "Offline / pre-setup fallback" section was removed and the `--local` mention deleted from "What NOT to do".

## 1.21.2 — 2026-05-15
### fix(PI planning): loadEdpaConfig scans .edpa/iterations/, Event prefix EV-

Two issues caught during runtime smoke test of the PI Planning UI.

**1. `/api/config` returned `pis: []` after v1.20.0.**
`loadEdpaConfig` only looked for `pis:` array or legacy `pi:` object inside `edpa.yaml`. Since v1.20.0 moved PI/iteration timeline data into per-file YAML under `.edpa/iterations/` (`PI-{id}.yaml` for PI metadata, `PI-{id}.{n}.yaml` per iteration), `edpa.yaml` no longer carries either field, so the UI saw zero PIs → zero iterations → no items rendered on the board.

`loadEdpaConfig` now scans `.edpa/iterations/`:
- Files containing `pi:` at root → PI metadata blocks (id, status, iteration_weeks, pi_iterations, shared_services, events).
- Files containing `iteration:` at root → per-iteration metadata; grouped by their `pi:` field; sorted numerically by id (so `PI-2026-1.10` comes after `.9`).
- PIs that have iterations but no PI metadata file get synthesised (status derived from iteration statuses).
- Falls back to legacy `pis:` array and `pi:` object in `edpa.yaml` for older projects.
- Dates: `start_date` / `end_date` are parsed by js-yaml as `Date` instances (YAML timestamp schema). New `formatIterationDates` handles both Date and string, renders as `D.M.–D.M.` (Czech short format).

**2. Event ID prefix `V-` → `EV-`.**
Single-letter `V` was unfamiliar; `EV` mirrors what the UI now calls the row ("Events") and reads more naturally next to `S-`, `F-`, `R-` etc.
- `TYPE_PREFIX.Event` flipped to `'EV'`; `PREFIX_TO_DIR.EV` replaces `PREFIX_TO_DIR.V` (the existing `loadItem` `id.split('-')[0]` happens to work for both single- and multi-char prefixes).
- Renamed files in this repo: `V-1.md` → `EV-1.md`, `V-2.md` → `EV-2.md`; `id:` fields updated to match.
- Smoke-tested: POST `events` → `EV-3` (auto-cleaned).

Strict tsc clean. PI Planning UI runtime-verified: 5 iterations of PI-2026-1 render with proper dates (6.4.–17.4. etc.), Events row shows EV-1 / EV-2, ROAM shows R-1/R-2/R-3.

## 1.21.1 — 2026-05-15
### fix(PI planning): nextId for Event uses prefix V, not E

The 1.21.0 unification exposed a latent bug in `yaml-store.ts:nextId`:
prefix was derived as `type[0]`, which mapped `Event` → `E` and
collided with Epic IDs. The first probe POST to `/api/backlog/events`
after release returned `E-3` and wrote `.edpa/backlog/events/E-3.md`,
contaminating both namespaces. Verified during runtime smoke test of
the PI Planning server; no real user data affected (only test probe
artefacts).

- Added explicit `TYPE_PREFIX` map next to `PREFIX_TO_DIR` in
  `tools/pi-planning/server/yaml-store.ts`; `nextId` now reads
  `TYPE_PREFIX[type]` instead of `type[0]`. Same map is the inverse
  of `PREFIX_TO_DIR` so the two stay in sync.
- Smoke-tested: POST `events` → `V-3`, POST `risks` → `R-4`.
- Strict tsc + Vite build still clean.

## 1.21.0 — 2026-05-15
### feat(PI planning)!: unify Milestone+Event → Event; expand setup scaffolding
**Breaking** for any code carrying `type: Milestone`. The PI Planning tool's `ItemType` no longer accepts `'Milestone'`; the YAML store has dropped the `milestones/` directory and the `M:` ID prefix; the plugin's `_md_frontmatter.LEVELS` set no longer recognises "Milestone". Migrate by renaming files to `events/V-N.md`, setting `type: Event` and (optionally) `event_kind: review|release|demo|deadline`.

- **PI Planning UI** (`tools/pi-planning/`):
  - `src/types/edpa.ts` — `ItemType` drops `'Milestone'`.
  - `server/yaml-store.ts` — drop Milestone from `TYPE_DIRS`, `PREFIX_TO_DIR`, and the directory scan list. The `events/` directory remains and is fed by the new `events: 'Event'` entry in `server/routes/backlog.ts`'s POST type map (was missing, so Events couldn't be created via the API).
  - `src/store/backlog-store.ts` — add missing `Event: 'events'` to TYPE_DIRS.
  - ProgramBoard + ProgramBoardSection + FeatureCard — collapsed every `type === 'Milestone' || type === 'Event'` branch to plain `type === 'Event'`. Row id renamed `__milestones__` → `__events__`, label renamed "Milestones & Events" → "Events", CSS class `pb-section__row--milestones` → `--events`, `pb-section__card--milestone` → `--event`, `rf-header--milestone-row` → `--events-row`. Variable renames throughout (`isMilestone*` → `isEvent*`, `backlogMilestones`/`syntheticMilestones`/`milestones` → `backlogEvents`/`syntheticEvents`/`events`, `MILESTONE_MIN_H` → `EVENTS_ROW_MIN_H`). `HeaderNode.tsx` variant type widened to include `events-row` + `external-row` (was lying via `as` cast).
  - Vite build + strict tsc both clean (210 modules, 785 ms).
- **Plugin** (`plugin/edpa/scripts/_md_frontmatter.py`) — LEVELS set now `{Story, Feature, Epic, Initiative, Defect, Task, Risk, Event}`. Used only by the meta-line stripper; nothing else in the plugin engine reads it.
- **Setup scaffolding** (`plugin/skills/edpa-setup/SKILL.md`) — Step 1 mkdir now also creates `defects/`, `tasks/`, `events/`, `risks/` under `.edpa/backlog/`, plus `.edpa/pi-objectives/`. Added prose explaining that PI Planning artefacts (events, risks, objectives) carry their own lifecycle and are surfaced in the local PI Planning UI rather than synced to GitHub Projects or credited by the engine.
- **Data migration in this repo:**
  - `.edpa/backlog/milestones/M-1.md` → `.edpa/backlog/events/V-1.md` (`type: Event, event_kind: review`).
  - `.edpa/backlog/milestones/M-2.md` → `.edpa/backlog/events/V-2.md` (`type: Event, event_kind: release`, was already Event-typed but misfiled).
  - `.edpa/backlog/risks/R-4.md` deleted (duplicate of R-1 — same OMOP CDM v6 schema risk).
  - `.edpa/backlog/risks/R-3.md` — added missing `roam_status: accepted`.

Rationale: PI Planning artefacts now follow the same model as core delivery items — global backlog with per-type sequential IDs, `iteration:` field as the PI binding, no per-team prefix on the ID itself. `pi-objectives/PI-{id}.yaml` stays as the only genuinely PI-scoped artefact (per-team committed/stretch agreement). The Milestone type was redundant with Event in SAFe usage and was already drifting (M-2 carried `type: Event`).

## 1.20.3 — 2026-05-14
### chore: drop SKILL.md metadata block (plugin.json is single source of truth)
- All 7 `plugin/skills/*/SKILL.md` files lost the `metadata:` block
  (`author`, `version`, `domain`, `phase`, `standard`, `pattern`). None
  of these fields were consumed by EDPA scripts or by the Claude Code
  Agent Skill loader; `plugin.json` holds canonical author/version/license.
  Removes drift risk (per-skill `version: 1.0.0` was stale against
  plugin `1.20.x`) and cleans up the false `standard: AgentSkills v1.0`
  label.
- `plugin/README.md` — softened "AgentSkills v1.0 frontmatter" claim to
  "Claude Code Agent Skill frontmatter — portable Markdown + YAML".
- `web/src/pages/{,en/}presentation/{index,kashealth}.astro` — risk
  table cell rewritten from "AgentSkills standard: 26+ platforms,
  convert.sh" to a more accurate "Markdown + YAML frontmatter —
  portable beyond Claude Code".
- No functional change. Top-level frontmatter retained: `name`,
  `user-invocable`, `description`, `license`, `compatibility`,
  `allowed-tools` (and `disable-model-invocation` on autocalib).

## 1.20.2 — 2026-05-14
### docs: surface auto_update_engine opt-out
- `plugin/edpa/templates/edpa.yaml.tmpl` — commented-out
  `auto_update_engine: false` block right after `governance:` with
  rationale (local engine patches / strict-mutation environments).
  Visible to every user the moment they open their `.edpa/config/edpa.yaml`.
- `plugin/skills/edpa-setup/SKILL.md` — new paragraph after the
  "Vendor engine" step describing the v1.20.1+ SessionStart auto-vendor
  and the opt-out flag.
- Fix stale `/edpa:edpa-setup` reference in setup SKILL.md → `/edpa:setup`
  (slash paths now match the post-1.19.5 namespace).

## 1.20.1 — 2026-05-14
### feat(plugin): auto-vendor engine on SessionStart
New SessionStart hook `update_engine.sh` compares the bundled plugin
version against the project's `.edpa/engine/VERSION` and re-vendors
`scripts/`, `schemas/`, `templates/` when they diverge. No more manual
`/edpa:setup` re-run after `/plugin update`.

Fast path: single file compare returns in <50ms when versions match.

Skip conditions:
- `CLAUDE_PLUGIN_ROOT` unset (hook invoked outside Claude Code)
- cwd has no `.edpa/engine/` (not an EDPA project / pre-setup)
- VERSIONs match
- `.edpa/config/edpa.yaml` has `auto_update_engine: false`

Legacy `.yaml` backlog detector: when the auto-vendor runs (or on
warm-path), the hook scans `.edpa/backlog/**/*.yaml` and prints a
one-line warning pointing at `migrate_backlog_yaml_to_md.py`. Sync/
engine silently ignore stale `.yaml` items in v1.20.0+, so this catches
the regression that would otherwise wipe the GH project on the next
sync push.

Migration script moved from `tools/` to `plugin/edpa/scripts/` so
`install.sh` vendors it automatically — users always have a working
migrate command at `.edpa/engine/scripts/migrate_backlog_yaml_to_md.py`.

Tests: +10 `test_update_engine_hook.py` covering all skip paths, the
update path, opt-out, legacy-yaml warning, and walking up to find
`.edpa/engine/` from a subdirectory.

## 1.20.0 — 2026-05-14
### fix(plugin): namespace + invocability consistency for all skills
All 7 `edpa-*` skills now use `name: edpa:<x>` (instead of bare `<x>` which
polluted the global slash palette as `/setup`, `/engine`, etc.) and set
`user-invocable: true` (previously: `setup`, `engine`, `reports`, `autocalib`
were `false`, blocking `/edpa:setup` etc.). Same rationale as v1.19.5 which
removed wrapper commands — now the skill itself serves as both the auto-
trigger surface AND the explicit slash entry point. No more duplicate
palette entries, no more "use Y skill" indirection.

Also fixed `tests/test_consistency.py:test_skills_exist` — its hardcoded
required-commands list was stale since v1.19.5 (still expected the 5
removed wrapper commands).

### BREAKING: backlog items move from `*.yaml` to `*.md` + YAML frontmatter
Backlog items in `.edpa/backlog/{initiatives,epics,features,stories,defects,risks,milestones}/`
are now stored as `.md` files: a YAML frontmatter block (structured metadata —
id, status, js/bv/tc/rr_oe, parent, contributors[], etc.) followed by a Markdown
body (prose — description, acceptance criteria, refinement notes, notes).

**Why**: the body becomes 1:1 with the GitHub issue body. `sync push` sends the
body verbatim, no per-field re-composition. The recent v1.19.6 ruamel
block-scalar preservation fix becomes obsolete for prose — Markdown is the
native carrier for prose, not YAML block scalars.

**Format** (`stories/S-200.md`):
```markdown
---
id: S-200
type: Story
title: …
status: Done
contributors:
  - person: alice
    cw: 1
    as: owner
---

## Description

Prose, links, code blocks, anything Markdown.

## Acceptance Criteria

- [ ] criterion 1
- [ ] criterion 2
```

**Migration**: run `python tools/migrate_backlog_yaml_to_md.py` — idempotent,
preserves all frontmatter fields, moves `description`/`acceptance_criteria`/
`refinement_notes`/`notes` into the body as `##`-headed sections, deletes the
original `.yaml`.

**Impact**:
- New helper `plugin/edpa/scripts/_md_frontmatter.py` is the single source of
  truth for load/save. Used by sync, engine, mcp_server, board, traceability,
  validate_syntax, detect_contributors, backlog CLI, edpa_commit_info,
  pi_close, _people_loader.
- pi-planning frontend: `WorkItem` gains optional `body?: string`;
  `yaml-store.ts` parses/serializes frontmatter inline (no new TS dep).
- Pre-commit hook (`validate_on_save.sh`) now accepts `.md` paths and routes
  them through the new `validate_markdown()` schema check, which also rejects
  prose fields in frontmatter (must live in body).
- Validator: prose fields in frontmatter are now an error — they belong in the
  Markdown body.

## 1.19.6 — 2026-05-14
### fix(sync): preserve YAML block scalars on pull (ruamel round-trip)
`sync pull` and conflict resolution were corrupting backlog YAML files with
multiline fields (`description`, `acceptance_criteria`, `refinement_notes`,
`notes`): `yaml.dump()` rewrote `>` folded block scalars into single-quoted
flow scalars, mangled indentation of lists, and added spurious trailing newlines.

Root cause: `load_yaml` (PyYAML `safe_load`) discards formatting metadata;
`save_yaml` (`yaml.dump`) emits whatever PyYAML thinks looks right.

Fix: new `update_yaml_field(path, field, value)` uses `ruamel.yaml` round-trip
(preserves block scalars, quotes, list style) to update a single field in-place.
Both write-back sites switched to it (pull at line ~1125, conflict-resolve at
~2228). Falls back to `load_yaml`+`save_yaml` if ruamel is unavailable.
`ruamel.yaml>=0.18` was already in `requirements.txt`.

## 1.19.5 — 2026-05-14
### fix(plugin): remove duplicate commands, fix /sync-people namespace
- Removed 5 commands that duplicated skills (add, sync, setup, reports, calibrate)
  — they caused `/add`, `/sync` etc. to appear alongside `/edpa:add`, `/edpa:sync`
- `plugin.json commands[]` now contains only `close-iteration` and `board`
  (skills without a skill counterpart)
- Fixed stale paths in `close-iteration.md` and `board.md`:
  `.claude/edpa/scripts/` → `.edpa/engine/scripts/`
- `edpa-sync-people/SKILL.md`: changed `name: sync-people` → `name: edpa:sync-people`
  so it registers as `/edpa:sync-people` instead of bare `/sync-people`

## 1.19.4 — 2026-05-14
### fix: keep governance.methodology in sync with engine version
- `edpa.yaml.tmpl` — updated hardcoded `1.17.0` to current version; `bump_version.py`
  now includes it in literal replacements (`✓ 1 replacement(s)`)
- `install.sh` — on engine update (when `.edpa/config/edpa.yaml` already exists),
  rewrites `governance.methodology` to the newly installed version via inline Python;
  handles both quoted and unquoted YAML values

## 1.19.3 — 2026-05-14
### feat(sync): push description/acceptance_criteria/notes to GH issue body
`sync push` now syncs YAML content fields to GitHub issue bodies.

**New in `sync.py`:**
- `_format_issue_body(item)` — renders `description`, `acceptance_criteria`
  (list → `- [ ] …` checkboxes), `refinement_notes`, `notes` as structured Markdown
- `_body_hash(body)` — SHA-256[:16] for change detection
- `gh_update_issue_body(state, issue_number, body)` — `gh issue edit --body`
- `collect_items_flat` — now includes all 4 content fields in the entry dict
- `gh_create_issue` — uses `_format_issue_body` instead of minimal one-liner body
- `cmd_push` — body sync pass after field changes: computes hash, compares with
  `body_hash` stored in `issue_map.yaml`, calls `gh_update_issue_body` only when changed.
  Hash is persisted so re-running `sync push` is idempotent.

## 1.19.2 — 2026-05-13
### Fix: engine version detection + correct invocation path in docstring
Two issues surfaced during `/edpa:close-iteration` testing:

1. **"EDPA unknown" in reports** — `get_version()` searched only for `plugin.json`
   (works in the EDPA dev repo) but not in installed target projects where only
   `.edpa/engine/VERSION` exists. Added `VERSION` file as a fallback candidate
   (`Path(__file__).parent.parent / "VERSION"`).
2. **Stale docstring path** — `engine.py` usage block still showed the old
   `.claude/edpa/scripts/engine.py` path, causing Claude to get confused about
   `--edpa-root` when invoking the engine. Updated to the canonical installed path
   `python3 .edpa/engine/scripts/engine.py --edpa-root .edpa`.

## 1.19.1 — 2026-05-13
### Fix: Issue Type assignment in GH-first `backlog.py add`
`gh issue create` was passing the item type (`Epic`, `Initiative`, …) as `--label`,
which always fails unless that exact label exists in the target repo. GitHub Issue Types
are org-level GraphQL objects, not repository labels.

**Changes in `plugin/edpa/scripts/backlog.py`:**
- `_gh_create_issue` — removed `--label <type>` from the `gh issue create` call
- `_gh_set_issue_type` (new) — sets the Issue Type via GraphQL after issue creation,
  importing `get_org_issue_types` / `get_issue_node_id` / `assign_issue_type` from
  `issue_types.py`; non-fatal (prints a warning if org Issue Types are not configured)
- `cmd_add` — calls `_gh_set_issue_type` immediately after a successful GH issue create

## 1.19.0 — 2026-05-13

### GH-first backlog item creation (`/edpa:add`)

New minor version consolidating the GH-first item creation feature introduced in
v1.18.6 and removing obsolete GitHub issue templates.

**`/edpa:add`** — new skill and command for creating backlog items with collision-free IDs:

- `gh issue create` → GitHub assigns atomic issue number (#42)
- EDPA ID = type prefix + issue number (`S-42`, `E-15`, `F-8`, `I-3`)
- No more sequential local ID scan → no multi-user race condition
- `gh project item-add` → item visible in GitHub Project immediately
- `issue_map.yaml` updated automatically
- Auto `git commit -m "feat(S-42): <title>"`
- `--local` flag for offline / pre-setup fallback

**Removed: `.github/ISSUE_TEMPLATE/`** — `epic.md`, `feature.md`, `story.md` deleted.
EDPA uses org-level Issue Types (stronger than templates) and the `/edpa:add` skill
covers all creation paths. Templates were stale (old `S-XXX` ID scheme, label-based
instead of Issue Types) and duplicated logic with no consumer in skill-first teams.

## 1.18.6 — 2026-05-13

### New feature — GH-first backlog item creation (`/edpa:add`)

New skill `edpa-add` and command `add.md` providing `/edpa:add` for creating backlog items
with collision-free IDs via GitHub-first flow.

**Problem solved:** Multiple team members (especially with AI assistance) running
`backlog.py add` simultaneously produce the same sequential ID (e.g. both get `S-5`),
causing merge conflicts on push. GitHub issue numbers are an atomic server-side counter —
no collision possible.

**Flow:**
1. `gh issue create` → GitHub assigns atomic issue number (#42)
2. EDPA ID = type prefix + issue number → `S-42`, `E-15`, `F-8`, `I-3`
3. `gh project item-add` → adds to GitHub Project immediately
4. Writes `.edpa/backlog/<type>/S-42.yaml`
5. Updates `issue_map.yaml` entry
6. `git commit -m "feat(S-42): <title>"`

**Offline / pre-setup fallback:** `--local` flag forces sequential local scan (old behaviour).
Auto-falls back to local-first if `edpa.yaml` has no sync config.

- `plugin/skills/edpa-add/SKILL.md` — new skill with full instructions
- `plugin/commands/add.md` — new command wrapper
- `plugin/edpa/scripts/backlog.py`: added `_read_sync_config`, `_gh_create_issue`,
  `_gh_add_to_project`, `_update_issue_map` helpers; `cmd_add` rewritten for GH-first;
  `--local` flag added to `add` subparser

## 1.18.5 — 2026-05-12

### Bug fixes

- **plugin.json**: removed `hooks` field — Claude Code v2.1.139+ auto-loads `hooks/hooks.json`
  and errors with "Duplicate hooks file detected" when it is also referenced in the manifest.
- **plugin/.mcp.json**: removed explicit `env.GITHUB_PERSONAL_ACCESS_TOKEN` declaration —
  CC v2.1.139+ validates env var references at load time; `npx` inherits the variable from
  the shell automatically so the explicit declaration was unnecessary.
- **test_consistency.py**: updated `test_plugin_json_hooks_reference` to assert that
  `hooks/hooks.json` is NOT referenced in plugin.json (inverted guard for new CC behaviour).

## 1.18.4 — 2026-05-12

### Bug fixes

- **plugin.json skills**: entries now point to directories (`./skills/edpa-setup`) instead
  of SKILL.md files — Claude Code v2.1.139 changed the loader to expect directories and
  errors with "path is a file; expected a directory" on the old format.
- **project_setup.py step 9**: `edpa.yaml` is now seeded from `edpa.yaml.tmpl` if missing;
  previously step 9 silently skipped persisting GitHub state when the file didn't exist.
- **project_setup.py**: corrected `create_project_views.py` hint path from `.claude/edpa/scripts/`
  to `.edpa/engine/scripts/` (3 occurrences).
- **settings.json**: `enabledPlugins` value changed from string `"enabled"` to boolean `true`
  (schema validation fix).
- **bump_version.py**: updated template reference from `project.yaml.tmpl` to `edpa.yaml.tmpl`.

### Docs

- All web guides (`guide.astro`, `en/guide.astro`, `playbook.astro`, `edpa-token-setup.md`,
  `docs/playbook.md`) updated: `.claude/edpa/scripts/` → `.edpa/engine/scripts/`,
  `.claude/edpa/templates/` → `.edpa/engine/templates/`.
- Step 3 (Install) in both guide pages rewritten for new architecture: marketplace install
  (`/plugin install tm-edpa@technomaton-hub`) as primary path, `curl|sh` as secondary.

## 1.18.3 — 2026-05-12

### Canonical Claude Code plugin layout

The plugin tree now matches Claude Code's auto-discovery spec end-to-end,
so `/plugin install` via the marketplace works without any manual steps.
Previously the layout relied on explicit listings in `plugin.json` to
bridge the gap between what the spec expected and what the repo shipped;
post-`/plugin install` to a clean machine surfaced the divergence.

- `plugin/commands/edpa/*.md` → `plugin/commands/*.md` (flat). Slash
  command names are unchanged (`/edpa:setup`, `/edpa:board`, …) — they
  derive from the plugin name plus file basename.
- Skill slugs canonicalised via `name:` frontmatter override
  (`edpa-setup` → `setup`, etc.) so the auto-discovered slug becomes
  `/edpa:setup` instead of `/edpa:edpa-setup`. Directory names kept as
  `skills/edpa-*/` for backward-compat with any external path refs.
- New `plugin/.claude-plugin/marketplace.json` lets maintainers
  `/plugin marketplace add /path/to/edpa/plugin` against a local clone
  for native dogfooding (no more `.claude/` symlink farm).

### SessionStart hook + `requirements.txt`

Python deps install moves out of `install.sh` and into the plugin so
the marketplace install path provisions them automatically.

- New `plugin/requirements.txt` — single source of truth for runtime
  deps (PyYAML, ruamel.yaml, mcp, openpyxl).
- New `plugin/edpa/scripts/hooks/install_deps.sh` — SessionStart hook
  with cheap import probe + content-hashed marker in
  `${CLAUDE_PLUGIN_DATA}`. Cold ~700ms, warm ~15ms. Falls back to
  `pip install --break-system-packages` for PEP 668 environments,
  exits 0 on failure (never blocks session start).
- `plugin/hooks/hooks.json` registers the new SessionStart event
  alongside the existing PostToolUse hooks.

### `install.sh` slimmed (281 → 197 lines)

`curl|sh` installer now does download + extract + `.edpa/` bootstrap
only. Responsibilities that don't belong to the installer move into
the plugin:

- `pip install …` blocks (PyYAML, ruamel.yaml, mcp, openpyxl) removed —
  the SessionStart hook handles them for Claude Code users; non-CC
  users get the explicit `pip3 install -r .claude/requirements.txt`
  command at the end-of-install banner.
- `.github/workflows/edpa-*.yml` copy removed — `/edpa:setup` already
  has it in its step 2b, so both install paths converge on the skill
  for that step. Eliminates the divergence where marketplace installs
  never got workflows.
- Mirror update applied to `web/public/install.sh` so the Astro static
  hosting serves the slim version too.

### Hub `tm-edpa` switches to upstream pointer model

`technomaton/technomaton-hub` packs/tm-edpa/ no longer holds a
vendored copy of the plugin. The hub's `.claude-plugin/marketplace.json`
registers `tm-edpa` with `source: {github, repo: technomaton/edpa,
path: plugin}`, so `/plugin install tm-edpa@technomaton-hub` fetches
the plugin payload directly from this repo. The previous vendor-then-
mirror flow (`scripts/sync-edpa.sh` + `.github/workflows/sync-edpa.yml`)
chronically lagged upstream and shipped a docs-only stub without the
Python engine — pointer model removes the vendor step entirely.

`packs/tm-edpa/_vendor.json` keeps the upstream pin metadata
(`tag: v1.18.3`, SHA recorded at release time).

### CI

`.github/workflows/release.yml` (already in place since the v1.18.0
line) keeps building `edpa-plugin.tar.gz` on `v*` tag push. Confirmed
end-to-end via simulated marketplace install + planted iteration:
1.6 MB cache, no monorepo siblings (web/, tools/, tests/, docs/) leak,
all six skills + six commands resolve correctly, MCP server boots, full
engine → reports → pi_close → velocity chain runs without error.

### Tests

`tests/test_consistency.py::test_skills_exist` updated for the flat
`commands/` layout — was previously asserting the pre-flatten paths.

## 1.18.2 — 2026-05-12

### Removed — dead v1.10 calibration code

`plugin/edpa/scripts/evaluate_cw.py` deleted. The script was the
evaluator for the v1.10 `role_weights` / `role_overrides` Karpathy
autoresearch loop, both of which the engine has ignored since v1.11.
With the `/edpa:calibrate` skill rewired to `calibrate_signals.py`
(1.18.1), the evaluator had no remaining callers.

### Fixed — stale documentation across web + plugin

- 8 web pages (`guide.astro`, `evaluation.astro`, `presentation/index.astro`,
  `presentation/kashealth.astro` — CZ + EN) had `evaluate_cw.py` /
  `role_weights` references. Rewritten to point at `calibrate_signals.py`
  with the live MC + coordinate-descent flow.
- `evaluation.astro` "Loop" + "Safety constraints" sections rewritten
  end-to-end to the MC pipeline (was describing the deleted Karpathy
  loop).
- `plugin/README.md` tree map now lists `calibrate_signals.py` instead
  of the deleted evaluator.
- `plugin/skills/edpa-autocalib/SKILL.md` + `plugin/commands/edpa/calibrate.md`
  legacy note updated to "v1.18.2 removed" instead of "deprecated".

No engine, scoring math, or data-format change. The
`test_no_role_overrides_in_heuristics` assertions stay — they correctly
test that `role_overrides` is absent from heuristics (v1.11+ engine
behavior).

## 1.18.1 — 2026-05-11

### Fixed — `/edpa:calibrate` skill rewired to v1.11+ MC pipeline

The `edpa-autocalib` skill drove the deprecated `role_weights` autoresearch
loop and required a hand-curated `.edpa/data/ground_truth.yaml` to even
start. Since v1.11 the engine has not consumed `role_weights` /
`role_overrides` at all (see `plugin/edpa/scripts/engine.py:864`), so the
skill was effectively dead on arrival: every invocation failed with
"Insufficient ground truth (0 < 20 records)" before doing any work.

`SKILL.md` now orchestrates `plugin/edpa/scripts/calibrate_signals.py`
(Monte Carlo random sampling + coordinate descent on the 5 git-signal
weights). The MC corpus is self-generated, so no ground-truth file is
required. `plugin/commands/edpa/calibrate.md` rewritten to match.

No engine, scoring math, or data-format change — the fix is purely in the
skill orchestration layer.

### Added — `tools/sensitivity_check.py` (dev tool, not in plugin tarball)

Stand-alone tool that perturbs each `gate_weights` entry ±20% (rebalanced
or naked) on a synthetic PI and reports per-person cw distribution shift.
Confirms shipped defaults are robust: all 17 weights land in LOW class at
±20% rebalanced; only `Implementing→Validating` (Feature) and
`Implementing→Done` (Epic) reach MED at ±50%. Useful before any future
manual tuning of gate weights.

## 1.18.0 — 2026-05-11

### Stable promotion

`1.18.0-beta` shipped earlier the same day; this tag promotes the
same code to a non-prerelease release so that GitHub's `/releases/
latest` redirect points at it and `curl … install.sh | sh` users
land on the workflow-prefix refactor by default. No code change
between 1.18.0-beta and 1.18.0 — only release-flag metadata.

Live install.sh patch (read overwrite prompt from /dev/tty, support
`EDPA_FORCE_INSTALL=1` for non-interactive overwrite) ships with
this stable tag; the v1.18.0-beta plugin tarball did not include
it since install.sh lives outside `plugin/`.

### Breaking — `edpa-` prefix on all distributed workflows

All 11 plugin-shipped GitHub Actions workflows were renamed to use the
`edpa-` prefix:

  branch-check.yml         → edpa-branch-check.yml
  collaborators-sync.yml   → edpa-collaborators-sync.yml
  contributor-detect.yml   → edpa-contributor-detect.yml
  iteration-close.yml      → edpa-iteration-close.yml
  pi-close.yml             → edpa-pi-close.yml
  sync-git-to-projects.yml → edpa-sync-git-to-projects.yml
  sync-projects-to-git.yml → edpa-sync-projects-to-git.yml
  traceability-check.yml   → edpa-traceability-check.yml
  validate-item.yml        → edpa-validate-item.yml
  velocity-track.yml       → edpa-velocity-track.yml
  wsjf-calculate.yml       → edpa-wsjf-calculate.yml

Rationale: generic names like `branch-check.yml` collided with target
projects' own workflows; install.sh's "skip if exists" silently no-op'd
in collision cases, leaving the user thinking EDPA was installed when
it wasn't. Prefixed names are namespace-safe and group together in the
Actions UI sidebar.

**Migration for existing installs:** `install.sh` now detects legacy
unprefixed files in `.github/workflows/` and either:
- (default) prints `git mv` commands and continues with the install
  alongside the legacy files — review and apply the rename manually,
- (`EDPA_AUTO_MIGRATE=1`) renames legacy files automatically before
  copying the new prefixed versions.

### Fixed — `projects_v2_item` is webhook-only, not a workflow trigger

The v1.17.x sync-projects-to-git workflow used `projects_v2_item` as
a primary `on:` trigger (commit fafc77a), claiming event-driven sync.
That was wrong: `projects_v2_item` is an *organization webhook event*
documented in [Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads),
not a [workflow trigger](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
GitHub Actions cannot subscribe to Project v2 board changes directly.

Replaced with a business-hours polling cron (`*/30 6-17 * * 1-5` UTC =
Mon-Fri 8-18 CET/CEST) plus `workflow_dispatch` for manual on-demand
reconciliation. ~528 CI min/month, ~26% of Free plan 2000-min limit.
Maximum latency 30 min during business hours; weekends pause sync
(use workflow_dispatch or wait for Monday's first tick — max ~14h
latency Friday 18:00 → Monday 08:00 local).

### Refactor — standardized workflow patterns

Unified all commit-producing workflows behind a single pattern:

- **Git identity** is configured in its own step *before* any action
  that could auto-commit. Standard values across all workflows:
    user.name  = "EDPA Bot @ TECHNOMATON"
    user.email = "edpa-bot@noreply.technomaton.com"
  Previously several workflows ran `git config` inside the commit step
  or used legacy placeholders (`github-actions[bot]`,
  `edpa-bot@users.noreply.github.com`) that produced inconsistent
  attribution and failed when an earlier step already triggered a commit.

- **Token usage** moves to the `EDPA_TOKEN || GITHUB_TOKEN` fallback
  pattern with an explicit warning step when EDPA_TOKEN is missing.
  `collaborators-sync.yml` drops its bespoke `COLLAB_SYNC_TOKEN` secret
  in favor of the shared `EDPA_TOKEN` (same PAT carries `read:org`,
  `repo`, and `project` scopes — one secret instead of two).

Also fixed `contributor-detect.yml` permission denial — setting
`contents: write` explicitly forced all other permissions to `none`,
breaking `gh pr view` calls in the detection script. Restored
explicit `pull-requests: read` + `issues: read`.

### Notes

- No CW recalibration, no schema migration.
- Workflow drift between `plugin/edpa/workflows/` and `.github/workflows/`
  is now reconciled: plugin is canonical for all distributed workflows.

## 1.17.1-beta — 2026-05-10

### Fixed — surfaced via 2-PI × 5-iteration end-to-end run

Three real bugs in the 1.17.0 engine + CLI, all reproducible via a
synthetic 4-person team across 10 iteration closes:

- **engine.py — IP-iteration gate events were orphaned (0h derived).**
  `load_gate_events` synthesised events from Feature/Epic/Initiative
  status transitions and inherited the parent's `contributors[]` via
  `_passthrough_contributors`. When the parent was seeded with
  title+js+status only (the realistic state for an Initiative or
  Feature being progressively elaborated), the contributor list was
  empty and every gate event derived 0h despite real strategic work.
  Now `load_gate_events(..., people=...)` accepts the `people:` block
  and falls back to crediting the transition's commit author at
  `cw=1.0` with a `gate_transition_author` signal in the audit trail.
  In the E2E sandbox this took PI-2026-1.5 from 0h → 120h.

- **engine.py — Defects (and Tasks) bypassed the iteration filter.**
  The filter at `engine.py:539-547` had explicit branches for `Story`
  (exact-match) and `Feature` (PI-prefix match); `Defect` and `Task`
  fell through to the `Epic`/`Initiative` "always include if Done"
  path, so a Defect with `iteration: PI-2026-2.4` was credited in
  every iteration close in PI-2026-2 — once correctly in iter .4 and
  again in iter .5, doubling its hours in the PI rollup. The branch
  now reads `if item_type in ("Story", "Defect", "Task")`.

- **backlog.py — `tree` and `status` crashed with `KeyError: 'project'`**
  on every project using the canonical pilot `people.yaml` template.
  `load_backlog()` was reading project metadata from `people.yaml` (it
  has never lived there in the post-v1.10 schema); now it merges the
  `project:` block from `edpa.yaml`, and `cmd_tree` / `cmd_status`
  use `.get()` so an unconfigured project prints `(unnamed project)`
  instead of dying.

### Added

- `_build_person_resolver(people)` helper extracted from
  `_enrich_items_with_yaml_edit_signals` so the same login/email/id
  resolution logic now powers gate-event author resolution too.

### Notes

- No CW recalibration needed — signal weights are unchanged.
- No backlog data migration — these are read-path fixes only.
- Existing snapshots remain valid; re-running the engine for any
  iteration produces a corrected `derived_hours` distribution.

## 1.17.0-beta — 2026-05-10

### New — yaml_edit signals (8 structural diff-derived signals)

Every commit touching `.edpa/backlog/*.yaml` is now an explicit signal
of work on that item. Previously only PR-API surfaces (pr_author,
pr_reviewer, commit_author from PR commits) and gate-event status
transitions produced credit; pure content elaboration on Initiatives,
Epics, Features, and Defects (writing business case, drafting
acceptance criteria, expanding NFR/FR lists, recording risks) was
invisible to the engine.

The new collector `yaml_edit_signals.py` walks `git log -p` over the
backlog YAMLs in the iteration window and scores each commit-file
diff via 8 **structural** signals — never trying to semantically
classify content (operator naming drift makes that brittle):

- `yaml_edit:create` — new file with +id+type+title (item born; 5.0)
- `yaml_edit:block_add` — new top-level nested object (2.0 each)
- `yaml_edit:list_grow` — net `- ` bullets added (1.0 each, capped at 10/commit)
- `yaml_edit:scalar_change` — top-level scalar field set (0.5 each)
- `yaml_edit:lines_volume` — substantive-edit proxy (capped at 3.0)
- `yaml_edit:contributors_rebalance` — new person added to contributors[] (0.3 each)
- `yaml_edit:revert` — net-removal commit (negative weight)
- `yaml_edit:bulk_migration_discount` — `chore: rename / migrate` commits get ×0.1

Mitigations baked in:

- **Bot authors** (`*[bot]@*`, `github-actions@*`) → 0 weight
- **Tool-generated commits** (`EDPA sync push:`, `EDPA: capacity override`,
  `EDPA setup state committed`) → 0 weight
- **Whitespace-only diffs** → 0 weight
- **File renames / moves** → 0 weight (metadata only)
- **Status-only changes** → 0 weight (transitions.py owns gate-event credit)
- **Backdated commits** (`GIT_AUTHOR_DATE`) → use author date for window check
- **Bulk migrations** (rr→rr_oe across 36 files) → ×0.1 per file

Engine integration is in-memory: yaml_edit signal weights are merged
into existing contributors[] before run_edpa, then cw is re-normalized
per item. No YAML files are mutated during engine close; the frozen
snapshot captures the augmented contributors so the audit trail is
complete. Tunable weights live in `cw_heuristics.yaml` →
`yaml_edit_weights:` and are subject to future calibration via
`/edpa:calibrate`.

### Fixed — Bug A: Defects silently dropped from engine

Engine.py:1198 filtered `items = [i for i in items if i.get("level") == "Story"]`,
discarding Done Defects (and Tasks) loaded from `.edpa/backlog/defects/`.
Defects passed all earlier filters (TYPE_DIRS, status=Done, js>0) but
the level-filter dropped them silently. Bug fix promotes the predicate
to `level in ("Story", "Defect", "Task")`.

Found during E2E pilot run: D-1 (whitespace bug, status=Done, js=2,
contributors=[turyna 0.7, matousek 0.3]) was loaded then immediately
discarded → 0h credit despite the team closing it.

### Calibration deferred

Default `yaml_edit_weights` are conservative round numbers anchored to
existing detect_contributors weights (assignee=4.0, pr_author=3.4).
Monte Carlo prior calibration (1000 scenarios, optimize 8D parameter
space against MAD) is deferred — first kashealth pilot PI close will
provide ground truth for posterior calibration via `/edpa:calibrate`.
Pre-calibration weights are intentionally over-conservative on
yaml_edit:create (5.0) and block_add (2.0); over-credit shows up
quickly in operator review and is straightforward to tune down.

## 1.16.0-beta — 2026-05-09

### Fixed — E2E pilot defects (4)

End-to-end pilot run against `technomaton/edpa-e2e-pilot` (synthetic
4-person team, 5-iteration PI, real GitHub Project) surfaced four
defects on the day-1 happy path. All four are now patched.

- **`backlog.py add --rr-oe` raised `NameError: rr`.** Two leftover
  references to the pre-v1.11 `rr` variable were not migrated when the
  field renamed to `rr_oe`. Replacing them unblocks the very first
  `backlog.py add` invocation in the kashealth runbook.
- **`backlog.py add --contributor` emitted a legacy `as:` role field
  that `validate_syntax.py --strict` rejects.** v1.11 dropped role
  classification (roles are derived from `signals[].type` at display
  time), but the CLI was still writing the old shape — the tool's own
  validator marked everything it produced as invalid. CLI now emits
  `{person, cw}` only.
- **`project_setup.py` left the `Iteration` single-select field with
  only the `TBD` placeholder.** Bootstrap created
  `.edpa/iterations/PI-{year}-1.{1..5}.yaml`, but those iteration IDs
  were never seeded as options on the GitHub Project. Every subsequent
  `sync.py push` failed with `no option_id for
  'Iteration':'PI-2026-1.X'` until the operator discovered the
  undocumented `sync.py add-iteration <id>` workaround. STEP 9 now
  scans `.edpa/iterations/` for child iteration files, calls
  `_extend_iteration_options_via_graphql`, and refetches the field
  options so `option_ids` persists into `edpa.yaml` in the same step.
- **`reports.py` printed `Mode: **?**` on every timesheet** and
  `(None)` on every PI summary bullet. The `mode` field was retired in
  v1.14 (single calculation path) but the templates still tried to
  read it. The lines are dropped — auditors no longer see a literal
  `?` next to "Methodology" on every timesheet.

### Fixed — preflight nag on current installs

`docs/kashealth-pilot/preflight.sh` carried a hardcoded
`latest=1.8.1-beta` constant and warned every fresh install that it
was "outdated". The check now resolves the latest tag dynamically via
`gh release list` so a current install reports as current.

## 1.15.0-beta — 2026-05-09

### BREAKING — WSJF field rename: `rr` → `rr_oe`

The WSJF Cost-of-Delay component is renamed across all surfaces from
the abbreviated `rr` (Risk Reduction) to the full SAFe term
`rr_oe` (Risk Reduction & Opportunity Enablement). The previous
shorthand was incomplete — SAFe 6 defines this component as
"Risk Reduction & Opportunity Enablement" together, and the docs
already call it that everywhere; this release closes the gap in
the field key itself.

**Changed:**

- YAML field key in backlog items: `rr:` → `rr_oe:` (36 files in
  `.edpa/backlog/` migrated automatically; new template + schema use
  `rr_oe:`).
- Engine scripts (`sync.py`, `project_setup.py`, `backlog.py`,
  `validate_syntax.py`, `board.py`): all internal field references
  use `rr_oe`.
- CLI flag on `backlog add`: `--rr-oe` is the canonical name; legacy
  `--rr` is accepted as a deprecated alias for one release.
- Web TS engine: `WorkItem.rr_oe` replaces `WorkItem.rr`. Demo data
  for the calculator + dashboards updated.
- GitHub Projects custom field: new projects create
  "Risk Reduction & Opportunity Enablement". Existing projects with
  the old "Risk Reduction" field continue to work — sync.py detects
  the legacy name and emits a one-line warning so you can rename
  in the Projects UI on your own schedule.

**Migration for existing projects:**

```bash
# In your project root (with .edpa/ initialized):
python3 .claude/edpa/scripts/../tools/migrate_rr_to_rr_oe.py
# (or wherever you keep the script; or copy it from the EDPA repo)
```

Or by hand: `find .edpa/backlog -name '*.yaml' -exec sed -i ''
's/^\(\s*\)rr:/\1rr_oe:/' {} +`. Then validate with
`backlog.py validate`.

The GitHub custom field can be renamed in the Projects UI when
convenient — sync.py keeps working through the rename.

## 1.14.0-beta — 2026-05-09

### BREAKING — Single calculation path; simple/full/gates mode selector removed

The engine no longer has a `--mode` argument. The pre-v1.14
selector (`simple` | `full` | `gates`) collapsed into one path
because:

- `simple` and `full` were functionally identical in v1.11+
  (Relevance Signal was dropped). `full` only added richer audit
  metadata that v1.11 ships in every snapshot regardless.
- `gates` was a strict superset of `simple`: when git history
  records no transitions, gate event extraction returns 0 entries
  and the engine credits only Done items — same output as
  `simple`.

So the three-mode surface was carrying maintenance weight without
delivering distinct semantics. v1.14 collapses to one path:

- Stories at `status: Done` get credited.
- Feature/Epic/Initiative status transitions captured in git
  history (via `sync pull --commit`) become synthetic gate events
  weighted by `gate_weights[type][transition]`.
- When no transitions exist, only Done credit fires.

Backward compatibility: **none**. Pre-v1.14 callers passing
`--mode <X>` get an `unrecognized arguments` error from argparse.
Pre-v1.14 `mode=` kwarg in `run_edpa()` calls — same. Test fixtures
and example configs across the repo were swept clean.

**Removed:**
- `--mode` CLI argument from `engine.py`
- `mode` parameter from `run_edpa()` Python signature
- `args.mode == "gates"` / `"simple"` / `"full"` branches in main
- `print_summary(results, mode, ...)` mode parameter
- `engine_output["mode"]` field (and snapshot's `mode:` key)
- `calculation_mode` field from `plugin/edpa/templates/project.yaml.tmpl`
- `audit_mode` field — was never read by any code (dead config)
- `mode` workflow input from `plugin/edpa/workflows/iteration-close.yml`
- `--demo` / mode-fallback noise in CLI dispatch

**Updated:**
- `docs/methodology.md` § 5.4 — rewritten as "Calculation (single
  path, v1.14+)" with Story Done + parent gate transitions
  explained together. Mode selector history noted.
- `plugin/skills/edpa-engine/SKILL.md` § 4 — single-path math; mode
  refs in JSON output schema example dropped.
- `plugin/edpa/templates/project.yaml.tmpl` governance: section —
  no calculation_mode/audit_mode; explanatory comment instead.
- `docs/kashealth-pilot/edpa.yaml.example` — same.
- `tests/test_invariants.py`, `tests/test_capacity_overrides.py`,
  `tests/test_gate_allocation.py` — all `mode=` kwargs and
  `--mode` subprocess args removed; tests renamed where mode-name
  was load-bearing.
- Web pages (calculator, dashboard, evaluation) still mention
  modes in narrative text — flagged for v1.14.x cosmetic patch.

**Verified:**
- 293/293 unit tests green
- `engine.py --demo` produces TEAM TOTAL = capacity, all invariants
  OK, no mode flag needed
- Sandbox engine run works via the new single-path CLI

Version bumped 1.13.0-beta → 1.14.0-beta.

## 1.13.0-beta — 2026-05-09

### Added: organization lookup helper

New script `plugin/edpa/scripts/lookup_org.py` fetches official
company data from public registries to fill
`project.organizations[]` in `.edpa/config/edpa.yaml` without manual
re-keying.

**v1.13 ships with one provider:** ARES (CZ) — https://ares.gov.cz
public REST API, no auth required. Returns: name, legal_name, tax_id
(ICO), vat_id (DIC), legal seat address, founded date, registry
status. Mockable for tests (no live API hits in CI).

**Pluggable provider model:** future country additions just register
a function that returns the standard dict shape:
```python
PROVIDERS["GB"] = lookup_uk_companies_house  # one line to register
```

CLI:
```bash
# Direct ID lookup
python3 lookup_org.py --ico 26350513
python3 lookup_org.py --country CZ --id 26350513

# Search by name
python3 lookup_org.py --search "Medicalc software"

# Output formats
python3 lookup_org.py --ico 26350513 --yaml      # YAML block to paste
python3 lookup_org.py --ico 26350513 --json      # full machine-readable

# Patch .edpa/config/edpa.yaml directly
python3 lookup_org.py --ico 26350513 --apply --org-index 1 --role partner
python3 lookup_org.py --ico 26350513 --apply --org-index 1 --yes  # CI
```

`--apply` preserves operator-set contact info (ARES doesn't carry
email/phone/website) and existing role values; replaces only identity
+ address fields. Pads organizations[] when --org-index is beyond
current length.

**Tests:** 30 unit tests (mocked HTTP) covering normalization,
formatters, --apply patching semantics (contact preservation, role
preservation, padding, missing config), provider registry contract.

**Docs:** new `docs/org-lookup.md` with full usage, ARES specifics
(sídlo vs operating offices, VAT status semantics), and steps to add
a future provider (UK Companies House, EU OpenCorporates, USA SEC
EDGAR).

Version bumped 1.12.0-beta → 1.13.0-beta. Codebase otherwise
unchanged from v1.12; install.sh fetches the new tarball
automatically.

## 1.12.0-beta — 2026-05-09

### Project schema enhancement (non-breaking — new fields, old keys ignored)

Refactors `plugin/edpa/templates/project.yaml.tmpl` (the file that
`install.sh` copies to `.edpa/config/edpa.yaml`) to make the project
metadata block more generic, internationally portable, and richer for
document generation.

**Old shape (v1.11 and earlier):**
```yaml
project:
  name: "..."
  registration: "..."          # grant-specific
  program: "..."               # grant-specific
  organizations:
    - name: "..."              # display name only
  domain: "..."
```

**New shape (v1.12):**
```yaml
project:
  name: "..."                  # display name (required)
  description: "..."           # NEW — free-text, replaces registration at top level
  domain: "..."                # optional URL
  funding:                     # NEW — optional block; drop if no external funding
    program: "..."
    registration: "..."
    period_start: ""           # NEW — YYYY-MM-DD
    period_end: ""             # NEW — YYYY-MM-DD
  organizations:
    - name: "..."
      legal_name: "..."        # NEW — full legal name
      role: "primary"          # NEW — free string (primary/partner/subcontractor/client/...)
      tax_id: ""               # NEW — generic (CZ: ICO, USA: EIN, UK: CRN)
      vat_id: ""               # NEW — generic (CZ: DIC, EU: VAT-ID, UK: VAT)
      address:                 # NEW
        street: ""
        city: ""
        postal_code: ""
        country: ""            # ISO 3166-1 alpha-2
      contact:                 # NEW
        email: ""
        phone: ""
        website: ""
```

**Why generic field names** (`tax_id` / `vat_id` instead of `ico` /
`dic`): EDPA is a generic product; CZ-specific terms in the schema
would force foreign users to misuse fields. Comment in the template
shows local-equivalent mapping.

**Why `funding:` is a separate block:** projects without external
funding just drop the block. Non-grant projects no longer carry
empty `registration:` / `program:` keys at top level.

**Backward compatibility.** Codebase reads only `project.name` from
this file (verified across `engine.py`, `board.py`, `mcp_server.py`,
`project_setup.py`). Old configs with `project.registration` /
`project.program` at top level keep working — the keys just sit
unused. New installs get the v1.12 layout from the template.

**Updated:**
- `plugin/edpa/templates/project.yaml.tmpl` — canonical template
- `docs/kashealth-pilot/edpa.yaml.example` — kashealth pilot example,
  filled with real ČVUT FBMI ICO/DIC/address; Medicalc placeholders
  for the partner organization's tax/contact details
- Version bumped to 1.12.0-beta in plugin.json, README badge,
  methodology doc, skill metadata, kashealth runbook
- 263/263 unit tests + 26-page web build remain green



### Single-source CW pipeline (BREAKING)

CW computation moved entirely from engine to detect_contributors.
The engine becomes a thin consumer of pre-computed `cw` values.
This fundamentally changes the meaning of `contributors[].cw` and
the calibration target — re-baseline required after upgrade.

**Architecture change.**
- `detect_contributors.py` collects all evidence signals (5
  auto-detected + 5 manual variants) and writes
  `contributors[].cw + signals[]` to backlog YAML.
- Engine reads `cw` directly. No `detect_evidence()`. No
  `compute_cw()`. No role-priority lookup. No RelevanceSignal.

**Schema migration (BREAKING).**
- `contributors[].as` field DROPPED (legacy `owner/key/reviewer/
  consulted` classifier). Role labels are derived at display time
  from signal types in reports.py / timesheets, not stored.
- `contributors[].cw` semantic CHANGED: was absolute [0,1] role
  weight, now per-item-normalized share (Σ across persons = 1.0
  per item).
- `contributors[].contribution_score` field ADDED — raw signal
  weight sum (input to per-item normalization).
- `contributors[].signals[]` field ADDED — full audit trail with
  `type`, `ref` (auditor-resolvable identifier), `weight`,
  optional `excerpt` (for `manual:*` types), `detected_at`.

**`/contribute` directive — additive signals.**
- Now parsed in 5 surfaces: PR body, PR comment, commit message,
  issue body, issue comment. Each emits `manual:<surface>` signal.
- Multiple directives stack additively (no override semantic).
- `as:role` clause silently dropped — role classification is gone.
- See `docs/contribute-directive.md` for usage patterns.

**Calibration target shrinks.**
- 11+ parameters → 5 parameters (5 signal weights only).
- `role_weights` and `role_overrides` matrices dropped from
  `cw_heuristics.yaml`. Strategic-role bias correction handled
  through signal weight tuning instead. v1.10 calibration data is
  NOT comparable; re-run `/edpa:calibrate` on v1.11.
- `gate_role_affinity` matrix also dropped (was an audit hint
  tied to the role taxonomy that no longer exists).

**Evidence threshold + RelevanceSignal removed.**
- The `evidence_threshold: 1.0` parameter is gone — per-item
  normalization makes thresholding meaningless (any positive
  signal contribution earns proportional cw).
- `--mode full` no longer differs from `--mode simple` in the
  formula; both credit `status: Done` items, full just adds
  richer audit metadata to the snapshot.

**Documentation.**
- Rewritten: docs/methodology.md § 5.3–6.5, docs/audit-trail.md,
  docs/evidence-detection.md, docs/auto-calibration.md.
- Added: docs/audit-references.md (canonical ref taxonomy +
  verification commands per signal type), docs/contribute-directive.md
  (manual override syntax + use cases).

**Snapshot incompatibility.**
- v1.10 and earlier snapshots are NOT directly comparable to
  v1.11. Re-run engine on archived backlogs to produce
  v1.11-compatible snapshots. No automated migration — clean cut
  per Q3 RFC decision.

**Released milestones consumed in v1.11.**
- Findings #1 (manual /contribute in PR body) and Finding #2 (dead
  evidence signals in engine) from v1.10.0-rc1 real-evidence E2E
  are both addressed by the architectural rewrite above.

### Fixed (post-1.10.0-rc1, real-evidence E2E)

- **`detect_contributors.py` now parses `/contribute @person weight:X
  [as:role]` directives from PR bodies.** Surfaced as Finding #1 in
  `docs/E2E-REPORT-2026-05-08-v1100-rc1-real-evidence.md`: previously
  manual attribution worked only from issue bodies (via `sync pull`),
  not from PR bodies, even though both surfaces invite users to write
  `/contribute`. Now the detect script fetches PR `body` via
  `gh pr view --json body`, parses `/contribute` lines, and applies
  them as authoritative overrides on top of auto-detected
  (`pr_author`, `commit_author`) attributions. The `as:role` clause is
  optional; when omitted, the role inherits from the auto-detected
  source. New entries created purely from a PR-body directive (no
  matching commit/author signal) get `source: pr_body:#N`; updates to
  existing detections record both signals as
  `source: <auto>+pr_body:#N` for full audit traceability.
- **`update_contributors()` honours manual `/contribute` overrides as
  authoritative.** Auto-detected updates still follow the
  v1.7+ "highest CW wins" merge rule, but a `pr_body:` source overwrites
  `cw`, `as`, and `source` regardless of relative magnitude — operator's
  explicit instruction beats any heuristic.
- **13 new unit tests** in `tests/test_detect_contributors.py` lock in
  the directive parser: edge cases (out-of-range weights, unknown
  roles, non-numeric weights, last-directive-wins, case-insensitive
  keyword and role, login formats with dashes/underscores, inline with
  surrounding text).

Verified end-to-end against the v1.10.0-rc1 sandbox PRs (#139..#148):
all 10 PR bodies' `/contribute` lines now flow into `contributors[]`
with the directive's `cw` value. Finding #2 (top-level
`pr_author`/`commit_authors`/`pr_reviewers`/`commenters` fields are
dead code in `detect_evidence`) is intentionally **not** addressed in
this fix — it's tracked separately as a v1.10.x cleanup decision
(remove dead branches vs. wire-through).

## 1.10.0-rc1 — 2026-05-08

Release candidate from `v1.10.0-beta` after a full pilot E2E
re-validation (`docs/E2E-REPORT-2026-05-07-v1100-beta-full-pilot.md`)
plus six paper-cut fixes. No new features vs. beta — same Stage 0
preflight, capacity-override prep step, and `edpa-results.xlsx`
consolidation. Promotion to stable is gated on the kashealth pilot
PI-2026-1.1 close on ~2026-05-13/14 with no further regressions.

### Fixed (post-1.10.0-beta E2E)

Six paper-cut issues surfaced by the full-pilot E2E. None blocked the
beta release but all closed before promoting to RC.

- **`sync.py` no longer crashes on empty `sync_state.json`**
  (`'NoneType' has no attribute 'get'`). Loads coalesce to `{}`; init
  path also catches 0-byte files left by older `install.sh` (`touch
  sync_state.json`).
- **`project_setup.py` field-create log distinguishes "already exists"
  from real failure.** Pre-fix every idempotent re-run printed
  misleading `✗ field-create failed` for fields that *did* land. Now
  matches stderr against "already been taken" / "already exists" and
  prints `(already exists)` instead.
- **`validate_syntax.py` allows `js: 0` for Initiative/Epic/Feature.**
  Strict validator was rejecting Initiatives that legitimately have no
  estimate at portfolio level. Story/Defect still require `js > 0`.
- **`backlog.py add` gains `--contributor PERSON:ROLE:CW` flag**
  (repeatable). Validates ROLE ∈ {owner,key,reviewer,consulted} and
  CW ∈ [0,1] before writing. Fixes the runbook examples that referenced
  a flag that didn't exist.
- **`project_setup.py` adds `--no-views` flag** for explicit views skip.
  Non-interactive auto-skip path now prints a louder `⚠` warning
  explaining Playwright requires interactive login on first run.
- **methodology.md + edpa-engine SKILL.md document `status: Done`
  requirement** for `simple` and `full` modes. Was a quirk noted only
  in source comments; now front-and-center in user docs as a
  three-mode comparison table.

## 1.10.0-beta — 2026-05-07

Skill-first gap closure + Excel workbook consolidation. Pays down
two structural debts surfaced during kashealth pilot prep. **Zero
new top-level skills** — extends `/edpa:setup` and
`/edpa:close-iteration` instead of multiplying ceremonies. RFC:
[`docs/proposals/v1.10-skill-first-gaps-and-excel-consolidation.md`](docs/proposals/v1.10-skill-first-gaps-and-excel-consolidation.md).

### Added

- **`plugin/edpa/scripts/preflight.py`** — Python port of the
  kashealth-pilot preflight shell with auto-fix offers and a public
  `run_preflight()` function. Checks toolchain, gh scopes,
  org access, member presence, Issue Types, `git config user.email`,
  Python modules, and (when `people.yaml` exists) cross-references
  declared github logins against org members.
- **`plugin/edpa/scripts/capacity_override.py`** — interactive
  helper for the v1.9.0 per-iteration `people:` override schema.
  Validates person-id against `people.yaml`, computes diff vs
  baseline, accepts absolute or `+N`/`-N` delta, prompts for audit
  note, runs `validate_syntax.py`, auto-commits with message
  `<iter>: capacity override <person> -> <hours>h (<note>)`.
- **`/edpa:setup` Stage 0** — preflight runs before any
  provisioning, blocks on ERROR. New flags: `--check-only` (Stage 0
  only, no provisioning), `--skip-preflight` (escape hatch for
  repeat runs), `--auto-fix` (apply offered fixes without
  prompting). Issue Types FAIL specifically offers
  `issue_types.py setup --org`. Eliminates the "setup fails with
  cryptic GraphQL error" path.
- **`/edpa:close-iteration` prep step** — interactive capacity
  override prompt before the engine call. Three argument forms:
  `<iter>` (full close: prep + engine + reports), `<iter> --prep-only`
  (record overrides without closing — for mid-iteration use, e.g.
  PTO declared Tuesday, close is Friday), `<iter> --skip-prep`
  (engine + reports only, for re-runs).

### Changed

- **Excel output consolidated** to a single `edpa-results.xlsx`
  per iteration with two tabs: `Team Summary` (per-person:
  Person, Role, FTE, Capacity, Derived, Items, OK + TOTAL row)
  and `Item Costs` (per-item-person: Item, Level, JS, Person,
  CW, Score, Ratio, Hours). Replaces the prior split of
  `summary.xlsx` + `item-costs.xlsx`. Pure code-shape refactor of
  `engine.py:write_excel` — same rows, one workbook.
- **`docs/kashealth-pilot/KASHEALTH-PILOT.md`** trimmed from 14
  sections (460 lines) to 8 sections (188 lines) as skill
  quick-reference. Full v1.9.0 form archived as
  `KASHEALTH-PILOT-detailed.md`.
- **`plugin/skills/edpa-reports/SKILL.md`** PI-rollup output
  description aligned with reality: `pi-summary-<id>.md` (the
  actual reports.py output) instead of the never-implemented
  `pi-summary.xlsx`.
- **Version bumped to 1.10.0-beta** in `plugin.json`, README badge,
  methodology doc, skill metadata.

### Why this release

Pilot kickoff prep revealed:

1. The kickoff runbook had 9 of 14 sections still calling
   `python3 .claude/edpa/scripts/...` directly — a gap inside
   existing skills, not a documentation problem. `/edpa:setup`
   failed with cryptic GraphQL error when org Issue Types were
   missing. There was no skill at all for capacity overrides
   (v1.9.0's flagship feature).
2. `summary.xlsx` and `item-costs.xlsx` were split across two
   `Workbook()` instances for no domain reason — auditor opens
   to aggregate, drills down to per-item, which is a single-file
   two-tab pattern.

Fixed by extending two existing skills with the necessary prep
and check stages, and refactoring engine's xlsx writer.

## 1.9.0 — 2026-05-07

## 1.9.0 — 2026-05-07

Stable release for the kashealth pilot kickoff (2026-05-07). Drops
the `-beta` suffix from 1.9.0-beta after a fourth consecutive E2E
run (`docs/E2E-REPORT-2026-05-06-v190.md`) confirmed 32/32 cumulative
findings PASS and the 260-test unit suite stayed green across the
B-fix breaking rename and the per-iteration override rollout.

This release is what kashealth/kas-platform-v1 will install
tomorrow per `docs/KASHEALTH-PILOT.md` § 12. No code changes vs.
1.9.0-beta — only the version string in plugin.json, README,
methodology, templates, skills, the E2E test plan, and the pilot
runbook. Backlog YAMLs, iteration overrides, snapshot signature,
and the install.sh fetch path are byte-identical to 1.9.0-beta.

## 1.9.0-beta — 2026-05-06

Adds per-person, per-iteration capacity overrides — the missing piece
for IP iterations with crunch hours, vacations, sick leave, and any
other one-off schedule deviation that doesn't belong in
people.yaml's permanent baseline.

### Added
- **Iteration-level `people:` overrides.** An iteration YAML
  (`.edpa/iterations/<id>.yaml`) may now carry a top-level `people:`
  block reusing the same schema as `people.yaml`. Engine matches
  entries by `id` and overrides `capacity_per_iteration` (or the
  legacy alias `capacity`) on top of the baseline declared in
  people.yaml. An optional `note:` is preserved through the snapshot
  and reports for audit. Example:

  ```yaml
  iteration:
    id: PI-2026-1.3
    ...
  people:
    - id: bob-dev
      capacity_per_iteration: 44
      note: "IP weekend deploy push (Jun 13-14)"
    - id: alice-arch
      capacity_per_iteration: 10
      note: "vacation Jun 9-11 (3 days PTO)"
  ```

  - `engine.run_edpa()` gained `edpa_root=` and `iteration_id=` kwargs;
    when both are passed it loads `iteration.people[]` overrides and
    surfaces `capacity_baseline` + `capacity_override` on each person
    result. Pre-1.9 callers (no iteration_id) still work — every
    person uses people.yaml baseline only.
  - `validate_syntax.py` recognises the iteration `people:` schema and
    hard-fails on unknown person id, duplicate entries, missing id,
    no override fields, or negative capacity. Backward-compat alias
    `validate_capacity_overrides` re-exports
    `validate_iteration_people_overrides` so older callers keep working.
  - Snapshots persist `capacity_baseline` + `capacity_override`
    (with `note`) when an override applied; absent fields keep
    pre-1.9 snapshots byte-identical (preserves the L6 dedup behaviour).
  - `reports.py` per-person timesheet shows `(baseline 40h, override
    abs 44h (+4h vs baseline 40h) ("IP weekend deploy push"))` when
    an override is active; team rollup gains an `Override` column the
    moment any iteration entry has overrides applied.

  Why iteration `people:` rather than a separate `capacity_overrides:`
  block (the original RFC shape): reuses an existing schema users
  already know, no new vocabulary. Trade-off accepted: the audit
  reason is downgraded from required `reason:` to optional `note:`,
  with `validate_syntax` enforcing that an override entry must touch
  at least one of capacity/note (otherwise it's a no-op typo).

- 15 new unit tests in `tests/test_capacity_overrides.py` covering:
  override applied, PTO override, person-without-override unchanged,
  no-override no-op, note-only audit annotation, negative capacity
  rejected, invariant holds with overrides, validator: unknown
  person / duplicate id / missing id / empty override entry /
  negative capacity / clean override / note-only override, snapshot
  persistence shape.

- `docs/proposals/per-iteration-capacity-overrides.md` — the original
  RFC; v1.9.0 implementation pivoted from `capacity_overrides:` to
  iteration `people:` based on review feedback (simpler, reuses
  existing schema). RFC retained for design history.

## 1.8.1-beta — 2026-05-06

Patch release closing the one new finding (N1) and one UX gap (N2)
caught by the v1.8.0-beta E2E re-validation
(`docs/E2E-REPORT-2026-05-06-v180.md`).

### Fixed
- **`sync.cmd_conflicts`** referenced a non-existent
  `parse_remote_items()` helper introduced in the F10 fix. Real
  function name is `map_gh_items_to_edpa(gh_data, fields_mapping)`.
  Same-field conflict detection raised `NameError` as soon as
  `gh_fetch_project_items` returned data; now flags conflicts
  cleanly with the live-diff augmentation message. (E2E v180 N1)

### Added
- **Auto-commit of EDPA-managed setup state.** New
  `plugin/edpa/scripts/_auto_commit.py` helper used by:
  - `project_setup.py` STEP 9b — commits `.edpa/config/edpa.yaml`,
    `.edpa/config/issue_map.yaml`, and `.edpa/iterations/` once the
    new project IDs / field IDs / option IDs are persisted.
  - `sync push` — commits `issue_map.yaml` updates after creating
    issues (and any field changes that landed on `edpa.yaml`).
  - `sync setup-refresh` — commits the recovered state.

  Each command takes `--no-commit` to opt out (useful for CI flows
  that want to inspect the diff before committing). The helper
  uses `git add <specific paths>` + `git commit -- <paths>` so
  unrelated work-in-progress in the working tree stays
  uncommitted; auto-commit silently skips when:
  - the directory is not a git repo,
  - the user has no `user.name` / `user.email` configured,
  - the targeted paths match HEAD.

  Closes E2E v180 N2 — sandboxes that ran setup, made an unrelated
  PR, then merged + pulled were silently losing the project IDs
  to a conflict-free `git pull --ff-only` against a HEAD that had
  the pre-setup `edpa.yaml`. The state now lives in git from the
  moment it's known to be useful.

## 1.8.0-beta — 2026-05-06

Closes all 18 findings from the 2026-05-06 E2E test
(`docs/E2E-REPORT-2026-05-06.md`) plus a follow-up cleanup of the
`contributors[].role` key. Minor-bumped from 1.7.0 because the
contributors schema rename is breaking — see "Breaking" below for
the one-shot migration command. Six findings were critical — engine
silently allocating 0h on a schema mismatch, project_setup
duplicating projects/issues on rerun, missing typed Status
field_ids on first run — and the rest were ergonomic gaps the
test plan documented but the scripts didn't deliver. Six
low-priority cleanups fix snapshot revisioning, --until parser
parity, per-iteration YAML bootstrap, GraphQL extension of the
Iteration field on rerun, the snapshot.frozen_at field, and an
explicit README example of the contributors schema.

### Breaking
- **`contributors[].role` → `contributors[].as`** in every YAML
  under `.edpa/backlog/`. The old key collided with
  `people[].role` (job role like Dev/Arch/QA/PM) and made every
  read of the two files require domain-switching in the reader's
  head. The new key has no alias on the engine or validator — a
  legacy YAML hard-fails with `validate_syntax.py` and is skipped
  by `engine.py load_backlog_items` with a migration breadcrumb.
  `contributors[].weight` is renamed to `contributors[].cw` for
  the same reason (one canonical key, no alias). One-shot fix:
  `python3 .claude/edpa/scripts/migrate_contributors.py`. The
  script also translates common job-role labels (architect /
  developer / QA / PM / product_owner) to their nearest evidence
  role (key / owner / reviewer / consulted) so the migration is a
  single command on existing backlogs.

### Fixed
- **`engine.py`** validates contributor schema and surfaces it
  loudly. `load_backlog_items` now warns per-item when
  `contributors[].as` is not in the evidence enum
  (owner|key|reviewer|consulted) or `cw` is missing, and prints a
  summary `WARN: 0 evidence pairs derived from N contributor
  entries` when nothing produced evidence. Top-level `body` and
  `assignees` preserved on the way to evidence detection. Legacy
  `role:` / `weight:` keys are rejected — see Breaking section.
  (E2E F14, F16)
- **`project_setup.py`** is idempotent. Reuses an existing project
  on exact title match (gh project create silently lets duplicate
  titles through), reuses existing issues by title on rerun, skips
  fields that already exist instead of erroring on "name already
  taken", and now retries the post-create field-list refresh up to
  six times so all four typed Status fields persist on first run
  (the eventual-consistency window that previously cost
  Initiative Status / Story Status). Final summary distinguishes
  created vs reused. (E2E F2, F3, F4)
- **`_sub_issue_linker.py`** treats "duplicate sub-issues" /
  "may only have one parent" as idempotent success so a rerun
  reports the existing links instead of `Links: 0`.
- **`issue_types.py`** uses `issueTypeId` on
  `UpdateIssueTypeInput` (the deprecated `id` argument now hard-
  fails). Description-update path works again. (E2E F1)
- **`sync.py conflicts`** augments the changelog-based detection
  with a live diff against GitHub. Same-field conflicts that
  skipped the changelog (direct GH UI / API edits) are now flagged
  as long as the local YAML was touched since `last_pull`. Falls
  back gracefully when gh fetch fails. (E2E F10)
- **`transitions.py`** tracks `.edpa/backlog/stories/` so story
  status changes show up in CLI output and engine gate audit;
  engine `load_gate_events` skips Story-level transitions to keep
  the existing "Story credited at Done only" semantics. (E2E F13)

### Added
- **`reports.py`** — batch generator for per-person timesheets and
  PI summaries. `python3 .claude/edpa/scripts/reports.py
  PI-2026-1.1` reads `edpa_results.json` and emits
  `timesheet-<id>.md` per person plus `timesheet-team.md`. `--pi`
  aggregates iteration results under a PI prefix. The
  /edpa:reports skill no longer needs a Claude session in the
  loop. (E2E F17)
- **`validate_syntax.py`** schema check for backlog YAMLs under
  `.edpa/backlog/`. Verifies required fields per type, status
  enum (portfolio vs delivery + legacy), id-prefix matching,
  js > 0, contributors structure. Contributors role mismatch is
  a warning by default (existing rich-doc backlogs use
  human-readable role labels for documentation); `--strict`
  upgrades it to an error. Stdin mode (`- --kind yaml`) and
  `--strict` flag added. (E2E F5, F6, F12)
- **`detect_contributors.py`** CLI / audit modes. `--pr <N>` and
  `--item <ID> --since 7days` work without `PR_NUMBER` so users
  can re-credit contributors offline. `--dry-run` shows changes
  without writing YAML. (E2E F7)
- **`transitions.py --since`** accepts relative durations
  (`1day`, `2weeks`, `3months`) in addition to ISO YYYY-MM-DD.
  Bad values produce a clear error message pointing at both
  formats. (E2E F9)
- **`evaluate_cw.py --check-readiness`** — exits 1 with a clear
  "Insufficient ground truth (X < 20 records)" message when the
  ground_truth.yaml is too sparse to start auto-calibration;
  exits 0 with "Ready: ..." otherwise. The locked evaluation
  logic is unchanged — readiness is a gate, not a new objective
  function. (E2E F18)
- **`project_setup.py`** Iteration field now collects iteration
  tags from backlog items, not just `.edpa/iterations/*.yaml`.
  Stories tagged `PI-2026-1.1` no longer fail every push with
  `[failed: no option_id for Iteration:PI-2026-1.1]`. When the
  Iteration field already exists on rerun, missing options are
  appended via `updateProjectV2Field` GraphQL mutation (replacing,
  with the existing option IDs round-tripped, so the call is
  effectively additive); we fall back to the previous
  "edit via UI" advice when the GraphQL endpoint is unavailable. (E2E F8, L2)
- **Engine snapshots** carry `frozen_at` (UTC ISO timestamp at
  write time) alongside the existing `generated_at` (engine
  compute time). Snapshot revisioning now compares a
  `payload_signature` (sha256 over content excluding timestamps)
  against the canonical `PI-X.Y.json`; identical reruns refresh
  `frozen_at` in place rather than producing `_rev2/_rev3/_rev4.json`
  proliferation. (E2E L1, L6)
- **`transitions.py --until`** accepts the same relative formats as
  `--since` (`1day`, `2weeks`, `3months`), so back-fill audits like
  `--since 2weeks --until 1day` work without computing dates by
  hand. (E2E L4)
- **`project_setup.py` bootstrap** — when `iterations/` is empty,
  setup now writes both the PI-level stub *and* the per-iteration
  `PI-X.Y.{1..N}.yaml` files (delivery + IP) in the format
  `transitions.py` expects (`iteration:` mapping with start/end).
  Previously a fresh project couldn't compute gates because
  `parse_iteration_dates` had no per-iteration windows to read. (E2E L5)
- **README** + `people.yaml.tmpl` ship an explicit "Backlog Item
  Schema" example that calls out `contributors[].as` ∈
  {owner, key, reviewer, consulted} and `cw`, so the F14/F16
  silent-0h failure mode is now documented up front. (E2E L3)

## 1.6.4-beta — 2026-05-06

### Added
- **`_sub_issue_linker.py`** — shared helper for the GraphQL
  `addSubIssue` mutation. `project_setup.py` STEP 8 (initial bulk
  link) and `sync.py push` (incremental link) now share one
  implementation. The mutation is idempotent — "already a sub-issue"
  is treated as success so re-runs on a partially-synced project
  are safe.
- **Optional auto-create of GitHub Project views.** New STEP 10 in
  `project_setup.py` prompts the maintainer ("Configure standard
  views now? [Y/n]"). On yes, runs `create_project_views.py`. On
  failure prints a warning and continues — non-fatal. New
  `--non-interactive` flag skips the prompt for CI / scripted runs.

### Changed
- **`/edpa:setup` skill explicitly forbids flat issue lists.** Real
  testing on 2026-05-06 surfaced that the wizard could be tricked
  into producing a flat backlog when items were created via
  `gh issue create` directly or by writing `.edpa/backlog/**/*.yaml`
  by hand. Skill now requires `backlog.py add` per item (which
  enforces `--parent`), then a single `sync push` at the end.
  `gh issue create` bypass is called out as forbidden in the skill
  body.

### Fixed
- N/A — Phase 1 fix is purely instructional.

## 1.6.3-beta — 2026-05-06

### Fixed
- **collaborators-sync workflow installs ruamel.yaml.** v1.6.2 fixed
  the workflow syntax but the `Install Python deps` step still only
  pip-installed `pyyaml`. The first run after the fix exited with
  `ERROR: ruamel.yaml required for round-trip writes` because
  `sync_collaborators.py` now imports it at startup. Workflow now
  installs both: `pip install pyyaml ruamel.yaml`. Both copies
  (live + shipped) updated in lockstep.

## 1.6.2-beta — 2026-05-06

### Fixed
- **collaborators-sync workflow no longer rejected by GitHub.** The
  v1.6.1 attempt added `permissions: { members: read }`, but that
  scope does not exist for GitHub Actions — the parser returned
  HTTP 422 on workflow_dispatch and the workflow file shipped
  broken. Replaced with the PAT-secret approach the TODO already
  flagged as the fallback: `GH_TOKEN: ${{ secrets.COLLAB_SYNC_TOKEN
  || secrets.GITHUB_TOKEN }}`. Without the secret the workflow
  uses the default token (direct collaborators only). Set
  `COLLAB_SYNC_TOKEN` (PAT with `repo` + `read:org`) to cover org
  members and pending invitations.

## 1.6.1-beta — 2026-05-06

### Fixed
- **collaborators-sync workflow now sees team-granted access.** Both
  `.github/workflows/collaborators-sync.yml` and the shipped copy in
  `plugin/edpa/workflows/` add `permissions: { members: read }` so the
  default `GITHUB_TOKEN` covers org members and pending invitations,
  not just direct collaborators. Live PR #20 on technomaton/edpa
  surfaced this — it picked up 2 of 5 collaborators because the
  default token's scope was narrower than the maintainer's local
  `gh auth`. (PAT-secret fallback for SAML-locked orgs is filed in
  TODO.md as v1.6.x patch material — open it only if `members: read`
  proves insufficient in production.)
- **people.yaml comments survive the sync.** `sync_collaborators.py`
  now uses `ruamel.yaml` round-trip for the read-modify-write cycle
  instead of `yaml.safe_dump()`. The first PR run wiped the
  `# EXAMPLE DATA — replace with your team when deploying` banner;
  this patch keeps comments, blank lines, key order, and quoting
  style on entries the sync did not touch.

### Added
- `ruamel.yaml` as a runtime dependency (`requirements.txt`,
  `install.sh` checks). Adds ~120 KB; pure-Python.

## 1.6.0-beta — 2026-05-06

### Added
- **GitHub-aware people pipeline.** The `github` field on `people.yaml`
  entries is now uniformly handled across the toolchain:
  - `_people_loader.py` (new): canonical loader, `display_handle()`
    (`@login` fallback to id), `avatar_url()`, plus `validate_people()`
    that flags assignees with no github login, unknown assignees,
    and unused people-registry entries.
  - `mcp_server.edpa_validate` now merges iteration + people
    diagnostics. The PostToolUse hook surfaces both whenever the
    user edits `.edpa/iterations/*.yaml` or `.edpa/config/people.yaml`.
  - `mcp_server.edpa_people` returns the `github` field so the
    assistant sees who has a login attached.
  - `backlog.py` renders `@github_login` for assignees in tree, show,
    and iteration views (falls back to internal id).
  - `board.py` uses `github.com/{login}.png` avatars on cards and
    filter chips when a login is on file; colored-initials fallback
    otherwise.
  - `edpa_commit_info.resolve_person()` learns two new match
    priorities: GitHub noreply email (`login@users.noreply.github.com`
    and the `id+login@…` privacy form) and `git user.name` literally
    matching a github handle. Web-UI commits now route to the right
    person.
- **Collaborator → people.yaml sync.** `sync_collaborators.py`
  (new) diffs the repository's GitHub collaborator list against
  `people.yaml`. Strategy "D" (asymmetric):
  - Removed collaborators → `availability: unavailable` (factual,
    no human input needed; auto-committed by the workflow).
  - New collaborators → auto-filled stub via PR for review (login,
    public name, public email pulled from `gh api users/{login}`;
    role/team/FTE/capacity left blank for the maintainer).
  Wired up as `.github/workflows/collaborators-sync.yml` (member
  added/removed/edited events + `workflow_dispatch`), the
  `/edpa:sync-people` skill (manual trigger), and a read-only MCP
  tool `edpa_sync_people` that reports the diff without writing.

### Changed
- `plugin/skills/edpa-setup/SKILL.md` template now includes the
  `github` field with an explicit "ASK user, never invent"
  instruction. Closes a real failure observed on 2026-05-06 where
  the wizard hallucinated GitHub logins from the admin's email
  pattern.

### Fixed
- _(none — Phase 1's defensive `gh project field-list` retry already
  shipped in 1.5.0-beta)._

## 1.5.0-beta — 2026-05-06

### Changed (BREAKING)
- **PI/iteration schema migration.** `pis[]` is no longer stored in
  `.edpa/config/edpa.yaml`. The canonical source is now
  `.edpa/iterations/`:
  - `PI-{year}-{n}.yaml` carries PI-level metadata (status,
    `iteration_weeks`, `pi_iterations`, `start_date`, `end_date`).
  - `PI-{year}-{n}.{m}.yaml` carries per-iteration plan and delivery.
  Per-iteration files use ISO `start_date`/`end_date` plus an explicit
  `weeks` override; the legacy Czech `dates: "D.M.–D.M.YYYY"` string
  and the `cadence: "2/10"` shorthand have been removed. `weeks` is
  reconciled against the date range; declared/derived mismatch is an
  error surfaced through `edpa_validate` and the PostToolUse hook.
- `edpa_iterations` MCP response is now `{iterations: [...], warnings?: [...]}`
  instead of a bare list. `edpa_status` replaces `active_iteration_dates`
  with separate ISO `active_iteration_start`/`_end` fields and adds a
  top-level `warnings` field when the loader detects schema drift.

### Added
- `derive_pis()` runtime loader (`plugin/edpa/scripts/_pi_loader.py`)
  reconstructs the PI list at runtime, validates continuity (no date
  gaps/overlaps; weekend bridging tolerated), and reconciles
  declared vs. derived weeks. 30 unit tests cover every diagnostic.
- `edpa_validate` MCP tool + `validate_iterations.py` CLI surface
  the loader's diagnostics for hooks, CI, and assistants.
- PostToolUse hook (`validate_on_save.sh`) now also runs the
  iteration validator whenever `.edpa/iterations/*.yaml` changes, so
  schema drift surfaces immediately on stderr (non-blocking).
- `project_setup.py` bootstraps a stub `iterations/PI-{year}-1.yaml`
  (1-week × 5 default cadence, status `planning`) when
  `iterations/` is empty, so the assistant has something to surface
  right after setup.

### Removed
- `config['pis'][*]` — both the field and every reader path. Legacy
  `config['pi']` (singular) fallback removed too. No migration shim:
  pre-1.5 projects that still ship `pis[]` should upgrade by moving
  iteration data into `iterations/*.yaml`.

### Fixed
- `project_setup.py` setup-refresh flow no longer crashes with
  `TypeError: the JSON object must be str, bytes or bytearray, not
  NoneType` when the GitHub ProjectV2 API returns 5xx mid-burst. The
  `gh project field-list` call retries once after a 2 s sleep and
  fails with a clear error message instead of `json.loads(None)`.
  Pre-existing bug surfaced by the v1.5 e2e run.

## 1.4.1-beta — 2026-05-06

Installer hot-fix on top of [v1.4.0-beta](https://github.com/technomaton/edpa/releases/tag/v1.4.0-beta).
Tag-only patch — engine, sync, MCP server, reports, and templates are
byte-identical. Only `install.sh` is materially different.

### Fixed
- `install.sh` now copies `plugin/edpa/workflows/*.yml` into the
  target project's `.github/workflows/` directory. Without this step
  the ten EDPA GitHub Actions (branch-check, contributor-detect,
  iteration-close, pi-close, sync-git-to-projects,
  sync-projects-to-git, traceability-check, validate-item,
  velocity-track, wsjf-calculate) sat unused inside
  `.claude/edpa/workflows/` because GitHub only runs files in
  `.github/workflows/`. Customers ended up with a half-functional
  EDPA install where PR branch checks, validation, and bidirectional
  sync workflows simply never fired.
- Safe defaults: only files that don't already exist get copied. A
  user with hand-edited workflows keeps the hand-edited versions; new
  workflows install without surprise overwrites. Set
  `EDPA_FORCE_WORKFLOWS=1` and re-run the installer to overwrite
  skipped files.
- Caught while reviewing the kashealth project's `.github/workflows/`
  directory on 2026-05-06 — six EDPA workflows were missing from
  what should have been a complete install.

### Verified live
Three install scenarios tested:
1. Fresh repo (no `.github/workflows/`) → 10 EDPA workflows installed.
2. Repo with custom `dispatch-hub-sync.yml` + a user-customized
   `branch-check.yml` → 9 installed, 1 skipped, the user's
   customization stays intact, the unrelated custom workflow stays
   too.
3. Same as #2 but with `EDPA_FORCE_WORKFLOWS=1` → all 10 installed,
   user customization gets replaced with the canonical version.

## 1.4.0-beta — 2026-05-05

Minor release. **Default cadence changes** for freshly initialized
projects only — existing `.edpa/config/people.yaml` files keep their
explicit `iteration_weeks` / `pi_weeks` settings; no migration is
required. The release also bundles every `## Unreleased` change since
1.3.2-beta (engine + plugin-wide hardening, MCP integration tests,
`sync add-iteration`, MCP load_yaml LRU cache, README walkthrough,
testing-strategy appendix).

### Changed (BREAKING for fresh installs only)
- **Default cadence is now AI-native: 1-week iterations, 5-week PI
  (4 delivery + 1 IP).** The IP iteration absorbs leftover work,
  debt, prioritization, and PI planning itself — compressible to a
  single day with AI-assisted ceremonies. Classic SAFe (2-week
  iteration / 10-week PI) is still fully supported; set
  `cadence.iteration_weeks: 2` and `cadence.pi_weeks: 10` in
  `people.yaml` to opt out. Default `capacity_per_iteration` values
  in the template halved accordingly (FTE × 40 for 1-week instead
  of FTE × 80 for 2-week).
- `project_setup.py` writes `pis[0].iteration_weeks: 1` for new
  setups (was `2`). Existing projects re-running setup keep their
  explicit value.
- Documentation updated: `docs/playbook.md`, `docs/quick-start.md`,
  `README.md` walkthrough show 1-week defaults with re-captured
  engine output (60h team total instead of 120h). The
  `docs/examples/capacity-small-team.yaml` reference is preserved
  as a classic-SAFe variant with a pointer to the new default.
- `mcp_server.py` legacy fallbacks (`iteration_weeks: 2` when the
  field is missing entirely from a v0.x bundled config) stay at
  `2` — they protect pre-1.0 installs from invariant breaks.

### Why this default

5-week PI matches AI-native team velocity better than 10 weeks. A
PM running CW analysis weekly produces tighter feedback loops than
biweekly; the gates allocation model (default since 1.1) was
already calibrated for high-frequency status transitions. The
classic-SAFe default predates EDPA's gates mode and the AI Studio
context — both push toward shorter cycles.



### Documentation
- `README.md` — replaced the terse 5-step Quick Start with a
  guided "First 5 minutes" walkthrough: install → edit `people.yaml`
  → seed a toy iteration + two stories → close iteration → generate
  timesheets. Every code block is copy-pasteable; every output
  block is real (captured from a fresh `/tmp` install end-to-end,
  not hand-edited). Reads like a tutorial; the older "see RUNBOOK.md
  for X" pattern still works as the next-step list at the bottom.
  Acceptance criterion from `TODO.md`: someone can read just the
  walkthrough and produce a working toy iteration on a fresh repo.
  Verified.

### Performance
- `mcp_server.load_yaml` — bounded LRU cache keyed by `(path,
  st_mtime_ns)`. Cap: 64 entries. Repeated MCP `tools/call`
  invocations against an unchanged `.edpa/backlog/` no longer
  re-parse every YAML file from scratch; touching a file
  invalidates only that entry. Measured on a 100-item backlog:
  cold 28.17 ms/call → warm 0.56 ms/call (≈ 50× speedup). The hot
  path inside a single Claude Code session — "what's in PI-X?"
  followed by repeated drill-down questions — was the explicit
  motivation. 6 new tests cover hit/miss, mtime invalidation,
  disappeared-file recovery, bounded eviction, LRU recency, and
  end-to-end handler benefit.

### Added
- `tests/test_mcp_integration.py` — 16 live JSON-RPC stdio roundtrip
  tests. Spawns `mcp_server.py` as a subprocess, drives the wire
  protocol Claude Code / Cursor / Codex use, asserts on serverInfo
  version, tool advertisement (5 tools), tool dispatch (status,
  item lookup, path-traversal rejection across 7 bad inputs), and
  stderr log discipline (INFO call_tool / WARNING rejected). Skipped
  on Windows and when `mcp` is missing. Default test marker — runs
  in the normal `pytest tests/` suite. Catches regressions where
  `Server(name, version=…)` upstream signature drifts, where the
  plugin path resolution breaks, or where the server crashes during
  initialize handshake.
- 155 tests pass (was 139 before this entry); 6 e2e deselected.
- `sync add-iteration <ID>` subcommand. After setup, when a new
  iteration YAML lands in `.edpa/iterations/`, the GitHub Project
  `Iteration` SINGLE_SELECT field doesn't know about it yet — `sync
  push` then fails with `no option_id for 'Iteration':'<ID>'`. The
  new subcommand fetches the field's current options, merges in the
  new one, calls `updateProjectV2Field` GraphQL mutation, and
  persists the new option_id back to `edpa.yaml`. Drops the `TBD`
  placeholder automatically when the first real iteration is added.
  Idempotent. `--color` (default GRAY), `--dry-run`. Verified live
  against `technomaton/edpa-e2e-test`: TBD purged, push of a story
  with `iteration: PI-2026-1.5` succeeded immediately after.
- Docs/RUNBOOK section updated.

### Changed (plugin-wide hardening pass — backport of v1.3 MCP rigor)
- `engine.py`, `sync.py`, `evaluate_cw.py`, and `pi_close.py` —
  `load_yaml` / `load_json` helpers now return `None` on failure
  instead of letting `OSError` / `yaml.YAMLError` /
  `json.JSONDecodeError` bubble up unhandled. Errors print to stderr
  so stdout (which downstream tools may parse) stays clean. Callers
  that already wrapped these in `try/except Exception` now check for
  `None` directly — same behavior, less catch-all.
- Replaced two `except Exception` blocks in `engine.py` with specific
  exception types. Same hardening pass MCP got in v1.3 —
  `KeyboardInterrupt` and `SystemExit` now propagate as they should.
- `validate_on_save.sh` hook — removed the `2>&1` stderr→stdout
  redirect that was making validation errors render as if they were
  tool output rather than diagnostics. Errors now stay on stderr;
  Claude Code shows them as diagnostics. Internal hook errors also
  surface on stderr now (were silently swallowed).
- Audit passes left two `except Exception` blocks in place:
  `mcp_server.call_tool` (intentional crash-safety wrapper around
  every JSON-RPC dispatch) and four in `create_project_views.py`
  (Playwright async patterns where any failure → fall through is
  the right shape). Both documented in code.
- 139/139 tests still pass.

## 1.3.2-beta — 2026-05-05

Surface fixes for `edpa_status` post-setup output. Caught in the
synthetic skill-driven E2E run as findings F3 and F4
(see `docs/E2E-SKILLS-TEST-PLAN.md`). Tag-only patch — engine,
sync, and reports are byte-identical.

### Fixed
- **F3** — `mcp_server._handle_status` read `project.name` from
  `people.yaml`, which has never had a `project:` section in any
  shipped template. Result: `edpa_status` always reported
  `"project": "unknown"` regardless of what `/edpa:setup` was given.
  Now reads from `edpa.yaml` (where the setting actually lives) and
  falls back to `people.yaml` only for legacy v0.x bundled configs.
- **F4** — `project_setup.py` persisted `sync.field_ids` and
  `sync.option_ids` after a successful setup but never wrote the
  matching `pis[]` array to `edpa.yaml`. Result: `edpa_status` and
  `edpa_iterations` reported `iterations_total: 0` immediately after
  setup, even though `.edpa/iterations/*.yaml` files were on disk
  the whole time. Setup now derives `pis[]` from those YAML files
  and writes them on the same persistence pass.
- `project_setup.py` also writes `project.name` from the
  `--project-title` argument when the template placeholder is still
  in place. Respects a name the user has set by hand.

### Verified live
Fresh setup → MCP `edpa_status` returns the actual project name,
`current_pi`, `iterations_total > 0`, and `active_iteration` — no
"unknown" fallbacks.

## 1.3.1-beta — 2026-05-05

Installer hot-fix on top of [v1.3.0-beta](https://github.com/technomaton/edpa/releases/tag/v1.3.0-beta).
Tag-only patch — engine, sync, MCP server, and reports are byte-identical.
Only `install.sh` is materially different.

### Fixed
- `install.sh` now installs the `mcp` Python SDK alongside `pyyaml`. Without
  this the MCP server (`plugin/edpa/scripts/mcp_server.py`) failed to start
  on a fresh `curl install.sh | sh` against the system python. The graceful
  import error in v1.3.0-beta said "ERROR: 'mcp' package required" and
  exited cleanly, but Claude Code clients silently fell back to `Bash + grep`
  because the MCP tools never advertised. Caught in the synthetic
  skill-driven E2E run on 2026-05-05; finding F1 in `docs/E2E-SKILLS-TEST-PLAN.md`.
- `install.sh` also installs `openpyxl` so the engine's Excel export and the
  `/edpa:reports` skill produce `item-costs.xlsx` and `pi-summary.xlsx`
  out of the box. Without it the engine printed "Excel export skipped" on
  every iteration close and reports lost the spreadsheet variant.

### Notes
- Both packages mirror the existing pattern: try `pip3 install ... --break-system-packages`,
  fall back to `pip3 install ...` for venv'd environments. No new system
  prerequisites — same Python 3.10+, same pip3 expectation.
- `web/public/install.sh` re-synced with the repo-root version (tracked
  drift from 2026-03-28 was fixed in 1.2.1; this release keeps them
  in lockstep).

## 1.3.0-beta — 2026-05-05

Production-quality MCP server. The server existed since 1.0.0-beta as a
prototype but had a relative plugin path, no input validation, no logging,
and unversioned identity. v1.3 makes it usable as a real Claude Code /
Cursor / Codex CLI tool surface against `.edpa/` data.

See `docs/mcp.md` for the full reference.

### Added
- `docs/mcp.md` — operator and integrator guide for the MCP server
  (tools, resources, env vars, security model, troubleshooting).
- `tests/test_mcp_server.py` grew from 36 to 48 tests:
  `TestItemIdValidation`, `TestCallToolErrorHandling`,
  `TestServerIdentity`, `TestLoggingSetup`. Live `subprocess` smoke
  test against the JSON-RPC stdio transport verified separately.

### Changed
- `plugin/.mcp.json` registers the EDPA server via
  `${CLAUDE_PLUGIN_ROOT}/edpa/scripts/mcp_server.py`. Previously a
  relative `.claude/edpa/scripts/mcp_server.py` path broke whenever
  the MCP client launched from a subdirectory.
- `plugin/.mcp.json` reads `GITHUB_PERSONAL_ACCESS_TOKEN` from the
  environment instead of shipping a literal empty string.
- `plugin/edpa/scripts/mcp_server.py`:
  - Server identity now carries the plugin version
    (`Server("edpa", version=…)`) read from `plugin.json`. MCP clients
    surface this in their connection panel.
  - Stderr `logging.Logger` named `edpa.mcp`; every `call_tool`
    invocation logged with arguments. `EDPA_LOG_LEVEL` and
    `EDPA_LOG_FILE` env vars control verbosity / mirroring. stdout
    stays clean for JSON-RPC.
  - `mcp` and `pyyaml` import errors exit with a one-line install
    hint instead of a stack trace.
  - `load_yaml` catches only `yaml.YAMLError` / `OSError`; bare
    `except` removed so `KeyboardInterrupt` propagates.
  - `call_tool` wraps every dispatch in a `try` so handler bugs
    return a `TextContent` `ERROR: internal error ...` rather than
    closing the JSON-RPC session.

### Fixed
- `edpa_item` accepted any string. A request like
  `{"item_id": "../etc/passwd"}` would skip the prefix lookup
  (returning "not found") rather than rejecting at the validator.
  Now `item_id` must match `^[A-Z]-\d{1,9}$`; anything else returns
  `ERROR: invalid item_id ...` before touching the filesystem.

### Dev tooling (carried from Unreleased)
- `requirements-dev.txt` now uses `-r requirements.txt` and adds
  `jsonschema` + `openpyxl` so a fresh `pip install -r
  requirements-dev.txt` runs the full test suite instead of
  silently skipping the schema-strictness and MCP groups.
- `pytest tests/ -m "not e2e"`: **139 passed**, 0 skipped, 0 errors
  (was 84 passed + 7 skipped + 1 collection error in 1.2.1-beta).
  The 6 e2e tests stay opt-in (real GitHub API, destructive
  to sandbox).
- `test_consistency.test_requirements_exist` now accepts a
  transitive `-r requirements.txt` include instead of demanding a
  literal `pyyaml` line in every requirements file.

## 1.2.1-beta — 2026-05-05

Installer hot-fix on top of 1.1.0-beta. No engine, sync, or report
changes — only `install.sh` is materially different.

### Fixed
- `install.sh` now seeds `.edpa/config/edpa.yaml` from
  `project.yaml.tmpl` alongside `heuristics.yaml` and `people.yaml`.
  Previously the template was bundled in `plugin/edpa/templates/` but
  never copied, so `engine --status` on a fresh install reported
  `✗ edpa.yaml not found` until `/edpa:setup` ran. No functional
  block — `setup` would still create the file — just a confusing
  onboarding hint.
- `install.sh` resolves the latest release with prerelease awareness.
  GitHub's `/releases/latest` API and `gh release download` without
  an explicit tag both skip prereleases, so while every release is
  `-beta` they returned 404 and the installer silently fell back to
  a `main` branch clone. The gh path now uses `gh release list
  --limit 1` to find the most recent tag (any release type); the
  curl path uses `/releases` (plural) and picks the first matching
  asset.

## 1.1.0-beta — 2026-05-05

### Changed (BREAKING for fresh installs only)
- **`--mode gates` is now the default** for `engine.py` and the
  `calculation_mode` field in `project.yaml.tmpl`. Existing
  `.edpa/config/edpa.yaml` files keep their explicit setting; only
  newly initialized projects pick up the new default. To stay on
  simple, set `governance.calculation_mode: simple` in
  `.edpa/config/edpa.yaml` or pass `--mode simple` on the command
  line.
- Validated against `technomaton/edpa-simulation-gates` (8 iterations,
  6-person virtual team, 156 git transitions, 30 Monte Carlo runs):
  avg MAD 7.8 % vs ground truth, 0.3 percentage points spread under
  ±20 % CW perturbation. See that repo's `reports/RESULTS.md` for
  the full validation report.

### Added
- `sync setup-refresh` subcommand — re-discovers field IDs, option
  IDs, and the issue map from an existing GitHub Project. Useful
  when checking out the project on a new machine or after manual
  GitHub edits.
- `tests/test_e2e_sync.py` — five end-to-end tests against a real
  GitHub sandbox repo (opt-in via `pytest -m e2e`). Covers the full
  chain: project setup → push creates issues → manual GitHub UI
  status change → pull updates YAML + commits → engine
  `--mode gates` reads the transition.
- `docs/RUNBOOK.md` — operational runbook for every `/edpa:*` slash
  command with prerequisites, expected output, common failure modes,
  and a 5-minute end-to-end smoke test.

### Fixed
- `project_setup.py` now persists `field_ids`, `option_ids`, and an
  `issue_map.yaml` so `sync push` can target real GitHub fields.
  Previously `gh project item-edit` was called with empty IDs.
- `sync push` works against a real GitHub Project: creates missing
  issues, sets fields with correct typing (NUMBER vs SINGLE_SELECT),
  mirrors status `→ Done` to `gh issue close`, and links parent/child
  via `addSubIssue`. Previously `push` was only validated against
  mock data.
- `sync pull` reads per-level typed status fields
  (Initiative/Epic/Feature/Story Status) instead of GitHub's default
  `Status` field, so SAFe workflow transitions actually round-trip.
- `project_setup.py` always creates the `Iteration` field (with a
  `TBD` placeholder option when no iteration YAMLs exist yet). Without
  this, every subsequent `sync push` of an item with `iteration:` set
  failed with `no field_id for 'Iteration'` and there was no recovery
  path short of recreating the project.
- `sync.compute_diff` no longer wipes a local `iteration:` value when
  the GitHub Project has no Iteration field or no value for the item.
  Previously every pull cleared local iteration tags whenever the
  field was lazily missing on GH.

## 1.0.0-beta — 2026-03-29

First public beta. Plugin-first distribution, restructured directories.

### Breaking Changes (vs internal v2.x)
- Installation via `curl -fsSL https://edpa.technomaton.com/install.sh | sh`
- All scripts moved: `scripts/edpa_engine.py` -> `.claude/edpa/scripts/engine.py`
- All config moved: `config/capacity.yaml` -> `.edpa/config/capacity.yaml`
- Heuristics renamed: `config/cw_heuristics.yaml` -> `.edpa/config/heuristics.yaml`
- Reports, snapshots, data moved under `.edpa/` prefix
- Claude Code skills/commands moved from `claude-code/` to `.claude/` (standard plugin location)

### Added
- `install.sh` — shell installer (detects `.claude/`, downloads release, copies plugin)
- `plugin/` directory — single source of truth for installable EDPA plugin
- **edpa-sync** skill — 5th skill for GitHub Projects <-> Git backlog synchronization
- `/edpa sync` command
- `plugin/.claude-plugin/plugin.json` — plugin manifest

### Changed
- Source reorganized: `plugin/` contains all installable assets (scripts, templates, workflows, skills, commands)
- `.edpa/` restructured: `config/`, `backlog/`, `reports/`, `snapshots/`, `data/`
- README, SETUP, CONTRIBUTING updated for new paths and installation method

### Removed
- GitHub template approach (`gh repo create --template`)
- `config/*.tmpl` files at repo root (moved to `plugin/edpa/templates/`)
- `scripts/` directory at repo root (moved to `plugin/edpa/scripts/`)

### Migration
| Old path | New path |
|----------|----------|
| `scripts/edpa_engine.py` | `.claude/edpa/scripts/engine.py` |
| `scripts/evaluate_cw.py` | `.claude/edpa/scripts/evaluate_cw.py` |
| `scripts/edpa_sync.py` | `.claude/edpa/scripts/sync.py` |
| `scripts/edpa_backlog.py` | `.claude/edpa/scripts/backlog.py` |
| `scripts/edpa_issue_types.py` | `.claude/edpa/scripts/issue_types.py` |
| `scripts/edpa_project_setup.py` | `.claude/edpa/scripts/project_setup.py` |
| `config/capacity.yaml` | `.edpa/config/capacity.yaml` |
| `config/cw_heuristics.yaml` | `.edpa/config/heuristics.yaml` |
| `config/project.yaml` | `.edpa/config/project.yaml` |
| `reports/` | `.edpa/reports/` |
| `snapshots/` | `.edpa/snapshots/` |
| `data/` | `.edpa/data/` |

## 2.0.0 — 2026-03-25

Multi-contract engine + role_overrides fix. **BREAKING CHANGE.**

### Breaking Changes
- Engine now applies `role_overrides` from `cw_heuristics.yaml` (was ignored in v1.x)
- CW values change for non-Dev roles: Arch reviewer 0.25→0.30, PM consulted 0.15→0.20, BO consulted 0.15→0.30
- Demo data: Alice split into alice-arch (40h) + alice-pm (20h)
- Person interface: new optional fields (`contract`, `evidence_scope`, `evidence_default`)

### Added
- `evidence_scope` per contract — route Git signals to correct contract via fnmatch patterns
- Multi-contract demo in `--demo` mode (Alice-Arch + Alice-PM)
- 3 new tests: `test_multi_contract_isolation`, `test_role_overrides_applied`, `test_evidence_scope_routing`
- `docs/migration-v2.md` — migration guide v1.x → v2.0
- TypeScript Person interface: `contract?`, `evidence_scope?`, `evidence_default?`

### Fixed
- **CRITICAL:** `role_overrides` from Monte Carlo calibration now applied in `compute_cw()`
  (was declared in config but ignored by engine since v1.0)

## 1.2.0 — 2026-03-25

Multi-role support + production readiness audit.

### Added
- Multi-role/multi-contract support: one person can have multiple entries with different roles, FTEs, and capacities (e.g., `urbanek-arch` + `urbanek-pm`)
- File-per-item backlog structure (`.edpa/initiatives/`, `epics/`, `features/`, `stories/`)
- `edpa_backlog.py add` command for creating new items from CLI
- `requirements.txt` (pyyaml) and `requirements-dev.txt` (pytest)
- Complete E2E playbook (`docs/playbook.md`, 1200+ lines)
- Production readiness audit fixes (score 73→90+)

### Changed
- Backlog: monolithic `backlog.yaml` → individual YAML files per item
- `.edpa/config.yaml`: hardcoded org → placeholder values
- Plugin version: 2.2.0 → 1.1.0 → 1.2.0
- Evidence principle documented: all commits are delivery evidence (no filtering)

### Removed
- `web/dist/` and `web/.vercel/` from git tracking
- Hardcoded GitHub Issue Type ID fallback

### Fixed
- `.gitignore`: added dist/, .vercel/, .env*
- Relative paths in Claude Code skill docs

## 1.1.0 — 2026-03-22

Migration from GitHub labels to native Issue Types. Branch `v1` preserves v1.0.

### Breaking Changes
- Work items now use **native GitHub Issue Types** instead of labels
- `edpa_project_setup.py` no longer creates Epic/Feature/Story/Initiative labels
- Project view filters changed from `label:Epic` to `type:Epic`
- Custom field "Issue Type" (SINGLE_SELECT) removed from Projects — redundant with native types

### Added
- `scripts/edpa_issue_types.py` — CLI for org-level Issue Type management (list, setup, assign, migrate)
- Native Issue Types on org: Initiative (PINK), Epic (PURPLE), Feature (BLUE), Story (GREEN), Defect (RED), Task (YELLOW)
- Enabler as label (SAFe classification: Business vs Enabler Epic/Feature/Story)
- `edpa_issue_types.py migrate` — bulk migration from labels to native types on existing repos
- `issue_types` section in `config/project.yaml.tmpl` and `.edpa/config.yaml`

### Changed
- `edpa_project_setup.py` — Issue creation uses GraphQL `updateIssueIssueType` instead of `--label`
- `edpa_sync.py` — `parse_gh_item_type()` reads native `issueType.name` first, labels as fallback
- `edpa_project_views.py` — view filters: `type:Epic`, `type:Feature`, `type:Story`
- `create_project_views.py` — same filter migration
- Default Bug type renamed to Defect via `updateIssueType` mutation
- Default Feature type description updated: "Musí se vejít do Planning Intervalu"
- Documentation: `github-project-setup.md`, `github-setup.md`, methodology pages (CS + EN)

### Removed
- Label creation for Initiative, Epic, Feature, Story, Bug in project setup
- Custom field "Issue Type" from GitHub Projects (native types replace it)

## 1.0.0 — 2026-03-21

EDPA v1.0.0 — first public release with calibrated CW heuristics.

### Added
- Public website at [edpa.technomaton.com](https://edpa.technomaton.com) (Astro, 14 pages, CS + EN)
- Interactive dashboard (generic + kashealth case study)
- 20-slide presentation (generic + kashealth)
- Full methodology documentation with sticky sidebar TOC
- Evaluation page: 302 verification checks (102 scenarios × per-person)
- Monte Carlo CW calibration (1000 scenarios, 68k records, p<0.001)
- Calibrated `role_overrides` in `cw_heuristics.yaml.tmpl`
- Git-native backlog management (`.edpa/backlog.yaml` + CLI)
- GitHub Projects ↔ Git sync (`edpa_sync.py` + GitHub Actions)
- SAFe 6 Epic Hypothesis Statements in backlog
- Full simulation repo ([edpa-simulation](https://github.com/technomaton/edpa-simulation))
- Simulation: 2 PIs, 10 iterations, 510 commits, realistic delivery variance (57-118%)
- Auto-calibration with Karpathy loop (MAD reduction 19.2%)
- Mobile hamburger menu, back-to-top button, ARIA accessibility
- Search/filter on evaluation page
- Responsive dashboard tables
- Vercel Analytics integration

### Changed
- Version: v2.2 → v1.0.0 across all files
- CW heuristics calibrated from Monte Carlo: reviewer 0.25→0.30, consulted 0.15→0.25
- Role-specific overrides: BO consulted 0.30, PM consulted 0.20, Arch reviewer 0.30
- TECHNOMATON Group → TECHNOMATON with link to technomaton.com
- Font sizes increased across website and presentation

## 0.0.1 — 2026-03-21

Initial open-source release as standalone repository (extracted from TECHNOMATON Hub).

### Added
- Standalone Python engine (`scripts/edpa_engine.py`) with `--demo` mode
- Claude Code skills: edpa-setup, edpa-engine, edpa-reports, edpa-autocalib
- Claude Code commands: `/edpa setup`, `/edpa close-iteration`, `/edpa reports`, `/edpa calibrate`
- GitHub Actions: branch naming check, iteration close workflow
- GitHub issue templates: Epic, Feature, Story
- Configuration templates: capacity.yaml, cw_heuristics.yaml, project.yaml
- CW evaluator for auto-calibration (`scripts/evaluate_cw.py`)
- Invariant validation tests (10 tests)
- Full documentation (11 docs)

### Origin
- Extracted from [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) `packs/tm-governance`
