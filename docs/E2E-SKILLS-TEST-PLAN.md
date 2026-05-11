# EDPA — Skill-driven E2E Test Plan

End-to-end validation of EDPA as customers experience it: through Claude
Code slash commands, skill orchestration, and MCP server tool calls — not
by invoking `engine.py`, `sync.py`, or `project_setup.py` directly.

**Companion to** `docs/E2E-TEST-PLAN.md`. The script-level plan tests the
backend behavior; this plan tests the product surface — prompts, decision
points, MCP tool dispatch, error messages users actually see. Both must
pass for a release to be production-ready.

**Verze plánu:** 1.0 (2026-05-05, post-v1.3.0-beta release)
**Pokrývá:** 5 skills (`edpa-setup`, `edpa-sync`, `edpa-engine`,
`edpa-reports`, `edpa-autocalib`) + 6 slash commands + MCP server (5 tools,
3 resources).

---

## 0. Why this exists

`docs/E2E-TEST-PLAN.md` runs the codebase as a developer does: bash
shell, direct Python invocation, manual `gh` calls. That is necessary
but **not sufficient**. EDPA's product surface is the
`/edpa:*` slash command set, the conversational orchestration each
skill performs, and the MCP server that lets the assistant query
`.edpa/` data structurally instead of via `Bash + grep`.

A script-level pass with a skill-level fail looks like this:
- `python3 .claude/edpa/scripts/sync.py push` → exits 0 ✅
- `/edpa:sync push` from inside Claude Code → skill prompts the user
  for the wrong field name, dispatches `Bash(python3 ...)` with
  `--mode=mock` by accident, never surfaces the failure → user thinks
  the project is in sync when it isn't ❌

This plan catches the second class.

---

## 1. Předpoklady

### 1.1 Toolchain (jednorázově)

```bash
# Confirm in your terminal, BEFORE entering Claude Code:
claude --version           # Claude Code CLI
gh --version               # ≥ 2.40
gh auth status             # scopes: repo, project, admin:org
python3 --version          # ≥ 3.10
python3 -m pip install -r requirements-dev.txt  # mcp + pyyaml + jsonschema + openpyxl
```

### 1.2 Sandbox

- GitHub repo: `technomaton/edpa-e2e-test` (private, must start empty
  before run; tests are destructive in this repo).
- Org-level Issue Types must exist:
  ```bash
  python3 plugin/edpa/scripts/issue_types.py setup --org technomaton
  ```
  (One-time per org. Idempotent.)

### 1.3 Plugin installed

