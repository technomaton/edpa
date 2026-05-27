# EDPA Operational Runbook

Verified manual walkthrough of every `/edpa:*` slash command. Use this when
onboarding a new project, debugging an unfamiliar workflow, or before relying
on the toolchain for a real iteration close.

**Last verified:** 2026-05-04 against branch `main` at `0b583be`.

---

## Quick reference

| Command              | Underlying script / skill          | Status     | Tested by |
|----------------------|------------------------------------|------------|-----------|
| `/edpa:setup`        | `plugin/edpa/scripts/project_setup.py` | ✅ verified | `tests/test_e2e_sync.py::test_setup_creates_project_and_persists_ids` |
| `/edpa:sync`         | `plugin/edpa/scripts/sync.py`      | ✅ verified | `tests/test_e2e_sync.py` (5 tests) |
| `/edpa:close-iteration` | `engine.py` then `edpa-reports` skill | ✅ verified | `tests/test_invariants.py`, `tests/test_gate_allocation.py` |
| `/edpa:reports`      | `edpa-reports` skill (no script)   | ✅ verified | manual + skill execution |
| `/edpa:calibrate`    | `edpa-autocalib` skill             | ⚠️ requires ≥20 ground-truth records — skip until first PI closed |
| `/edpa:board`        | `plugin/edpa/scripts/board.py`     | ✅ verified | manual run |

---

## Prerequisites (one-time per machine)

```bash
gh auth login              # repo + project + admin:org scopes
gh extension install --upgrade  # ensure latest gh
python3.13 --version       # 3.10+ required
python3.13 -m pip install pyyaml openpyxl
```

For org-level Issue Types (Initiative, Epic, Feature, Story):

```bash
python3.13 plugin/edpa/scripts/issue_types.py setup --org <your-org>
```

---

## 1. `/edpa:setup` — initialize a new project

**Purpose:** create GitHub Project v2, custom fields, issues from local
backlog, link parent/child via sub-issues, persist IDs for sync.

**Prerequisites:**
- Repo exists on GitHub.
- `.edpa/backlog/{initiatives,epics,features,stories}/` populated with item
  YAMLs (use `plugin/edpa/templates/*.tmpl` as starting point).
- `.edpa/config/edpa.yaml` exists (template at `plugin/edpa/templates/project.yaml.tmpl`).
- Org has native Issue Types set up (see prerequisites above).

**Run:**

```bash
python3.13 plugin/edpa/scripts/project_setup.py \
  --org <org> --repo <repo> \
  --project-title "Project Name"
```

Use `--dry-run` first to print the plan without touching GitHub.

**Expected output (last steps):**

```
[9] Persisting GitHub state (.edpa/config/edpa.yaml + issue_map.yaml)
      ✓ Project #N, K fields, M options saved
      ✓ issue_map.yaml: X items mapped
══════════════════════════════════════════════════════════════════════
  Setup complete!
  Project: https://github.com/orgs/<org>/projects/N
  Issues:  X created
  Fields:  Y values set
  Links:   Z sub-issue links
```

**What got persisted:**

- `.edpa/config/edpa.yaml` → `sync.github_org`, `sync.github_repo`,
  `sync.github_project_id`, `sync.github_project_number`,
  `sync.field_ids`, `sync.option_ids`.
- `.edpa/config/issue_map.yaml` → per-item `issue_number`, `project_item_id`,
  `node_id`.

**Common failure modes:**

- `Could not query issue types from org` → run `issue_types.py setup --org X` first.
- `Project might already exist` → setup reuses it (idempotent re-run is safe;
  it does NOT recreate fields, but issue creation will skip duplicates).

**Recovery:** if `field_ids` / `issue_map.yaml` are lost (different machine,
file corruption), run `python3.13 plugin/edpa/scripts/sync.py setup-refresh`.

---

## 2. `/edpa:sync` — bidirectional sync GitHub ↔ local YAML (optional)

**Purpose:** keep local `.edpa/backlog/` and the GitHub Project in agreement.
Push local changes, pull remote field updates, detect conflicts.

**V2.1 positioning:** sync is *optional*. The engine reads evidence directly
from `git log`; running EDPA without ever pushing to GitHub Projects is a
fully supported path. Enable sync only when PMs/BOs want a board view.

**Run options:**

```bash
python3.13 plugin/edpa/scripts/sync.py status         # health overview
python3.13 plugin/edpa/scripts/sync.py diff            # dry-run, what would change
python3.13 plugin/edpa/scripts/sync.py pull            # GH → local
python3.13 plugin/edpa/scripts/sync.py pull --commit   # also git commit the change
python3.13 plugin/edpa/scripts/sync.py push            # local → GH (creates new issues)
python3.13 plugin/edpa/scripts/sync.py log             # last 20 changelog entries
python3.13 plugin/edpa/scripts/sync.py conflicts       # items changed on both sides
python3.13 plugin/edpa/scripts/sync.py setup-refresh   # rebuild IDs from existing project
python3.13 plugin/edpa/scripts/sync.py add-iteration PI-2026-1.5  # add new iteration option to GH
```

