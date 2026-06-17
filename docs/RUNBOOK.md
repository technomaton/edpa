# EDPA Operational Runbook

Verified manual walkthrough of every `/edpa:*` slash command. Use this when
onboarding a new project, debugging an unfamiliar workflow, or before relying
on the toolchain for a real iteration close.

**Last reviewed:** 2026-05-31 — **V2 local-first** (2.0.0+). `.edpa/backlog/`
YAML is the source of truth, git is the audit trail. GitHub Projects sync is
**optional**; the engine derives hours from local git evidence without it.

---

## Quick reference

| Command              | Underlying script / skill          | Status |
|----------------------|------------------------------------|--------|
| `/edpa:setup`        | `.edpa/engine/scripts/project_setup.py` | ✅ vendors engine + seeds `.edpa/` (local-first) |
| `/edpa:create-pi`    | `.edpa/engine/scripts/create_pi.py` | ✅ writes the PI-level `pi:` file (also `edpa_pi_create` MCP tool) |
| `/edpa:close-iteration` | `.edpa/engine/scripts/engine.py` → `/edpa:reports` skill | ✅ verified by `tests/test_invariants.py`, `tests/test_gate_allocation.py` |
| `/edpa:reports`      | `/edpa:reports` skill (no script)   | ✅ manual + skill execution |
| `/edpa:board`        | `.edpa/engine/scripts/board.py`    | ✅ manual run |
| `/edpa:capacity`     | `.edpa/engine/scripts/capacity_override.py` | ✅ per-iteration capacity overrides |
| `/edpa:calibrate`    | `/edpa:autocalib` skill             | ⚠️ needs ≥20 ground-truth records — skip until first PI closed |
| GitHub PR signals (optional) | `edpa-contribution-sync.yml` CI → `sync_pr_contributions.py` | ⚪ opt-in — materializes PR-thread evidence (§2) |

---

## Prerequisites (one-time per machine)

EDPA is **local-first** — you need only Python + git:

```bash
python3 --version                         # 3.10+ required
python3 -m pip install pyyaml openpyxl ruamel.yaml
git --version
```

GitHub CLI is needed **only** if you opt into the optional GitHub Projects sync
or the `--with-ci` PR-signal workflow — neither is required to compute hours:

```bash
gh auth login              # repo scope; optional, for sync / PR-signal CI only
```

---

## 1. `/edpa:setup` — initialize a new project

**Purpose:** bootstrap a **local-first** EDPA project. Vendors the engine into
`.edpa/engine/`, seeds `.edpa/config/{edpa.yaml,people.yaml,cw_heuristics.yaml}`
+ `id_counters.yaml`, and (with flags) installs git hooks, the PR-signal CI
workflow, and architectural rules. **No GitHub Project provisioning** — the V1
`--org/--repo/--project-title`, Issue Types, and `issue_map.yaml` path was
removed in 2.0.0.

**Prerequisites:**
- A git repo (local is fine — no GitHub required).
- The EDPA plugin installed in Claude Code (`/plugin install edpa@technomaton-edpa`).

**Run (Claude Code):**

```
/edpa:setup --with-ci --with-hooks --with-rules
```

Under the hood:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py \
  --with-ci --with-hooks --with-rules
```

Idempotent — safe to re-run to add hooks/CI/rules later. Outside Claude Code,
`curl -fsSL https://edpa.technomaton.com/install.sh | sh` vendors the same
engine + `.edpa/` tree.

**Flags (all recommended for team workflows):**
- `--with-hooks` — pre-commit + commit-msg + post-commit + pre-push git hooks
  (ID safety, ticket-attached, local `commit_author` evidence emission). Detects
  lefthook and prints a paste-ready snippet instead of touching `.git/hooks/`;
  never clobbers a foreign hook. See **Git hooks** below.
- `--with-ci` — copies `edpa-contribution-sync.yml`; materializes PR-thread
  signals (`pr_reviewer`, `issue_comment`) into `evidence[]` after merge.
  Optional, GitHub-only — local commit evidence flows without it.
- `--with-rules` — copies architectural rules to `.claude/rules/` so AI sessions
  follow the same ticket-first workflow as humans.

**Expected output (last steps):**

```
  [1] Vendor engine    ✓ Vendored engine → .edpa/engine/ (50 scripts, VERSION 2.8.1)
  [2] Directory tree   ✓ Directory tree at .edpa/
  [3] Config templates ✓ Seeded people.yaml, edpa.yaml, cw_heuristics.yaml
  [4] ID counter       ✓ id_counters.yaml seeded
  [5] Git hooks (--with-hooks)        ✓ pre-commit, pre-push, commit-msg, post-commit
  [6] Architectural rules (--with-rules)  ✓ edpa-work-rules.md → .claude/rules/
EDPA setup complete.
```