```bash
TARGET=$(mktemp -d -t edpa-skills-test-XXXX)
cd "$TARGET"
git init -q
echo "# skills test" > README.md
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

Verify: `.claude/edpa/`, `.edpa/config/{edpa,people,heuristics}.yaml`,
plugin v1.3.0-beta or later.

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

| Notation                | Meaning                                                        |
|-------------------------|----------------------------------------------------------------|
| `> /edpa:setup ...`     | What you type into the Claude Code prompt                      |
| `→ skill: edpa-X`       | Which skill should be invoked                                  |
| `→ MCP: edpa_status`    | Tool call the assistant should make against the EDPA MCP server |
| `→ Bash: gh project …`  | A Bash tool call the skill is expected to issue                |
| `[expect prompt]`       | Skill should ask the user for input here                       |
| `[expect artifact]`     | A file should appear at this path                              |
| `[pass]` / `[fail]`     | Acceptance / rejection criteria                                |

---

## Fáze 1 — Plugin loads, MCP server is reachable

**Goal:** Claude Code session loads the EDPA plugin successfully, MCP
server starts, all 5 tools are advertised.

### 1.1 Plugin discovery

Inside the Claude Code session:

```
> /help
```

**[expect]** `/edpa:setup`, `/edpa:sync`, `/edpa:close-iteration`,
`/edpa:reports`, `/edpa:calibrate`, `/edpa:board` appear in the
slash command list.

### 1.2 MCP probe

```
> What EDPA MCP tools are available? List them and their inputs.
```

**[expect]** Assistant calls `→ MCP: list_tools` (not `Bash + grep`)
and reports 5 tools: `edpa_status`, `edpa_iterations`, `edpa_people`,
`edpa_backlog`, `edpa_item`. The `edpa_item` tool requires `item_id`.

**[expect]** Assistant also reports `serverInfo: edpa v1.3.0-beta` (or
later) — the version string the server returns at `initialize`.

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
or MCP version is older than 1.3.0-beta; or fewer than 5 tools advertised.

---

## Fáze 2 — `/edpa:setup`

**Goal:** The setup skill conversationally collects project metadata,
creates the GitHub Project, custom fields, issue types, and seeds
`issue_map.yaml`.

### 2.1 First invocation, no arguments

```
> /edpa:setup
```

**[expect skill: edpa-setup]**

**[expect prompt]** Skill asks (one or more questions, in order):
- Project name
- GitHub org
- Repo name
- Whether to use existing iterations from `.edpa/iterations/` or
  start with the placeholder

The skill MUST NOT silently `gh project create` without confirming
inputs. Setup is a write operation and the user must see what's about
to happen.

### 2.2 Provide answers

Type each answer into the prompt as the skill asks. For the rerun
example use:

- Project name: `EDPA-Skills-Demo-<timestamp>`
- Org: `technomaton`
- Repo: `edpa-e2e-test`
- Iterations: start placeholder

### 2.3 Setup execution

**[expect Bash]** `gh project create --owner technomaton --title ...`
**[expect Bash]** `gh project field-create ...` (loop, ~10 fields)
**[expect Bash]** `gh issue create ...` (loop, one per backlog item)
**[expect Bash]** `python3 .../project_setup.py` OR direct `gh` calls;
either is acceptable as long as the orchestration is skill-driven.

The skill should narrate what it's doing — the assistant's chat history
should read like a setup log, not like a wall of bash output.

### 2.4 Persistence verification

After setup completes, verify via MCP (not by reading files directly):

```
> Confirm the EDPA setup is persisted: project number, field count,
  how many items mapped.
```

**[expect MCP: edpa_status]** Returns project name, current_pi
(possibly "unknown" if no real iteration), team_size, etc.

**[expect Bash: cat .edpa/config/edpa.yaml]** OR `→ MCP: read_resource
edpa://config` — both acceptable. Verify `sync.field_ids` has at least
21 entries (per-level Status + Iteration + Job Size + WSJF + …).

**[pass]** GitHub Project visible at `https://github.com/orgs/technomaton/projects/N`,
`.edpa/config/issue_map.yaml` has every item mapped, `field_ids` includes
`Iteration` (a v1.1+ guarantee).

**[fail]** Any of: skill skipped a confirmation prompt; `gh project
create` ran with empty title; `field_ids` missing `Iteration`;
`issue_map.yaml` missing entries.

---

## Fáze 3 — Backlog hygiene through the assistant

**Goal:** The assistant uses MCP for backlog discovery, edits items
through `Edit` (which fires the validation hook), and the validate
hook surfaces an error when YAML breaks.

### 3.1 List backlog via MCP

```
> List every Story currently in the backlog with its status.
```

**[expect MCP: edpa_backlog with type=Story]** (one tool call, returns
all stories). Assistant must not `Bash: ls .edpa/backlog/stories/` and
read each YAML.

### 3.2 Read one item via MCP

```
> Show me the full S-1 record.
```

**[expect MCP: edpa_item with item_id="S-1"]** Returns the full YAML
contents as JSON.

### 3.3 Path-traversal safety

```
> Try fetching item ID "../etc/passwd" via the MCP tool. What happens?
```

**[expect MCP: edpa_item with item_id="../etc/passwd"]** Returns
`ERROR: invalid item_id ...`. Assistant must explain that the regex
guard rejected the input.

### 3.4 Edit triggers validation hook

```
> Edit S-2: change its status to "In Progress" (note: invalid status,
  the validator should catch this).
```

**[expect Edit tool]** on `.edpa/backlog/stories/S-2.yaml`.

**[expect hook]** `validate_on_save.sh` fires (status message
"Validating syntax..."). If the schema enforces enum, it must reject
`In Progress` (only `Backlog`, `Analyzing`, `Implementing`, `Reviewing`,
`Done` are valid for Story Status).

**[expect assistant]** sees the validation failure and tells the user.
A v1.3 quality bar: it should not silently accept bad data.

**[pass]** All four behaviors above. Assistant prefers MCP tools over
filesystem grepping; bad item ID is rejected; bad YAML edit is caught
by the hook.