**Adding new iterations after setup:** when you create a new
`.edpa/iterations/PI-2026-1.5.yaml` file, the GitHub Project's
`Iteration` SINGLE_SELECT field doesn't know about it yet. Run
`sync add-iteration PI-2026-1.5` to append it via
`updateProjectV2Field` GraphQL mutation. The `TBD` placeholder
option (created by `project_setup.py` when no iterations existed
yet) is dropped automatically the first time a real iteration is
added. Idempotent — re-running on an iteration whose option already
exists is a no-op. Pass `--dry-run` to see the plan without calling
the API; `--color BLUE|GREEN|...` overrides the default `GRAY`.

**Per-level typed status fields:** `pull` reads `Initiative Status` /
`Epic Status` / `Feature Status` / `Story Status` based on the item's level
(not the default GitHub `Status` field). This is what makes the SAFe
workflow work end-to-end.

**Push semantics:**

- Local-only items → new GitHub issue created, added to project, fields set,
  parent linked via `addSubIssue`. `issue_map.yaml` updated.
- Existing items with field deltas → `gh project item-edit` with the right
  `--number` or `--single-select-option-id` based on field type.
- Status `→ Done` also closes the issue. Reverting from Done reopens it.

**Timestamp fields (v1.23.0+):** `sync pull` now extracts `created_at`,
`closed_at`, and `updated_at` from each GitHub issue and stores them as
read-only frontmatter fields in the local YAML/Markdown item. These are
populated automatically; do not edit them by hand. They are used for flow
metrics computation and conflict detection.

**Conflict detection (v1.23.0+):** `_detect_remote_modifications()` compares
the local `updated_at` timestamp against the GitHub-side value. If the
remote `updated_at` is newer than the locally stored one, the item is
flagged as remotely modified (e.g. someone edited the issue directly in
the GitHub UI, bypassing `sync push`). `sync conflicts` surfaces these
items alongside the existing changelog-based conflict checks.

**Conflict policy:** items changed on both sides since last sync are surfaced
by `sync conflicts`. Resolution is manual today — edit `.edpa/backlog/...yaml`
to the desired state and run `push`. Local then wins.

**Flow metrics (v1.23.0+):** with timestamps in place, the MCP tool
`edpa_flow_metrics` computes cycle time, throughput, and open item age
from the synced data. See [`docs/mcp.md`](mcp.md) for inputs and output
schema.

**Common failure modes:**

- `Push aborted: GitHub setup state missing or incomplete` → run setup or
  `sync setup-refresh` first.
- `[skipped: not in issue_map]` → an item exists locally without a GH issue
  AND has not been created by this push (rare; usually means manual deletion
  on GH while item remained local).

---

## 3. `/edpa:close-iteration` — compute derived hours

**Purpose:** at iteration end, compute each person's derived hours from
delivery evidence and produce the per-person reports.

**Two-step orchestration** (this slash command runs both):

```bash
# Step 1: engine — produces .edpa/reports/iteration-<ID>/edpa_results.json
python3.13 plugin/edpa/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.4 \
  --output .edpa/reports/iteration-PI-2026-1.4/edpa_results.json

# Step 2: reports skill — reads the JSON and writes timesheets, snapshots, XLSX
# (the edpa-reports skill is invoked by Claude; no separate script)
```

**Single calculation path (v1.14+, extended in v1.17):** the mode
selector (`--mode simple|gates`) was retired in 1.14 because `gates`
was a strict superset of the others. The current path credits three
event kinds together:

- **Story / Defect / Task Done credit** — items at `status: Done` get
  `JS × cw` per their contributors[]. (v1.17 fix: pre-1.17 Defects
  were silently dropped at a `level == "Story"` filter.)
- **Parent gate transitions** — Feature / Epic / Initiative status
  changes captured in git history become synthetic events with
  `effective_js = parent.JS × gate_weights[type][transition]`.
  Validated against `edpa-simulation-gates` harness (avg MAD 7.8%,
  stable to ±20% CW perturbation). **Requires git history of status
  changes** — `sync pull --commit` produces these automatically.
- **YAML-edit signals (v1.17)** — every commit on a backlog YAML in
  the iteration window contributes structural signals (create,
  block_add, list_grow, scalar_change, lines_volume,
  contributors_rebalance, revert). Captures progressive elaboration
  on parents (LBC, benefit hypothesis, AC, NFRs, risks) that is
  invisible to PR-only or status-only collectors.