**What got created:**

- `.edpa/engine/{scripts,schemas,templates}/` — vendored engine (do **not**
  hand-edit; the SessionStart hook re-syncs it on plugin update).
- `.edpa/config/{edpa.yaml,people.yaml,cw_heuristics.yaml,id_counters.yaml}`.
- `.edpa/{backlog,iterations,reports,snapshots}/` tree.
- (flags) `.git/hooks/*` (or a lefthook snippet),
  `.github/workflows/edpa-contribution-sync.yml`, `.claude/rules/`.

**Git hooks — registration, lefthook, verification:**

`--with-hooks` writes four hooks into `.git/hooks/` (`pre-commit`, `pre-push`,
`commit-msg`, `post-commit`). The `post-commit` one runs `local_evidence.py` —
**this is what records contribution evidence onto items**, so if it isn't
registered, contributions silently never appear. The registration is
deliberately careful:

- **Re-running is safe and self-refreshing.** Re-run `/edpa:setup --with-hooks`
  (or `python3 .edpa/engine/scripts/project_setup.py --refresh-hooks`) any time:
  EDPA-owned hooks are overwritten with the current version, missing ones
  reinstalled. EDPA marks its hooks with an `EDPA-MANAGED-HOOK` sentinel.
- **Foreign hooks are never clobbered.** If a non-EDPA file already occupies a
  slot, EDPA skips it and prints a loud warning with the exact line to chain
  EDPA in by hand (`sh .edpa/engine/scripts/hooks/<hook> "$@"`).
- **lefthook (or any tool that owns `.git/hooks/`).** lefthook generates its own
  dispatcher shims into `.git/hooks/` (and can set `core.hooksPath`), so a plain
  copy would be ignored or clobbered — this is the usual cause of "contribution
  stopped working after an update". EDPA detects `lefthook.yml` and, instead of
  writing `.git/hooks/`, prints a paste-ready block. Add it to your
  `lefthook.yml`, then run `lefthook install`:

  ```yaml
  pre-commit:
    commands:
      edpa-id-safety:
        run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety
  commit-msg:
    commands:
      edpa-ticket-attached:
        run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}
  post-commit:
    commands:
      edpa-evidence:
        run: sh .edpa/engine/scripts/hooks/post-commit-evidence
  pre-push:
    commands:
      edpa-id-safety:
        run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}
        use_stdin: true   # pre-push refs arrive on stdin — without this lefthook hangs
  ```

- **After a plugin update**, the SessionStart auto-update re-registers EDPA hooks
  automatically when the project already uses them (and, under lefthook, reminds
  you to verify). No manual step needed for the plain `.git/hooks/` case.
- **Verify any time** (read-only doctor — no changes):

  ```bash
  python3 .edpa/engine/scripts/project_setup.py --check-hooks
  ```
  Reports each hook as active / missing / foreign, or flags lefthook so you know
  to register via the snippet.

**Next:** edit `people.yaml` (your team) + `edpa.yaml` (`project.name`), then
create items locally:

```bash
python3 .edpa/engine/scripts/backlog.py add --type Initiative --title "Project Apollo"
```

**Common failure modes:**

- `--with-rules` reports "Rules source dir missing" → the engine's `rules/`
  weren't vendored; re-run `/edpa:setup` (or `install.sh`), which now vendors them.
- `.edpa/engine/scripts/*.py` not found → run from the **project root** (the
  engine resolves `.edpa/` by walking up from CWD, or honoring `EDPA_ROOT`).

---

## 2. GitHub integration (optional) — PR-signal materialization

V2 is **local-first**: the engine reads delivery evidence straight from
`git log`, so EDPA produces a complete derived timesheet with **no GitHub at
all**. The V1 bidirectional `sync.py` (GitHub Project push/pull, `issue_map.yaml`,
sub-issues, org Issue Types, `gh project` provisioning) was removed in 2.0.0.

The single optional GitHub touchpoint is **PR-signal materialization**, enabled
by `/edpa:setup --with-ci` (which copies `.github/workflows/edpa-contribution-sync.yml`):

- After a PR that references an EDPA item (`feat(S-1): …`) merges, the workflow
  runs `.edpa/engine/scripts/sync_pr_contributions.py`, which writes PR-thread
  signals (`pr_reviewer`, `issue_comment`) into that item's `evidence[]`.
