# EDPA — Skill-driven E2E Test Plan

End-to-end validation of EDPA V2 as customers experience it: through Claude
Code slash commands, skill orchestration, and MCP server tool calls — not
by invoking `engine.py`, `backlog.py`, or `project_setup.py` directly.

**Companion to** `docs/E2E-TEST-PLAN.md`. The script-level plan tests the
backend behavior; this plan tests the product surface — prompts, decision
points, MCP tool dispatch, error messages users actually see. Both must
pass for a release to be production-ready.

**Verze plánu:** 2.1.x (2026-05-31, EDPA V2 local-first)
**Pokrývá:** 5 skills (`edpa:setup`, `edpa:add`, `edpa:engine`,
`edpa:reports`, `edpa:calibrate`) + 4 slash commands
(`edpa:close-iteration`, `edpa:board`, `edpa:capacity`, `edpa:server`) + MCP server
(14 tools, 3 resource families).

> **V2 is local-first.** `.edpa/backlog/**/*.md` is the source of truth and
> git is the audit trail. There is **no** GitHub Project provisioning, **no**
> `gh project` orchestration, **no** org-level Issue Types, **no**
> `issue_map.yaml`, and **no** bidirectional `sync.py` — all removed in
> 2.0.0. GitHub is **optional**: the only GitHub touchpoint is the opt-in
> `--with-ci` contribution-sync workflow that materialises PR-thread signals.
> Consequently there is **no `/edpa:sync`** skill or command in this plan.

---

## 0. Why this exists

`docs/E2E-TEST-PLAN.md` runs the codebase as a developer does: bash
shell, direct Python invocation, manual `git`/`gh` calls. That is necessary
but **not sufficient**. EDPA's product surface is the
`/edpa:*` slash command set, the conversational orchestration each
skill performs, and the MCP server that lets the assistant query *and
mutate* `.edpa/` data structurally instead of via `Bash + grep` + hand-edited
YAML.

A script-level pass with a skill-level fail looks like this:
- `python3 .edpa/engine/scripts/backlog.py add --type Story ...` → exits 0 ✅
- `/edpa:add Story ...` from inside Claude Code → skill prompts the user
  for the wrong field name, invents an ID instead of allocating from
  `id_counters.yaml`, writes a Story with a bad parent, and never surfaces
  the validation failure → user thinks the item was created correctly when
  the hierarchy is broken ❌

This plan catches the second class.

---

## 1. Předpoklady

### 1.1 Toolchain (jednorázově)

```bash
# Confirm in your terminal, BEFORE entering Claude Code:
claude --version           # Claude Code CLI
git --version              # any modern git
python3 --version          # ≥ 3.10
python3 -m pip install -r requirements-dev.txt  # mcp + pyyaml + jsonschema + openpyxl
# gh is OPTIONAL — only needed for the --with-ci PR-signal phase (§ 5).
gh --version               # ≥ 2.40 (optional)
gh auth status             # scopes: repo (optional)
```

### 1.2 Sandbox

V2 setup is **local-first**, so no remote provisioning is required to run
most of this plan. A fresh, throwaway git repo is enough:

```bash
TARGET=$(mktemp -d -t edpa-skills-test-XXXX)
cd "$TARGET"
git init -q
echo "# skills test" > README.md
git add -A && git commit -qm "chore: init sandbox"
```

The optional PR-signal phase (§ 5) needs a GitHub remote
(`technomaton/edpa-e2e-test`, private) and an `EDPA_TOKEN` secret so the
`edpa-contribution-sync.yml` workflow can write back PR-thread signals.
Skip § 5 entirely if you only want to validate the local-first product
surface.

### 1.3 Plugin installed