**[fail]** Assistant grepped instead of using MCP; path traversal
returned a file; bad enum status was written.

---

## Fáze 4 — Branche, commity, PR

**Goal:** Standard git workflow flows through the assistant. The
`edpa-branch-check.yml` GitHub Action enforces naming. Commit triggers
`edpa_post_commit.sh` hook with structured commit info.

### 4.1 Wrong branch name

```
> Create a junk branch and push it. We expect the GitHub Action to fail.
```

**[expect Bash: git checkout -b junk-branch ...]**
**[expect Bash: gh pr create ...]**
After CI runs (~ 30 s), check:

```
> Did the branch-check action pass on this PR?
```

**[expect Bash: gh pr checks ...]** `branch-check` ❌.

### 4.2 Correct branch (refers item)

```
> Cancel the junk PR. Switch to a new feature branch for S-1, make a
  trivial change, and open a PR.
```

**[expect Bash]** branch name `feature/S-1-something`. PR opens.

After CI:

```
> Status of all checks on the new PR.
```

**[expect Bash: gh pr checks ...]** `branch-check` ✅, `validate-item`
✅ (because S-1 exists in backlog).

**[pass]** Junk branch fails CI; correctly named branch passes.
Assistant uses `gh` consistently, doesn't try to manually parse PR HTML.

---

## Fáze 5 — `/edpa:sync push`

**Goal:** Local-only items propagate to GitHub via the sync skill.
Status changes propagate too. Iteration field works (no
`no field_id for 'Iteration'` regression).

### 5.1 Add a local-only story

```
> Add S-3 to the backlog: Story under F-1, JS=2, owner is example-dev,
  iteration PI-2026-1.1, status Backlog.
```

**[expect Write tool]** for `.edpa/backlog/stories/S-3.yaml`.
**[expect hook]** `validate_on_save.sh` fires and passes.

### 5.2 Status change on existing story

```
> Mark S-1 as Implementing.
```

**[expect Edit tool]** on `.edpa/backlog/stories/S-1.yaml`.

### 5.3 Push

```
> /edpa:sync push
```

**[expect skill: edpa-sync]**
**[expect Bash: python3 .../sync.py push]** OR equivalent skill
orchestration.