- `git pull` brings the enriched item YAML back to every clone.
- The next `/edpa:close-iteration` reads the new evidence;
  `.edpa/engine/scripts/detect_contributors.py` turns `evidence[]` into
  per-person `cw`.

This captures contributions local commits can't see — a reviewer who approved a
PR, a BO who commented requirements — **without any board sync**.

**Requires** an `EDPA_TOKEN` secret for the workflow — see
[`docs/edpa-token-setup.md`](edpa-token-setup.md).

**Flow metrics:** the `edpa_flow_metrics` MCP tool computes cycle time,
throughput, and open-item age from item timestamps (backfilled from git
history via `_git_timestamps.py`). See [`docs/mcp.md`](mcp.md).

**Want a board view?** Use `/edpa:board` for a self-contained local HTML Kanban
(§6) — no GitHub, no sync.

---

## 3. `/edpa:close-iteration` — compute derived hours

**Purpose:** at iteration end, compute each person's derived hours from
delivery evidence and produce the per-person reports.

**Two-step orchestration** (this slash command runs both):

```bash
# Step 1: engine — produces .edpa/reports/iteration-<ID>/edpa_results.json
python3 .edpa/engine/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.4 \
  --output .edpa/reports/iteration-PI-2026-1.4/edpa_results.json

# Step 2: reports skill — reads the JSON and writes timesheets, snapshots, XLSX
# (the /edpa:reports skill is invoked by Claude; no separate script)
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

**Verification:** `python3 -m pytest tests/test_invariants.py -v` ensures
score formula, capacity invariant, and ratio sums hold for any output.

---

## 3b. `/edpa:capacity` — per-iteration capacity overrides

**Purpose:** adjust one person's capacity for a single iteration (PTO, sick
leave, overtime, onboarding ramp) **without** changing the `people.yaml`
baseline.

Baseline capacity is `capacity_per_iteration` (fallback `capacity`) in
`.edpa/config/people.yaml`. An override is stored in the iteration YAML
`people:` block and applied by the engine — it shows up in
`edpa_results.json` as `capacity`, `capacity_baseline`, and `capacity_override`.

```bash
# list current overrides
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.4 --list

# set: absolute hours, or +N / -N delta from baseline
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.4 --add --person dave  --hours 12 --note "PTO"
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.4 --add --person alice --hours +8 --note "release push"

# remove (revert to baseline)
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.4 --remove --person dave
```

- Each change is validated and auto-committed (`--no-commit` to skip the commit).
- **Closed iterations reject overrides** (audit trail) — set them BEFORE closing.
  This is also Stage 1 of `/edpa:close-iteration` (`<iter> --prep-only`), so
  capacity prep can happen during close.
- A permanent change across all iterations → edit `capacity_per_iteration` in
  `people.yaml`. Re-run the engine after any change so reports reflect it.

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

**No standalone script** — the `/edpa:reports` skill drives Claude to read
results, format reports, and write artifacts. See `.claude/skills/reports/SKILL.md`
for the per-step contract.

**Existing snapshots in this repo:** `.edpa/snapshots/PI-2026-1.1.json` and
`PI-2026-1.1_rev2.json` — examples to compare structure.

---

## 5. `/edpa:autocalib` — auto-calibrate CW signal weights

**Purpose:** optimize the 3 signal weights (`commit_author`,
`pr_reviewer`, `issue_comment`) in
`.edpa/config/cw_heuristics.yaml` using Monte Carlo + coordinate descent
against a synthetic corpus (always available) or blended with team-confirmed
corrections from a closed PI retrospective.

**Target file:** `.edpa/config/cw_heuristics.yaml`
(installed from `plugin/edpa/templates/cw_heuristics.yaml.tmpl`)

### Quarterly cadence

Run after each PI close, once the retrospective corrections are recorded:

```bash
# 1. Record corrections after retrospective
#    .edpa/data/calibration_corrections.yaml (create from template if missing)
cp .edpa/engine/templates/calibration_corrections.yaml.tmpl \
   .edpa/data/calibration_corrections.yaml
# Edit: add iteration/item/person/actual_cw entries

# 2. Preview what would change (no write)
python3 .edpa/engine/scripts/calibrate_signals.py \
  --real-data --quick --dry-run

# 3. Run and apply
python3 .edpa/engine/scripts/calibrate_signals.py \
  --real-data --scenarios 1000 --apply --commit