```bash
cd "$TARGET"
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

Verify after install: `.edpa/engine/scripts/` (vendored engine),
`.edpa/config/{edpa.yaml,people.yaml,id_counters.yaml}`, plugin v2.1.x or
later. (`cw_heuristics.yaml` appears after `/edpa:setup` seeds it.)

### 1.4 Enter Claude Code

```bash
cd "$TARGET"
claude
```

**Every phase below assumes you are inside this session unless explicitly
noted.** Slash commands like `/edpa:setup` are typed *into the Claude
Code prompt*, not the shell.

---

## 2. Conventions for the rest of this document

| Notation                  | Meaning                                                        |
|---------------------------|----------------------------------------------------------------|
| `> /edpa:setup ...`       | What you type into the Claude Code prompt                      |
| `→ skill: edpa-X`         | Which skill should be invoked                                 |
| `→ MCP: edpa_status`      | Tool call the assistant should make against the EDPA MCP server |
| `→ Bash: python3 …`       | A Bash tool call the skill is expected to issue                |
| `[expect prompt]`         | Skill should ask the user for input here                       |
| `[expect artifact]`       | A file should appear at this path                              |
| `[pass]` / `[fail]`       | Acceptance / rejection criteria                                |

---

## Fáze 1 — Plugin loads, MCP server is reachable

**Goal:** Claude Code session loads the EDPA plugin successfully, MCP
server starts, all 14 tools are advertised.

### 1.1 Plugin discovery

Inside the Claude Code session:

```
> /help
```

**[expect]** `/edpa:setup`, `/edpa:add`, `/edpa:engine`, `/edpa:reports`,
`/edpa:calibrate`, `/edpa:server`, `/edpa:close-iteration`, `/edpa:board`,
`/edpa:capacity` appear in the slash command list. **No `/edpa:sync`** — it
was removed in 2.0.0.

### 1.2 MCP probe

```
> What EDPA MCP tools are available? List them and their inputs.
```

**[expect]** Assistant calls `→ MCP: list_tools` (not `Bash + grep`)
and reports the 14 tools:
`edpa_status`, `edpa_iterations`, `edpa_people`, `edpa_backlog`,
`edpa_item`, `edpa_validate`, `edpa_flow_metrics`, `edpa_item_create`,
`edpa_item_update`, `edpa_item_transition`, `edpa_item_link_parent`,
`edpa_iteration_create`, `edpa_iteration_close`, `edpa_people_upsert`.
The `edpa_item` tool requires `item_id`.

**[expect]** Assistant also reports `serverInfo: edpa v2.1.x` (or
later) — the version string the server returns at `initialize`. The
version is read from `plugin.json` (single source of truth), so it must
match the installed plugin.

### 1.3 Read-only smoke

```
> Show me the current project status using the EDPA MCP.
```

**[expect]** `→ MCP: edpa_status` (one tool call). Response is JSON-shaped
even though the actual `.edpa/config/edpa.yaml` is still the template
(project name "My Project", PI unknown). Assistant must not fall back to
`Bash + cat`.

**[pass]** All three checks above succeed without the assistant
shelling out for anything that's queryable via MCP.

**[fail]** Assistant uses `Bash + grep` / `Read` for data that has a tool;
or MCP version is older than the installed plugin; or fewer than 14 tools
advertised; or `/edpa:sync` shows up anywhere.

---

## Fáze 2 — `/edpa:setup`

**Goal:** The setup skill vendors the engine into `.edpa/engine/`, seeds
`.edpa/config/{edpa.yaml,people.yaml,cw_heuristics.yaml,id_counters.yaml}`,
and optionally installs hooks/CI/rules — all **local-first**. No GitHub
Project, no custom fields, no Issue Types, no `issue_map.yaml`.

### 2.1 First invocation

```
> /edpa:setup --with-ci --with-hooks --with-rules
```

**[expect skill: setup]**

**[expect prompt]** Setup is a write operation; the skill should narrate
what it is about to vendor/seed before doing it, or confirm the flag set.
It MUST NOT prompt for a GitHub org / repo / project title — those V1
inputs no longer exist.

**[expect Bash]** `python3 ${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py
--with-ci --with-hooks --with-rules`. The script first **vendors the engine**
(`scripts` + `schemas` + `templates` + `VERSION`) into `.edpa/engine/`, then
seeds the configs and `id_counters.yaml`.

What each flag does:
- `--with-ci` — copies `edpa-contribution-sync.yml` into
  `.github/workflows/` (the only GitHub touchpoint; materialises
  `pr_reviewer` / `issue_comment` PR-thread signals).
- `--with-hooks` — installs the git-hook stack into `.git/hooks/`:
  **pre-commit** (ID-safety: filename ≡ frontmatter `id`, counter
  monotonicity, HEAD collisions), **commit-msg** (require an EDPA item
  reference, or a `no-ticket:` escape), **post-commit**
  (`local_evidence.py` emits `commit_author` signals).
- `--with-rules` — copies `plugin/rules/*.md` into `.claude/rules/`.

The skill should narrate what it's doing — the assistant's chat history
should read like a setup log, not like a wall of bash output.

### 2.2 Edit the seeded configs

```
> Set the project name to "EDPA-Skills-Demo-<timestamp>" and replace the
  example team in people.yaml with example-arch + example-dev.
```

**[expect Edit/Write]** on `.edpa/config/edpa.yaml` (`project.name`) and
`.edpa/config/people.yaml`. These are user-owned config files — editing
them by hand (or via the assistant) is the intended path.

### 2.3 Persistence verification

After setup completes, verify via MCP (not by reading files directly):

```
> Confirm the EDPA setup is persisted: project name, team size, and that
  the engine is vendored.
```

**[expect MCP: edpa_status]** Returns project name, current_pi (possibly
"unknown" if no real iteration), team_size, etc.

**[expect MCP: read_resource edpa://config]** OR
`Bash: cat .edpa/config/edpa.yaml` — both acceptable to confirm the seeded
config.

**[pass]** `.edpa/engine/scripts/` exists (vendored engine, NOT
`.claude/edpa/scripts/`); `.edpa/config/{edpa.yaml,people.yaml,
cw_heuristics.yaml,id_counters.yaml}` all present;
`.github/workflows/edpa-contribution-sync.yml` present (because
`--with-ci` was passed); git hooks installed in `.git/hooks/`.

**[fail]** Any of: skill prompted for a GitHub org/repo/project title;
attempted `gh project create`; engine landed under `.claude/edpa/`;
`id_counters.yaml` missing; a `--with-X` flag silently no-op'd.

---

## Fáze 3 — Backlog creation through the assistant (`/edpa:add`)

**Goal:** Items are created through the `/edpa:add` skill, which allocates
IDs atomically from `id_counters.yaml`, validates the parent hierarchy via
`edpa_item_create`, writes the `.md` file under `.edpa/backlog/`, and
auto-commits `feat(<ID>): <title>`. No GitHub calls happen at create time.

### 3.1 Create an Initiative → Feature → Story chain

```
> /edpa:add Initiative "Skills E2E"
> /edpa:add Feature "Login flow" --parent <the I- id from above>
> /edpa:add Story "Implement login endpoint" --parent <the F- id> --js 5 --iteration PI-2026-1.1
```

**[expect skill: add]** for each.

**[expect MCP: edpa_item_create]** (or `Bash: python3
.edpa/engine/scripts/backlog.py add`). The ID is allocated from
`id_counter.next_id(type)` — e.g. `I-1`, `F-1`, `S-1`. The assistant must
**never invent IDs**.

**[expect Write]** of the `.md` file under the right directory:
`.edpa/backlog/initiatives/I-1.md`, `.edpa/backlog/features/F-1.md`,
`.edpa/backlog/stories/S-1.md`.

**[expect hook]** `validate_on_save.sh` fires on the `.md` write
("Validating syntax...") and passes. **[expect]** a git commit
`feat(<ID>): <title>` per item (auto-committed by the skill).

### 3.2 Parent-validation guard

```
> /edpa:add Story "Orphan story" --parent F-999
```

**[expect MCP: edpa_item_create]** rejects the unknown parent. The
assistant should surface the validation error (no such parent `F-999`) and
**not** write an orphaned Story.

### 3.3 Missing-Job-Size guard

```
> /edpa:add Story "No size yet" --parent F-1
```

**[expect]** the skill warns "Set Job Size for WSJF: re-run with
`--js <1-100>`" rather than silently writing a Story with no `js`.

**[pass]** IDs come from `id_counters.yaml` (never invented); hierarchy is
validated before write; each created item is auto-committed
`feat(<ID>): …`; bad parent and missing `--js` are surfaced to the user.

**[fail]** Assistant invented an ID; wrote a Story with a non-existent
parent; skipped the auto-commit; or wrote `.yaml` instead of `.md`.

---

## Fáze 4 — Backlog hygiene through MCP + validation hook

**Goal:** The assistant uses MCP for backlog discovery and transitions,
and the validate hook surfaces an error when a hand edit breaks the schema.

### 4.1 List backlog via MCP

```
> List every Story currently in the backlog with its status.
```

**[expect MCP: edpa_backlog with type=Story]** (one tool call, returns
all stories). Assistant must not `Bash: ls .edpa/backlog/stories/` and
read each `.md`.

### 4.2 Read one item via MCP

```
> Show me the full S-1 record.
```

**[expect MCP: edpa_item with item_id="S-1"]** Returns the full item
(frontmatter + body) as JSON.

### 4.3 Path-traversal safety

```
> Try fetching item ID "../etc/passwd" via the MCP tool. What happens?
```

**[expect MCP: edpa_item with item_id="../etc/passwd"]** Returns
`ERROR: invalid item_id ...` (logged server-side as
`edpa_item: rejected item_id='../etc/passwd'`). Assistant must explain
that the regex guard rejected the input.

### 4.4 Status change via the transition tool

```
> Move S-1 to Implementing.
```

**[expect MCP: edpa_item_transition]** (preferred) — this validates the
status against the Story state machine and auto-commits the transition,
which the engine later reads as a gate event. `Implementing` is valid for
a Story (`DELIVERY_STATUSES`).

### 4.5 Hand edit triggers the validation hook

```
> Edit S-2 directly: set status to "In Progress" (note: invalid for a
  Story — the validator should catch this).
```

**[expect Edit tool]** on `.edpa/backlog/stories/S-2.md`.

**[expect hook]** `validate_on_save.sh` fires
("Validating syntax..."). `validate_syntax.py` enforces the per-type
status enum; for a Story the delivery states are
`Funnel, Analyzing, Backlog, Implementing, Validating, Deploying,
Releasing, Done` — `In Progress` is **not** in that set, so it must be
flagged (`✗`/`⚠` line surfaced on stderr).

**[expect assistant]** sees the validation failure and tells the user. It
must not silently accept bad data.

**[pass]** All five behaviors above. Assistant prefers MCP tools over
filesystem grepping; transitions go through `edpa_item_transition`; bad
item ID is rejected; bad status edit is caught by the hook.

**[fail]** Assistant grepped instead of using MCP; path traversal returned
a file; an out-of-enum status was written without a hook warning.

---

## Fáze 5 — Optional: PR-signal contribution sync (`--with-ci`)

> **Optional phase — GitHub only.** Skip entirely if you are validating
> the local-first surface. There is **no `/edpa:sync`** in V2; the only
> GitHub integration is the opt-in contribution-sync workflow that
> materialises PR-thread signals (`pr_reviewer`, `issue_comment`) into the
> item YAML's `evidence[]`. Local `commit_author` signals flow regardless
> via the post-commit hook.

**Goal:** A PR that references a backlog item produces PR-thread evidence
that the engine can read on the next run.

### 5.1 Preconditions

- Sandbox repo has a GitHub remote and the `edpa-contribution-sync.yml`
  workflow installed (from `--with-ci` in § 2).
- An `EDPA_TOKEN` repository/org secret with `repo` scope is configured so
  the workflow can commit signal updates back.

### 5.2 Open a PR that references an item

```
> Create a feature branch for S-1, make a trivial change, commit
  referencing S-1, push, and open a PR.
```

**[expect Bash]** branch name like `feature/S-1-...`, commit subject
referencing `S-1` (so the commit-msg hook passes), PR opened.

### 5.3 Materialise PR-thread signals

The workflow normally commits PR-thread signals on `pull_request: closed`.
To refresh signals for an **open** PR (e.g. mid-iteration), run the
materialiser directly:

```
> Refresh the contribution signals for the open PR referencing S-1.
```

**[expect Bash]** `python3 .edpa/engine/scripts/sync_pr_contributions.py
--pr <PR_NUMBER> --rebuild` (add `--skip-commit` to write the YAML
in-process without a git commit). This writes `evidence[]` (reviewer /
comment signals) into the referenced item's YAML.

**[pass]** Reviewer/comment signals appear in the item's `evidence[]`; the
post-commit `commit_author` signal from § 5.2 is already present;
**no `gh project` calls** and **no custom-field pushes** anywhere.

**[fail]** Any attempt to provision a GitHub Project / Issue Types / custom
fields; `issue_map.yaml` written; the assistant looks for a `/edpa:sync`
command.

---

## Fáze 6 — `/edpa:capacity` (per-iteration overrides)

**Goal:** Non-baseline capacity (PTO, sick leave, overtime, onboarding
ramp) is recorded on the iteration so the engine's `Σ hours == capacity`
invariant reflects reality.

### 6.1 List current overrides

```
> /edpa:capacity PI-2026-1.1 list
```

**[expect Bash]** `python3 .edpa/engine/scripts/capacity_override.py
PI-2026-1.1 --list`. With no overrides yet, it reports baseline capacity
from `.edpa/config/people.yaml`.

### 6.2 Add an override

```
> /edpa:capacity PI-2026-1.1 set example-dev -12h "sick"
```

**[expect Bash]** `python3 .edpa/engine/scripts/capacity_override.py
PI-2026-1.1 --add --person example-dev --hours -12 --note "sick"`. The
override lands in the iteration YAML `people:` block and is auto-committed
with an audit message.

**[pass]** Override stored on the per-iteration file (not the person
baseline); reflected in `edpa_results.json` later as `capacity`,
`capacity_baseline`, `capacity_override`.

**[fail]** Override mutated `people.yaml` baseline; or was written to a
PI-level rollup instead of the `.<n>` iteration file.

---

## Fáze 7 — `/edpa:close-iteration`

**Goal:** Capacity prep + engine + reports run together via one command
invocation; the engine picks up the status-transition commits from earlier
phases. There is a **single calculation path** — the V1 `--mode
simple|full` flag was removed in 1.14.

### 7.1 Close all stories Done

Make sure every Story in `PI-2026-1.1` has `status: Done` (use
`edpa_item_transition`). Commit the transitions.

### 7.2 Close

```
> /edpa:close-iteration PI-2026-1.1
```

**[expect command flow]:**
- **Stage 1 (capacity prep)** — the command asks whether anyone had
  non-baseline capacity, driving `capacity_override.py` as needed (skip
  with `--skip-prep`, or for a PI-level id).
- **Stage 2a (optional, V2-only)** — if
  `.github/workflows/edpa-contribution-sync.yml` is installed, refresh open
  PRs via `sync_pr_contributions.py --pr <N> --rebuild --skip-commit` so
  their evidence is in the engine's view at close time.
- **Stage 2 (engine + reports)** —
  `python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration
  PI-2026-1.1`, then reports.

**Output narrative:**
- Engine summary: `TEAM TOTAL = capacity`, `All invariants passed: YES`
  (the `Σ hours == capacity` invariant). The engine is **evidence-driven**:
  it combines `commit_author` + `yaml_edit` + gate-transition signals,
  applies role weights (owner 1.0 / key 0.6 / reviewer 0.25 / consulted
  0.15, threshold 1.0), and derives per-person hours.
- Reports take over: per-person `timesheet-<person_id>.md`,
  `timesheet-team.md`, an `edpa-results.xlsx` export, a frozen snapshot,
  and `edpa_results.json` under `.edpa/reports/iteration-PI-2026-1.1/`.

### 7.3 Read results via MCP

```
> Use the MCP to fetch the engine results for PI-2026-1.1.
```

**[expect MCP: read_resource edpa://results/PI-2026-1.1]** Returns the
JSON contents of `edpa_results.json`. (This is one of the 3 MCP resource
families: `edpa://config`, `edpa://people`, `edpa://results/<iter-id>`.)

**[pass]** Engine invariants pass; report artifacts present under
`.edpa/reports/iteration-PI-2026-1.1/`; `edpa://results/...` resource
readable. No `--mode` flag appears anywhere.

**[fail]** Engine ran but reports were skipped; MCP resource missing for a
closed iteration; the command tried a `--mode simple|full` flag.

---

## Fáze 8 — `/edpa:reports`

**Goal:** Standalone report generation against an already-closed iteration.

### 8.1 Generate again

```
> /edpa:reports PI-2026-1.1
```

**[expect skill: reports]**

Skill should be idempotent — running twice should produce identical
artifacts (modulo timestamps): per-person `timesheet-<id>.md` for each
person with derived hours > 0, plus `timesheet-team.md`.

### 8.2 PI summary

```
> /edpa:reports pi PI-2026-1
```

**[expect skill: reports]** Aggregates all closed iterations in the
PI into `pi-summary-PI-2026-1.md`.

**[pass]** Each invocation produces the right artifact; the skill
recognizes both the iteration-id and `pi <PI-ID>` argument forms.

**[fail]** Skill defaults to "list everything" instead of acting on the
argument; or it expects engine results to be missing and re-runs the
engine instead of just rendering.

---

## Fáze 9 — `/edpa:board`

**Goal:** A visual Kanban board renders from local `.edpa/backlog/` items.

```
> /edpa:board
```

**[expect command: board]**
**[expect Bash]** `python3 .edpa/engine/scripts/board.py --open`.

**[pass]** An HTML board file is produced (default location, or the path
the skill reports) and the item count is reported. Columns reflect the
local statuses (e.g. a `Done` column for items with `status: Done`).

**[fail]** Board reads from a remote GitHub Project (it must not — there
is none); or fails because it can't find `.edpa/backlog/`.

---

## Fáze 10 — `/edpa:calibrate` (CW signal weights)

**Goal:** The auto-calib skill optimizes CW signal weights against a
**synthetic Monte-Carlo corpus** — runnable any time, no ground-truth file
required.

> V1 behaviour removed: the old "refuse until ≥ 20 ground-truth records"
> gate is gone. The optimizer is self-contained — `calibrate_signals.py`
> generates its own corpus procedurally and uses MAD on that corpus as the
> single metric. The only legitimate refusal is the not-yet-implemented
> **real-data adapter**.

### 10.1 Synthetic run (preview)

```
> /edpa:calibrate
```

**[expect skill: autocalib]**

**[expect]** the skill describes the run against
`plugin/edpa/templates/cw_heuristics.yaml.tmpl`: a baseline MAD, the
two-phase method (MC random-sample → coordinate descent), and a proposed
calibrated weight set — without applying changes. It must NOT claim it
needs `.edpa/data/ground_truth.yaml`.

### 10.2 Apply

```
> /edpa:calibrate apply
```

**[expect Bash]** `python3 plugin/edpa/scripts/calibrate_signals.py
--apply`. Reports `baseline MAD → calibrated MAD (+X%)` and writes the
tuned weights into `cw_heuristics.yaml.tmpl`. A `+0.0%` improvement is an
acceptable outcome (shipped defaults already near-optimal), not a failure.

### 10.3 Real-data adapter (out of scope today)

```
> /edpa:calibrate using our real PI corrections
```

**[expect refusal]** "Real-data calibration adapter not yet implemented.
Run the synthetic MC pipeline first." This is the ONLY refusal the skill
should produce.

**[pass]** Synthetic run works without any ground-truth file; `apply`
tunes `cw_heuristics.yaml.tmpl`; only the real-data path is refused.

**[fail]** Skill refuses the synthetic run for lack of ground truth (a V1
regression); or it edits `calibrate_signals.py` (must never happen — the
corpus generator and cost function are locked inside it).

---

## Fáze 11 — `/edpa:server` (optional PI-planning HTTP server)

**Goal:** The experimental V2 PI-planning server starts, reports status,
and stops — proxying all reads/writes through the EDPA MCP server (single
source of truth). Off by default.

```
> /edpa:server status
> /edpa:server start
> /edpa:server status
> /edpa:server stop
```

**[expect command: server]** Reports not-running, then starts on
`localhost:3001`, then running, then stopped.

**[pass]** Server is opt-in, binds to localhost:3001, and goes through MCP
for data (no direct file writes that bypass the MCP layer).

**[fail]** Server runs by default; or mutates `.edpa/` directly instead of
via MCP tools.

---

## Fáze 12 — Skill-level smoke (5 minutes)

After any change to skills or MCP server, the assistant should pass this in
under 5 minutes.

```
> /edpa:setup --help
> Show me the EDPA project status via MCP.
> List all Done stories in the active iteration.
> Show details for the first story you see.
> What MCP tools are available?
> /edpa:board
> /edpa:capacity PI-2026-1.1 list
```

Each line in turn. Expected:
- `/edpa:setup --help` → skill explains its arguments without running setup
- MCP `edpa_status` returns JSON
- MCP `edpa_backlog` returns Done stories
- MCP `edpa_item` returns one item
- MCP `list_tools` returns 14 tools
- `/edpa:board` produces an HTML board file
- `/edpa:capacity ... list` prints baseline / override capacity

**[pass]** All seven complete; assistant uses MCP whenever a tool fits
(four out of seven).

**[fail]** Assistant resorts to `Bash + grep` for queries that have a
tool; any skill silently fails; `/edpa:sync` is referenced.

---

## Fáze 13 — Customer dogfood

**Goal:** First real customer onboarding, run as the customer would
experience it — entirely local-first.

### 13.1 Setup

In a Claude Code session opened inside the customer project root:

```
> /edpa:setup --with-ci --with-hooks --with-rules
```

Then edit `.edpa/config/{edpa.yaml,people.yaml}` with the real project
name and team.

**[expect skill: setup]** vendors the engine and seeds configs. No
GitHub org/repo prompts.

### 13.2 First backlog

The team creates initial items via the skill:

```
> /edpa:add Feature "..." --parent <I-id> --js 8
> /edpa:add Story "..." --parent <F-id> --js 5 --iteration PI-2026-1.1
```

**[pass]** IDs allocated from `id_counters.yaml`; each item auto-committed
`feat(<ID>): …`; hierarchy validated. Zero GitHub calls at create time.

### 13.3 First close

End of the first iteration:

```
> /edpa:close-iteration PI-2026-1.1
```

**[pass]** Per-person derived hours produced via the single evidence-driven
calculation path; `Σ hours == capacity` invariant passes; timesheets +
`edpa_results.json` written.

### 13.4 First calibration

Once team-confirmed CW corrections are available, re-run the calibrator (it
also runs fine before that, on the synthetic corpus):

```
> /edpa:calibrate
```

**[pass]** Synthetic MC pipeline runs and proposes a weight update; the
team tracks real CW corrections for the future real-data adapter.

### 13.5 Capture as worked example

The whole onboarding should be transcribed (with personally identifying
info redacted) into a follow-up worked example in this plan, so subsequent
customers can compare their own runs.

---

## Akceptační kritéria — celkový plán

The plan is "passed" when:

| #  | Kritérium                                                              | Status |
|----|------------------------------------------------------------------------|--------|
| 1  | Plugin loads in Claude Code; 14 tools advertised by MCP; no `/edpa:sync` | ☐    |
| 2  | `/edpa:setup` vendors engine to `.edpa/engine/`, seeds configs, no GH prompts | ☐ |
| 3  | `/edpa:add` allocates IDs from `id_counters.yaml`, validates parent, auto-commits | ☐ |
| 4  | Backlog reads go through MCP, not `Bash + grep`                        | ☐      |
| 5  | `edpa_item` rejects path-traversal IDs                                 | ☐      |
| 6  | Hand `Edit` to a backlog `.md` fires `validate_on_save.sh`; bad status caught | ☐ |
| 7  | (Optional) `sync_pr_contributions.py` materialises PR-thread signals into `evidence[]` | ☐ |
| 8  | `/edpa:capacity` writes per-iteration overrides (not baseline)         | ☐      |
| 9  | `/edpa:close-iteration` runs capacity prep + engine + reports (single path) | ☐ |
| 10 | Engine `Σ hours == capacity` invariant passes                          | ☐      |
| 11 | `/edpa:reports` accepts iter-id and `pi <PI-ID>` arg forms             | ☐      |
| 12 | `/edpa:board` renders HTML from local `.edpa/backlog/`                 | ☐      |
| 13 | `/edpa:calibrate` runs the synthetic MC pipeline (no ground-truth gate) | ☐    |
| 14 | 5-minute smoke (§ 12) all green                                        | ☐      |
| 15 | Customer onboarding (§ 13) recorded as worked example                 | ☐      |

---

## Příloha A — MCP tool / Bash decision matrix

When the assistant has both a tool and a shell option, it should default
to the tool. This matrix codifies that.

| Question                                | First-line tool                        | Acceptable fallback             |
|-----------------------------------------|----------------------------------------|----------------------------------|
| "What's the project status?"            | `MCP edpa_status`                      | `Bash: cat .edpa/config/...`     |
| "List iterations"                       | `MCP edpa_iterations`                  | —                                |
| "Show team / who's on team X"           | `MCP edpa_people`                      | —                                |
| "List backlog by iteration / type"      | `MCP edpa_backlog`                     | —                                |
| "Show item S-1"                         | `MCP edpa_item`                        | —                                |
| "Create an item"                        | `/edpa:add` (→ `MCP edpa_item_create`) | `Bash: python3 backlog.py add`   |
| "Move an item to a new status"          | `MCP edpa_item_transition`             | `Bash: python3 backlog.py`       |
| "Read engine results for PI-..."        | `MCP read_resource edpa://results/...` | `Bash: cat ...`                  |
| "Read flow metrics"                     | `MCP edpa_flow_metrics`                | —                                |
| "Run the engine / close iteration"      | `/edpa:close-iteration` command        | `Bash: python3 engine.py`        |
| "Record a capacity override"            | `/edpa:capacity` command               | `Bash: python3 capacity_override.py` |
| "Materialise PR-thread signals"         | `Bash: python3 sync_pr_contributions.py` | —                              |

If during a run the assistant systematically prefers the right column
when the left exists, that's a regression — capture as a finding.

---

## Příloha B — Známé skill-level limitations (as of 2.1.x)

1. **MCP exposes local state only.** Tools read/write `.edpa/`; they do not
   read live GitHub state. The only GitHub touchpoint in V2 is the opt-in
   `--with-ci` contribution-sync workflow (`sync_pr_contributions.py`,
   needs `EDPA_TOKEN`).
2. **No bidirectional sync.** V1's `sync.py` / `issue_map.yaml` / GitHub
   Project provisioning were all removed in 2.0.0. There is no
   `/edpa:sync` command, and there must never be a regression that
   re-introduces one.
3. **No `/edpa:setup --help` flag formally.** The skill responds to
   conversational hints ("explain what you'd do without running"); there is
   no canonical `--help` argument.
4. **`/edpa:calibrate` real-data path is unimplemented.** The synthetic MC
   pipeline runs any time; the real-corpus adapter is a documented TODO and
   refuses cleanly.
5. **`docs/E2E-TEST-PLAN.md` and this plan can disagree.** They test
   different layers; if they disagree the truth is "both are bugs".

---

## Příloha C — Differences vs `docs/E2E-TEST-PLAN.md`

| Aspect            | `E2E-TEST-PLAN.md` (script)            | This plan (skill)                          |
|-------------------|----------------------------------------|--------------------------------------------|
| Driver            | Shell terminal                          | Inside Claude Code session                  |
| Invocation        | `python3 .edpa/engine/scripts/engine.py …` | `/edpa:close-iteration PI-…`            |
| Item creation     | `python3 .../backlog.py add …`         | `/edpa:add` (→ `edpa_item_create`)          |
| Data reads        | `cat .edpa/...`, `python3 -c`          | MCP `edpa_*` tools                          |
| Decision points   | Hard-coded in shell script             | Skill prompts, assistant judgment           |
| Failure surface   | Non-zero exit code                     | Assistant explains in natural language      |
| Validates         | Backend correctness                    | Product surface (prompts, dispatch, MCP)   |
| Required          | Yes (CI / regression)                  | Yes (release readiness, customer experience)|

Run both. A passing release requires both green.

---

## Příloha D — Testing strategies for skill flows

This plan exists because script tests don't cover skill orchestration.
But the skill layer is not one thing — it has four observable surfaces,
each with a different right tool.

| What you're trying to verify                              | Right tool                                            |
|-----------------------------------------------------------|-------------------------------------------------------|
| Skill side-effects (filesystem, git audit trail)         | `claude -p` subprocess + outcome assertions           |
| Skill prompts UX (readable? in the right order? skippable?) | Live human walkthrough — there is no automation here |
| MCP tool dispatch from inside a skill (does it call `edpa_status` instead of `Bash + grep`?) | subprocess + stderr log inspection (the `call_tool name=…` lines) |
| Regression on a known-good skill flow                     | recorded transcript + semantic diff (LLM nondeterminism makes exact-match brittle) |

### `claude -p` pattern (outcome-based)

**Implemented:** `tests/test_skill_e2e.py` (opt-in pytest marker `skill_e2e`).
Run with `EDPA_SKILL_E2E=1 pytest tests/test_skill_e2e.py -v`.

The harness drives the **working-tree** plugin (not whatever release is
installed in `~/.claude/plugins`) so a repo regression is caught before it
ships:

```bash
SANDBOX=$(mktemp -d); cd "$SANDBOX"
git init -q && git commit -qm init --allow-empty

# `-p` IS the non-interactive mode — there is NO `--no-interactive` flag.
# `--plugin-dir` loads the repo under test; `bypassPermissions` lets the
# skill's Bash run unattended. Side effects land on disk + in the git log;
# assertions read those, never the (nondeterministic) stdout.
CLAUDE="claude -p --plugin-dir /path/to/edpa/plugin \
        --permission-mode bypassPermissions --output-format text"

$CLAUDE "/edpa:setup"
test -d .edpa/engine/scripts                        # engine vendored
test -f .edpa/config/id_counters.yaml               # ID allocator seeded
test -f .edpa/config/cw_heuristics.yaml             # CW weights seeded

$CLAUDE "/edpa:add Story 'Demo' --parent F-1 --js 3"
git log -1 --format=%s | grep -qE '^feat\(S-[0-9]+\):'   # auto-commit happened
```

**Why outcome-based, not transcript-based:** the skill's *response*
varies (LLM nondeterminism) but its *effects* don't. Asserting on "the
`.md` file exists and a `feat(S-N):` commit landed" is stable across runs;
asserting on "the assistant said 'Setup complete!'" is flaky.

### `pexpect` pattern (interactive multi-turn flow)

```python
import pexpect
c = pexpect.spawn("claude", timeout=30)
c.sendline("/edpa:add Story")
c.expect("[Pp]arent")                  # broad regex — see catch below
c.sendline("F-1")
c.expect("[Jj]ob [Ss]ize|--js")        # multiple phrasings tolerated
c.sendline("5")
c.expect("created|feat\\(S-")
c.close()
```

**Catch:** every regex you write here is a hostage to LLM phrasing
drift. `pexpect` is the right tool when you *need* to drive an interactive
session, but treat it as a smoke test, not a regression suite. Outcome
assertions still need to follow.

### MCP dispatch verification

`mcp_server.py` logs every `call_tool` invocation to stderr:

```
INFO edpa.mcp call_tool name=edpa_status args={}
WARNING edpa.mcp edpa_item: rejected item_id='../etc/passwd'
```

To verify a skill flow uses MCP tools (instead of `Bash + grep`), spawn
Claude Code with `EDPA_LOG_FILE=/tmp/edpa-mcp.log` set and grep the log
after the skill completes:

```bash
EDPA_LOG_FILE=/tmp/edpa-mcp.log claude -p "Show me the active iteration's Done stories."
grep -c "call_tool name=edpa_backlog" /tmp/edpa-mcp.log  # should be ≥ 1
```

Zero hits means the assistant fell back to `Bash + grep`, which is a
regression even if the answer ends up correct.

### Live walkthrough (UX validation)

There is no shortcut here. A human types the slash command, watches what
the skill asks, and judges whether it reads naturally. Notes go into the
appropriate phase of this plan as findings; if they're sharp enough they
become test cases for one of the automation tools above.

The customer onboarding (Phase 13) is the natural first one. Phase 13.5
reserves space for the transcript with PII redacted.

### Strategy pyramid for EDPA today

| Layer                                | Tool                          | EDPA today               |
|--------------------------------------|-------------------------------|---------------------------|
| Unit (handler functions)             | pytest                         | ✅ in `test_mcp_server.py` |
| Integration (MCP wire protocol)      | subprocess + JSON-RPC          | ✅ in `test_mcp_integration.py` |
| Integration (skill side-effects)     | `claude -p` + outcome asserts | ✅ in `test_skill_e2e.py` (opt-in) |
| UX / prompt readability              | live walkthrough               | customer onboarding       |
| Regression on recorded session       | transcript + semantic diff     | ❌ flaky; defer            |

Layers 1–2 are CI-enforceable today. Layer 3 landed in `test_skill_e2e.py`
(opt-in: `EDPA_SKILL_E2E=1` + `claude` on PATH — it spawns real Claude Code,
so it auto-skips in default CI and runs locally / on a scheduled job).
Layer 4 is human, by design — the goal is to keep its surface area small
enough that one walkthrough per release covers it. Layer 5 (regression) is
filed as undated; only worth doing once we have a stable enough skill set
that exact behaviour matters more than outcomes.