The skill output should narrate:
- 1 new issue created (S-3 → #N)
- 1 field change pushed (S-1 status → Implementing)
- **0 failures** (this is the v1.1.0+ guarantee — no Iteration field
  failures)

### 5.4 Verify on GitHub via MCP

```
> Pull the current status of S-1 from the GitHub Project.
```

**[expect MCP: edpa_item OR Bash: gh api graphql ...]** Either is fine;
prefer MCP if it exposes remote state (it does not today — TODO).

**[expect Bash: gh issue view #N]** Shows S-3 issue with the right
fields and the parent link to F-1.

**[pass]** Push reports zero failures. S-3 visible on GitHub. Status
field on S-1 is `Implementing`. No "no field_id for 'Iteration'"
in the assistant's chat trail.

**[fail]** Any failure count > 0 in push output. Iteration-related
errors. Skill silently retries without telling user.

---

## Fáze 6 — `/edpa:sync pull --commit`

**Goal:** Remote changes flow into local YAML. Iteration values
on stories survive (don't get cleared by the bug we fixed in 1.1.0).
Commits are produced for `--mode gates` to read later.

### 6.1 Manual change in GitHub UI (or via gh CLI)

```
> Set F-1's "Feature Status" to "Analyzing" on the GitHub Project.
  Use gh project item-edit.
```

**[expect Bash: gh project item-edit ...]** with the right field-id
and option-id (the assistant has these from `.edpa/config/edpa.yaml`).

### 6.2 Pull

```
> /edpa:sync pull --commit
```

**[expect skill: edpa-sync]**

The skill should narrate:
- 1 change detected: F-1 status `Funnel → Analyzing`
- Applied to `.edpa/backlog/features/F-1.yaml`
- Auto-commit created with message `sync: pull 1 change ...`

### 6.3 Iteration preservation check

```
> Confirm S-1, S-2, S-3 still have iteration: PI-2026-1.1 in their YAML.
```

**[expect MCP: edpa_backlog with iteration=PI-2026-1.1]** Returns 3
items. Assistant reports they all have the iteration tag.

**[pass]** F-1 round-trip OK; pull-commit happened; **stories' iteration
field NOT cleared** (the v1.1.0 fix). One git commit produced.

**[fail]** Iteration tag missing from any of S-1/S-2/S-3 after pull.
More than 1 commit (would suggest noisy diff).

---

## Fáze 7 — `/edpa:sync conflicts`

**Goal:** Cross-side conflict detection works on the first try (the
v1.1.0 conflict-cutoff fix).

### 7.1 Build a conflict

```
> 1. Set F-1 status locally to "Reviewing", commit.
  2. Push to GitHub via sync.
  3. On GitHub, override F-1 to "Done" via gh project item-edit.
  4. Locally, edit F-1 again to "Implementing", commit.
  5. Run sync pull (without --commit, just to record the GH change).
```

This is exactly the sequence that exposed the `max(last_pull, last_push)`
bug in 1.0.0-beta.

### 7.2 Inspect conflicts

```
> /edpa:sync conflicts
```

**[expect skill: edpa-sync]**
**[expect Bash: python3 .../sync.py conflicts]**

Output must show:
```
✗ 1 items have changes from both sources:
  F-1
    GitHub changes:  status: ... → Done
    Git changes:     status: ... → Implementing OR Reviewing
```

If the output says `✓ No conflicts detected.`, the per-side cutoff
logic regressed.

**[pass]** Conflict detected on first run.

**[fail]** "No conflicts" → regression of the v1.1.0 fix.

### 7.3 Resolve

```
> Resolve with local-wins.
```

**[expect Bash: python3 .../sync.py conflicts --strategy local-wins --apply]**

**[pass]** F-1 on GitHub now matches local; conflict cleared on rerun.

---

## Fáze 8 — Recovery via `setup-refresh`

**Goal:** After losing `field_ids` / `issue_map.yaml` (different
machine, file deletion), the skill re-discovers everything from the
existing GitHub Project.

### 8.1 Simulate loss

```
> Wipe sync.field_ids and sync.option_ids from .edpa/config/edpa.yaml,
  and delete .edpa/config/issue_map.yaml.
```

**[expect Edit + Bash: rm]**

### 8.2 Refresh

```
> /edpa:sync setup-refresh
```

**[expect skill: edpa-sync]**
**[expect Bash: python3 .../sync.py setup-refresh]**

Output:
```
✓ Setup state refreshed: 21 fields, ≥5 items mapped
```

### 8.3 Confirm Iteration field present

```
> Does the Iteration field exist in the refreshed config?
```

**[expect Bash: yq / python3 -c]** OR `→ MCP: read_resource edpa://config`

**[pass]** `Iteration` is in `field_ids`, `issue_map.yaml` rebuilt with
all original entries.

**[fail]** Iteration missing → either the project is from before the
v1.1.0 fix, or refresh has a bug.

---

## Fáze 9 — `/edpa:close-iteration`

**Goal:** Engine + reports run together via one skill invocation;
gates mode picks up the status transition commits from earlier phases.

### 9.1 Close all stories Done

Make sure every Story in `PI-2026-1.1` has `status: Done`. Push to
GitHub.

### 9.2 Close

```
> /edpa:close-iteration PI-2026-1.1
```

**[expect skill: edpa-engine then edpa-reports]** (chained).

**[expect Bash: python3 .../engine.py --iteration PI-2026-1.1 --mode gates]**

Output narrative:
- Engine summary: `TEAM TOTAL = capacity`, `All invariants passed: YES`
- Reports skill takes over: 2× timesheet (per person), single
  `edpa-results.xlsx` (Team Summary + Item Costs tabs), frozen snapshot,
  `edpa_results.json`.

### 9.3 Read results via MCP

```
> Use the MCP to fetch the engine results for PI-2026-1.1.
```

**[expect MCP: read_resource edpa://results/PI-2026-1.1]** Returns the
JSON contents of `edpa_results.json`. (This is one of the 3 MCP
resources.)

**[pass]** Engine invariants pass; reports artifacts present;
`edpa://results/...` resource readable.

**[fail]** Skill chains broken (engine ran but reports skipped); MCP
resource missing for a closed iteration.

---

## Fáze 10 — `/edpa:reports`

**Goal:** Standalone report generation against an already-closed
iteration.

### 10.1 Generate again

```
> /edpa:reports PI-2026-1.1
```

**[expect skill: edpa-reports]**

Skill should be idempotent — running twice should produce identical
artifacts (modulo timestamps).

### 10.2 Per-item analysis

```
> /edpa:reports per-item S-1
```

**[expect skill: edpa-reports]** Produces a focused report on S-1's
contribution allocation.

### 10.3 PI summary

```
> /edpa:reports pi
```

**[expect skill: edpa-reports]** Aggregates all closed iterations in
the PI into `pi-summary-{PI}.md`.

**[pass]** Each invocation produces the right artifact; skill recognizes
all three argument forms.

**[fail]** Skill defaults to "list everything" instead of acting on the
argument.

---

## Fáze 11 — `/edpa:calibrate` readiness

**Goal:** The auto-calib skill correctly refuses to run before the
first PI is closed and reviewed (≥ 20 ground-truth records).

### 11.1 Empty ground truth

```
> /edpa:calibrate
```

**[expect skill: edpa-autocalib]**

**[expect refusal]** Skill should say something like
"Insufficient ground truth (< 20 records). Skip until first PI is
closed and reviewed." It must NOT touch `.edpa/config/heuristics.yaml`.

**[pass]** Skill refuses gracefully, explains why, no file written.

**[fail]** Skill runs the autoresearch loop on noise (would overfit).

### 11.2 (Out-of-scope today) Real run

After kashealth's first real PI with manual review, verify:

```
> /edpa:calibrate
```

actually runs the loop, picks up `.edpa/data/ground_truth.yaml`,
writes `.edpa/data/calibration_log.tsv`, achieves ≥ 5% MAD reduction
before committing changes to `heuristics.yaml`.

---

## Fáze 12 — Skill-level smoke (5 minutes)

After any change to skills or MCP server, the assistant should pass
this in under 5 minutes.

```
> /edpa:setup --help
> Show me the EDPA project status via MCP.
> List all Done stories in the active iteration.
> Show details for the first story you see.
> What MCP tools are available?
> /edpa:sync status
> /edpa:board
```

Each line in turn. Expected:
- `/edpa:setup --help` → skill explains its arguments without running setup
- MCP `edpa_status` returns JSON
- MCP `edpa_backlog` returns Done stories
- MCP `edpa_item` returns one item
- MCP `list_tools` returns 5 tools
- `/edpa:sync status` returns the sync.py status table
- `/edpa:board` produces an HTML board file

**[pass]** All seven complete; assistant uses MCP whenever a tool fits
(four out of seven).

**[fail]** Assistant resorts to `Bash + grep` for queries that have a
tool; any skill silently fails.

---

## Fáze 13 — Kashealth dogfood

**Goal:** First real customer onboarding, run as the customer would
experience it.

### 13.1 Setup

In a Claude Code session opened inside the kashealth project root:

```
> /edpa:setup "Kashealth"
```

Provide real inputs as the skill asks: org, repo, team, iterations.

**[expect skill: edpa-setup]** runs to completion against the actual
kashealth org and repo.

### 13.2 First sync

After the team adds initial stories to `.edpa/backlog/stories/`:

```
> /edpa:sync push
```

**[pass]** Issues created on GitHub with the right Issue Type, parent
links, fields. Zero "no field_id" warnings.

### 13.3 First close

End of the first iteration:

```
> /edpa:close-iteration PI-2026-1.1
```

Run in `--mode simple` for the first PI (audit-conservative). Compare
results with `--mode gates` separately for A/B before switching the
default.

**[pass]** Per-person derived hours produced. PM reviews them and
records ≥ 20 ground-truth correction records into
`.edpa/data/ground_truth.yaml`.

### 13.4 First calibration

After the PM's manual review:

```
> /edpa:calibrate
```

**[pass]** Auto-calib loop now has data, runs the experiment loop,
proposes a heuristic update with ≥ 5% MAD reduction.

### 13.5 Capture as worked example

The whole kashealth onboarding should be transcribed (with personally
identifying info redacted) into a follow-up worked example in this
plan, so subsequent customers can compare their own runs.

---

## Akceptační kritéria — celkový plán

The plan is "passed" when:

| #  | Kritérium                                                              | Status |
|----|------------------------------------------------------------------------|--------|
| 1  | Plugin loads in Claude Code; 5 tools advertised by MCP                | ☐      |
| 2  | `/edpa:setup` is conversational (asks before writing)                  | ☐      |
| 3  | Backlog reads go through MCP, not `Bash + grep`                        | ☐      |
| 4  | `edpa_item` rejects path-traversal IDs                                 | ☐      |
| 5  | `Edit` to a backlog YAML fires the validation hook                     | ☐      |
| 6  | `branch-check` action fails on junk names, passes on item-prefixed     | ☐      |
| 7  | `/edpa:sync push` reports `0 failed` (no Iteration regression)         | ☐      |
| 8  | `/edpa:sync pull --commit` preserves stories' iteration tag            | ☐      |
| 9  | `/edpa:sync conflicts` detects cross-side divergence on first try     | ☐      |
| 10 | `/edpa:sync setup-refresh` rebuilds `field_ids` incl. Iteration       | ☐      |
| 11 | `/edpa:close-iteration` chains engine + reports                        | ☐      |
| 12 | `/edpa:reports` accepts iter-id, `pi`, `per-item X` arg forms          | ☐      |
| 13 | `/edpa:calibrate` refuses on empty ground truth                        | ☐      |
| 14 | 5-minute smoke (§ 12) all green                                        | ☐      |
| 15 | Kashealth onboarding (§ 13) recorded as worked example                 | ☐      |

---

## Příloha A — MCP tool / Bash decision matrix

When the assistant has both a tool and a shell option, it should default
to the tool. This matrix codifies that.

| Question                                | First-line tool                   | Acceptable fallback         |
|-----------------------------------------|-----------------------------------|------------------------------|
| "What's the project status?"            | `MCP edpa_status`                 | `Bash: cat .edpa/config/...` |
| "List iterations"                       | `MCP edpa_iterations`             | —                            |
| "Show team / who's on team X"           | `MCP edpa_people`                 | —                            |
| "List backlog by iteration / type"      | `MCP edpa_backlog`                | —                            |
| "Show item S-200"                       | `MCP edpa_item`                   | —                            |
| "Read engine results for PI-..."        | `MCP read_resource edpa://results/...` | `Bash: cat ...`         |
| "Read raw heuristics.yaml"              | `Bash: cat` (no MCP tool today)   | —                            |
| "Run the engine"                        | `/edpa:close-iteration` skill     | `Bash: python3 engine.py`    |
| "Push a status change"                  | `/edpa:sync push` skill           | `Bash: python3 sync.py push` |
| "Set a custom field on GitHub"          | `Bash: gh project item-edit`      | —                            |

If during a run the assistant systematically prefers the right column
when the left exists, that's a regression — capture as a finding.

---

## Příloha B — Známé skill-level limitations (as of 1.3.0-beta)

1. **MCP is read-only.** Tools cannot push or close issues. Customer
   sessions that want write paths must use the slash command skills
   (which call sync via Bash).
2. **MCP doesn't expose remote GitHub state.** `edpa_backlog` reads
   `.edpa/backlog/`, not the live Project. To see remote state the
   assistant has to call `gh`.
3. **No `/edpa:setup --help` flag formally.** Skill responds to
   conversational hints ("explain what you'd do without running"), but
   there is no canonical `--help` argument. Add in v1.4.
4. **No `/edpa:status` command.** Status is exposed via MCP and via
   `/edpa:sync status`. No plain `/edpa:status` slash command exists
   today; consider adding for symmetry.
5. **`docs/E2E-TEST-PLAN.md` and this plan can disagree.** They test
   different layers; if they disagree the truth is "both are bugs".

---

## Příloha C — Differences vs `docs/E2E-TEST-PLAN.md`

| Aspect            | `E2E-TEST-PLAN.md` (script)            | This plan (skill)                          |
|-------------------|----------------------------------------|--------------------------------------------|
| Driver            | Shell terminal                          | Inside Claude Code session                  |
| Invocation        | `python3 .../engine.py …`              | `/edpa:close-iteration PI-…`                |
| Data reads        | `cat .edpa/...`, `yq`, `python3 -c`    | MCP `edpa_*` tools                          |
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
| Skill side-effects (filesystem, GitHub state)             | `claude -p` subprocess + outcome assertions           |
| Skill prompts UX (readable? in the right order? skippable?) | Live human walkthrough — there is no automation here |
| MCP tool dispatch from inside a skill (does it call `edpa_status` instead of `Bash + grep`?) | subprocess + stderr log inspection (the `INFO call_tool name=…` lines) |
| Regression on a known-good skill flow                     | recorded transcript + semantic diff (LLM nondeterminism makes exact-match brittle) |

### `claude -p` pattern (outcome-based, runnable in CI)

```bash
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"
git init -q
curl -fsSL https://edpa.technomaton.com/install.sh | sh > /dev/null

# Drive Claude Code in non-interactive mode. Skill side-effects land
# on disk and on GitHub; assertions read those, not the stdout.
claude -p "/edpa:setup TestProject" --no-interactive

# Outcome assertions
test -f .edpa/config/issue_map.yaml         # setup persisted IDs
project_num=$(yq '.sync.github_project_number' .edpa/config/edpa.yaml)
gh project view "$project_num" --owner "$ORG" --format json \
  | jq -e '.title == "TestProject"'         # actually created on GH

# Cleanup
gh project delete "$project_num" --owner "$ORG"
```

**Why outcome-based, not transcript-based:** the skill's *response*
varies (LLM nondeterminism) but its *effects* don't. Asserting on
"the issue_map.yaml exists with these IDs" is stable across runs;
asserting on "the assistant said 'Setup complete!'" is flaky.

### `pexpect` pattern (interactive multi-turn flow)

```python
import pexpect
c = pexpect.spawn("claude", timeout=30)
c.sendline("/edpa:setup")
c.expect("[Pp]roject name")           # broad regex — see catch below
c.sendline("Demo")
c.expect("organization|GitHub org")    # multiple phrasings tolerated
c.sendline("technomaton")
c.expect("Setup complete|setup done")
c.close()
```

**Catch:** every regex you write here is a hostage to LLM phrasing
drift. The skill could one week ask "What's the project name?" and
another week "Project name:". `pexpect` is the right tool when you
*need* to drive an interactive session, but treat it as a smoke test,
not a regression suite. Outcome assertions still need to follow.

### MCP dispatch verification

`mcp_server.py` logs every `call_tool` invocation to stderr:

```
INFO edpa.mcp call_tool name=edpa_status args={}
WARNING edpa.mcp edpa_item: rejected item_id='../etc/passwd'
```

To verify a skill flow uses MCP tools (instead of `Bash + grep`),
spawn Claude Code with `EDPA_LOG_FILE=/tmp/edpa-mcp.log` set and
grep the log after the skill completes:

```bash
EDPA_LOG_FILE=/tmp/edpa-mcp.log claude -p "Show me the active iteration's Done stories."
grep -c "call_tool name=edpa_backlog" /tmp/edpa-mcp.log  # should be ≥ 1
```

Zero hits means the assistant fell back to `Bash + grep`, which is a
regression even if the answer ends up correct.

### Live walkthrough (UX validation)

There is no shortcut here. A human types the slash command, watches
what the skill asks, and judges whether it reads naturally. Notes go
into the appropriate phase of this plan as findings; if they're sharp
enough they become test cases for one of the automation tools above.

The kashealth onboarding (Phase 13) is the natural first one. Phase
13.5 reserves space for the transcript with PII redacted.

### Strategy pyramid for EDPA today

| Layer                                | Tool                          | EDPA today               |
|--------------------------------------|-------------------------------|---------------------------|
| Unit (handler functions)             | pytest                         | ✅ 48 tests in `test_mcp_server.py` |
| Integration (MCP wire protocol)      | subprocess + JSON-RPC          | ✅ 16 tests in `test_mcp_integration.py` |
| Integration (skill side-effects)     | `claude -p` + outcome asserts | ❌ open — TODO.md v1.5    |
| UX / prompt readability              | live walkthrough               | kashealth onboarding      |
| Regression on recorded session       | transcript + semantic diff     | ❌ flaky; defer            |

Layers 1–2 are CI-enforceable today. Layer 3 is the next thing to
build (see `TODO.md`). Layer 4 is human, by design — the goal is to
keep its surface area small enough that one walkthrough per release
covers it. Layer 5 (regression) is filed as undated; only worth
doing once we have a stable enough skill set that exact behaviour
matters more than outcomes.