# 4. Verify
cat .edpa/config/cw_heuristics.yaml | grep -A6 "signals:"
```

Or via the skill: `/edpa:autocalib --real-data apply`

### Synthetic-only (no real data yet)

```bash
python3 .edpa/engine/scripts/calibrate_signals.py \
  --scenarios 1000 --seed 42 --apply --commit
```

Synthetic calibration is runnable any time. Real-data blending requires at
least one closed PI with retrospective corrections.

### Governance flags

| Flag | Effect |
|---|---|
| `--dry-run` | Show weight diff + MAD improvement without writing |
| `--apply` | Write best weights to template |
| `--commit` | After `--apply`, `git commit` with MAD-diff message |
| `--real-data` | Blend `.edpa/data/calibration_corrections.yaml` with synthetic |
| `--real-weight N` | How many times real records count vs synthetic (default 10) |

### Rollback

```bash
git log --oneline --follow plugin/edpa/templates/cw_heuristics.yaml.tmpl | head -5
git checkout <SHA> -- plugin/edpa/templates/cw_heuristics.yaml.tmpl
cp plugin/edpa/templates/cw_heuristics.yaml.tmpl .edpa/config/cw_heuristics.yaml
```

### Acceptance threshold

A calibration run is worth applying when MAD improvement ≥ 2% vs baseline.
Below that, the synthetic corpus is near the local optimum — add more real
corrections and re-run next quarter.

### Weight bounds

Signal weights must stay in **[0.1, 8.0]**. The `validate_on_save` hook
checks `cw_heuristics.yaml` on every edit and reports bound violations.
Manual edits outside this range will produce a validation warning.

---

## 6. `/edpa:board` — visual HTML Kanban snapshot

**Purpose:** generate a self-contained HTML Kanban view of the backlog.
No server, no auth — open the file directly.

**Run:**

```bash
python3 .edpa/engine/scripts/board.py --open
# or: python3 .edpa/engine/scripts/board.py --output ~/Desktop/board.html
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
# 1. Unit + integration suite (from the EDPA source checkout)
python3 -m pytest tests/                       # fast; seconds

# 2. Engine smoke — demo computation + status (no project data needed)
python3 .edpa/engine/scripts/engine.py --demo
python3 .edpa/engine/scripts/engine.py --status

# 3. Backlog smoke
python3 .edpa/engine/scripts/backlog.py tree

# 4. Board smoke
python3 .edpa/engine/scripts/board.py --output /tmp/edpa-board.html
test -s /tmp/edpa-board.html && echo "board OK"
```

If these pass, the toolchain is ready for a real PI close.

---

## ID collision handling

When two developers parallel-allocate the same backlog item ID (both add `S-5` on different branches before either merges), EDPA detects and recovers via four defense layers — full documentation in [`docs/dev-collisions.md`](dev-collisions.md).

**Quick reference for operators:**

| Layer | Where | What it does |
|---|---|---|
| Pre-commit hook | local | blocks commit on staged-set inconsistencies |
| Pre-push hook | local | blocks push if local ID exists upstream |
| CI workflow | server | comments on PR + fails check on collision |
| Manual recovery | local | `renumber_collisions.py --apply` renames + updates parents + bumps counter |

**Standard recovery flow** (when a PR shows a conflict in `.edpa/backlog/` or `id_counters.yaml`):

```bash
git fetch origin
python3 .edpa/engine/scripts/renumber_collisions.py --apply
git add . && git commit -m "renumber: collision with main"
git merge origin/main   # resolve id_counters.yaml conflict by taking MAX value
git push
```

**Setup checklist for a new project** (do once):

```bash
# 1. Install local hooks (pre-commit + pre-push)
python3 .edpa/engine/scripts/project_setup.py --with-hooks

# 2. Copy CI workflow template into project's workflows dir
cp .edpa/engine/templates/github-workflows/edpa-collision-check.yml \
   .github/workflows/edpa-collision-check.yml
git add .github/workflows/edpa-collision-check.yml
git commit -m "ci: add EDPA collision check"
```

Verify hooks are installed (read-only doctor — works for `.git/hooks/` and
flags lefthook):
```bash
python3 .edpa/engine/scripts/project_setup.py --check-hooks
```

If your repo uses **lefthook**, `--with-hooks` prints a paste-ready snippet
instead of writing `.git/hooks/`; add it to `lefthook.yml` and run
`lefthook install` (see §1 → *Git hooks — registration, lefthook, verification*).

See [`docs/dev-collisions.md`](dev-collisions.md) for decision tree, common collision shapes (single / multi / parent-chain / cascading), troubleshooting, and the `--target develop` flag for Git Flow projects.

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
