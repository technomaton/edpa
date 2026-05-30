---
name: edpa:setup
user-invocable: true
description: >
  Initialize EDPA V2 governance for a project. Vendors the engine
  (scripts + schemas + templates) into `.edpa/engine/`, creates
  `.edpa/config/{edpa.yaml,people.yaml}`, seeds id_counters.yaml, and
  optionally copies the PR-signal CI workflow + installs git hooks.
  No GitHub Project provisioning (V1 path removed in 2.0.0).
license: MIT
compatibility: Python 3.10+, MCP edpa server
allowed-tools: Read Write Bash(git *) Bash(mkdir *) Bash(python3 *) Bash(cp *) Bash(touch *)
---

# EDPA Setup — V2 Project Initialization

## What this does

Bootstraps a local-first EDPA project. Everything EDPA-related lives
under `.edpa/`; the engine is vendored as `.edpa/engine/` so CI and
non-Claude-Code tools can run scripts directly without a per-run
install.

Resulting layout:

```
<project>/
├── .edpa/
│   ├── engine/                       ← vendored from ${CLAUDE_PLUGIN_ROOT}/edpa/
│   │   ├── scripts/                  ← Python: backlog.py, engine.py, mcp_server.py, …
│   │   ├── schemas/                  ← JSON Schemas
│   │   └── templates/                ← yaml + workflow templates
│   ├── config/
│   │   ├── edpa.yaml                 ← project.name + governance metadata
│   │   ├── people.yaml               ← team registry
│   │   └── id_counters.yaml          ← local-first ID allocator state
│   ├── backlog/                      ← per-item .md files
│   │   ├── initiatives/  epics/  features/  stories/  defects/  events/  risks/
│   ├── iterations/                   ← per-iteration .yaml
│   ├── reports/                      ← timesheet + engine results
│   └── snapshots/                    ← frozen audit snapshots
└── .github/workflows/
    └── edpa-contribution-sync.yml    ← PR signal materialization (optional)
```

## Arguments

`$ARGUMENTS` — optional flags:

- `--with-ci` — copy `edpa-contribution-sync.yml` to
  `.github/workflows/`. Optional enhancement that materialises
  pr_reviewer / issue_comment signals (PR-thread-only events) from
  GitHub Actions into `evidence[]`. Local commit_author signals
  flow regardless via `--with-hooks`.
- `--with-hooks` — install the full git-hook stack into `.git/hooks/`:
  - **pre-commit**: ID-safety validator (filename≡frontmatter id,
    counter monotonicity, HEAD collisions) — Layer 5 of collision defense
  - **commit-msg**: require EDPA item reference in commit subject/body
    (or `no-ticket:` escape) — catches "did work, forgot to attribute"
  - **post-commit**: `local_evidence.py` emits commit_author and
    `/contribute` signals into the referenced item's `evidence[]`
  - **pre-push**: upstream ID collision check (`validate_ids.py
    --pre-push`) — Layer 6 of collision defense; blocks push when local
    ID already exists on `origin/main`. Recover via `renumber_collisions.py
    --apply`. Full guide: [`docs/dev-collisions.md`](../../../docs/dev-collisions.md).
  - **NOTE**: Layer 7 (CI workflow `edpa-collision-check.yml`) is a
    separate manual step — copy from
    `.edpa/engine/templates/github-workflows/` to `.github/workflows/`
    after running setup.
- `--with-rules` — copy `plugin/rules/*.md` to `.claude/rules/`.
  Claude Code auto-loads these into every agent session, so
  AI assistants in this repo follow the same ticket-first workflow
  as humans.

All three flags are recommended for any team workflow.

## Steps

### 1. Run the bootstrap script

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py \
  --with-ci --with-hooks --with-rules
```

The script is idempotent — safe to re-run when adding hooks/CI after
the initial setup.

### 2. Edit the seeded configs

- `.edpa/config/edpa.yaml` — set `project.name`, `project.registration`
  (optional grant ID), `project.organization`, `project.program`.
- `.edpa/config/people.yaml` — replace the example team with your
  members. Each entry: `{id, name, role, team, fte, capacity}`.

### 3. Create the first item

```bash
python3 .edpa/engine/scripts/backlog.py add \
  --type Initiative --title "Project Apollo"
```

### 4. (Optional) Enable PR signal materialization later

If you skipped `--with-ci` initially:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py --with-ci
```

Then push the new workflow to `main`. After merge of any PR
referencing an EDPA item, the workflow runs `sync_pr_contributions.py`
which writes `evidence[]` into the item's YAML. The engine reads this
on the next `edpa-engine` run.

Migrating from V2.0 (where the block was named `ci_signals[]`):

```bash
python3 .edpa/engine/scripts/migrate_evidence_rename.py
```

(idempotent; `--dry-run` for preview)

## Tuning weights — `.edpa/config/cw_heuristics.yaml`

`project_setup.py` seeds this file with sensible defaults. Three
sections matter:

- **`signals:`** — per-signal-type weight (commit_author 2.78,
  pr_reviewer 2.25, issue_comment 1.14, …). Higher = more influence
  on a person's `cw` share for an item. Calibrate via
  `/edpa:calibrate` after collecting ≥20 ground-truth records.

- **`gate_weights:`** — fires when a Feature/Epic/Initiative status
  transitions inside an iteration window. Splits the parent's
  `job_size` across its lifecycle (`Funnel→Analyzing` … `Releasing→Done`)
  so prep + delivery + acceptance work all gets credited. Stories
  flow through the regular Done-only path; they don't generate gate
  events.

- **`yaml_edit_weights:`** — credits structural changes to
  `.edpa/backlog/*.md` YAML (new block added, list item added, scalar
  changed, …). Captures work that doesn't go through a commit
  attribution flow.

When gate transitions fire (multi-iteration Feature/Epic work),
strategic roles (PM, Arch, BO) get credit via gate events that would
otherwise be invisible. For Story-only sprints, gate_weights is dead
weight — engine still works, just produces empty `gate_events: []`.

Edit + commit `cw_heuristics.yaml` like any other YAML in `.edpa/`;
no special migration needed.

## What NOT to do

- **Never modify `.edpa/engine/` by hand.** It's a vendored copy of
  the plugin; the SessionStart hook auto-resyncs when the plugin
  version changes. Hand edits will be silently overwritten.
- **Never set `EDPA_USE_GH=1` in production.** It's a local-debug
  escape hatch that re-enables runtime gh calls in the engine —
  bypassing the deterministic CI materialization layer. Used in
  production it creates the V1 drift problem all over again.
- **Don't create `.github/ISSUE_TEMPLATE/` files.** V2 doesn't use
  GitHub Issues for item creation — items are created locally via
  `backlog.py add` and synced into git, not into GH.

## V1 migration

If you're coming from EDPA V1 (sync.py / issue_map.yaml in place), run
the migration script first:

```bash
python3 .edpa/engine/scripts/migrate_v1_to_v2.py --dry-run   # preview
python3 .edpa/engine/scripts/migrate_v1_to_v2.py             # apply
```

It seeds the counter from existing IDs, backfills timestamps from git
log, archives `issue_map.yaml`, and strips the `sync:` block from
`edpa.yaml`. After migration, run `project_setup.py --with-ci
--with-hooks` to opt into the CI workflow.
