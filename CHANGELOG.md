# Changelog

## Unreleased

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