**Verification:** `python3.13 -m pytest tests/test_invariants.py -v` ensures
score formula, capacity invariant, and ratio sums hold for any output.

---

## 4. `/edpa:reports` — generate timesheets and exports

**Purpose:** produce per-person Markdown + JSON reports, per-item cost
allocation, frozen JSON snapshot, optional Excel exports.

**Inputs required:**

- `.edpa/reports/iteration-<ID>/edpa_results.json` (from `/edpa:close-iteration`).
- `.edpa/config/people.yaml` (for hourly rates and roles).

**Produces:**

- `.edpa/reports/iteration-<ID>/timesheet-<person>.md` (one per person).
- `.edpa/reports/iteration-<ID>/edpa_results.json` (engine echo, in-place).
- `.edpa/reports/iteration-<ID>/edpa-results.xlsx` (Team Summary + Item Costs tabs).
- `.edpa/snapshots/<ID>.json` (frozen, methodology-tagged).
- `.edpa/reports/pi-<PI>/pi-summary-<PI>.md` (when invoked with `pi`).

**No standalone script** — the `edpa-reports` skill drives Claude to read
results, format reports, and write artifacts. See `.claude/skills/edpa-reports/SKILL.md`
for the per-step contract.

**Existing snapshots in this repo:** `.edpa/snapshots/PI-2026-1.1.json` and
`PI-2026-1.1_rev2.json` — examples to compare structure.

---

## 5. `/edpa:calibrate` — auto-calibrate CW heuristics

**Purpose:** optimize role weights in `heuristics.yaml` against ground-truth
records using Karpathy autoresearch loop.

**Prerequisites:**

- ≥20 records in `.edpa/data/ground_truth.yaml` — manually confirmed CW
  values from a closed PI with retrospective adjustments.
- Closed iterations with engine results.

**Skip until first PI is closed and reviewed.** Running before that has no
signal — the loop will overfit on noise. See `feedback_cw_calibration.md` in
auto-memory.

**When ready:**

```bash
# Skill invocation handles experiment budget + iteration count
# Manual fallback for inspection:
ls .edpa/data/ground_truth.yaml      # must exist
cat .edpa/config/heuristics.yaml     # current state
```

The skill writes `.edpa/data/calibration_log.tsv` per iteration with MAD
delta. Acceptance: MAD reduction ≥ 5%.

---

## 6. `/edpa:board` — visual HTML Kanban snapshot

**Purpose:** generate a self-contained HTML Kanban view of the backlog.
No server, no auth — open the file directly.

**Run:**

```bash
python3.13 plugin/edpa/scripts/board.py --open
# or: python3.13 plugin/edpa/scripts/board.py --output ~/Desktop/board.html
```

**Options:**

- `--iteration PI-2026-1.4` — filter by iteration prefix.
- `--level story|feature|epic|initiative` — which level to show (default: story).

**Verified output:** ~42 KB self-contained HTML, dark theme, JetBrains Mono +
DM Sans fonts. 37 items rendered from current `.edpa/backlog/`.

---

## End-to-end smoke test (5 minutes)

After a fresh machine setup, this proves the toolchain is functional:

```bash
# 1. Unit + integration suite
python3.13 -m pytest tests/                # 118 tests, < 10s

# 2. End-to-end against real GH sandbox (5–6 min, opt-in)
EDPA_E2E_REPO=technomaton/edpa-e2e-test \
  python3.13 -m pytest tests/test_e2e_sync.py -m e2e -v

# 3. Engine smoke
python3.13 plugin/edpa/scripts/engine.py --status
python3.13 plugin/edpa/scripts/engine.py --demo

# 4. Sync smoke
python3.13 plugin/edpa/scripts/sync.py status

# 5. Board smoke
python3.13 plugin/edpa/scripts/board.py --output /tmp/edpa-board.html
test -s /tmp/edpa-board.html && echo "board OK"
```

If all five pass, the toolchain is ready for a real PI close.

---

## Known limitations (as of 2026-05-04)

1. **Gates mode under-allocates without commit-recorded status changes.** Real
   `sync pull --commit` produces them; manual YAML edits do not unless you
   commit them with a status-change message recognised by `transitions.py`.
2. **Static-contributor model**: engine uses one contributor list per parent
   item for *every* gate of that item. Highly specialised roles that touch
   only some gates (e.g. Architect at LBC only) get over-attributed at the
   other gates. Per-iteration MAD outliers up to ~47 % observed in
   `edpa-simulation-gates`. In practice teams contribute across most gates,
   so this is rarely a problem; address by recalibrating heuristics or
   removing such contributors from items where they are truly absent.
