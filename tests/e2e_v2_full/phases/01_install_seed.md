# Phase 01 — Install + Seed Config (run log)

Run tag: 20260527-142316-c6ac4db8
Worker: Wave B Unit 6 (agent-adc45952bd02dd534)
Started: 2026-05-27T14:24:52Z
Finished: 2026-05-27T14:30Z

## Steps executed

1. Pre-flight check — `gh auth status` confirmed (jurby account, scopes:
   admin:org, gist, project, repo, workflow). `.e2e_state.json` parsed
   cleanly with run_tag matching coordinator. Sandbox contained only
   `README.md` and `.git/` as expected.
2. Ran `EDPA_FORCE_INSTALL=1 bash /Users/jurby/projects/edpa/install.sh`
   — output reported "EDPA 2.1.2 installed" with 36 Python modules
   vendored to `.edpa/engine/scripts/`, 1 JSON schema, 3 YAML
   templates. Seeded `.edpa/config/people.yaml` and `.edpa/config/edpa.yaml`
   from default templates.
3. Invoked `Skill` tool with `skill: "edpa:edpa-setup"` and
   `args: "--with-ci --with-hooks --with-rules --non-interactive"` —
   outcome: the skill returned its documentation prompt (text instructions),
   not direct execution. Fallback path used: invoked
   `python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks
   --with-rules` directly. The `--non-interactive` flag is not supported by
   the script and was rejected initially; the script does not block on
   interactive input when run with valid flags, so it was dropped.
   Outcome: success (all 6 steps reported `✓` — directory tree, config
   templates left as-is, id_counters.yaml seeded, CI workflow copied,
   git hooks installed, rules installed).
4. Copied Wave A fixtures from
   `/Users/jurby/projects/edpa/tests/e2e_v2_full/fixtures/{edpa.yaml,people.yaml}`
   into sandbox `.edpa/config/`. Verified `name: "EDPA E2E Pilot"` and
   `len(people) == 5` (alice + 4 others, Bob carrying two contracts).
5. Validated via MCP `edpa_validate` — see note in MCP outputs section
   below; tool runs against the calling agent's host project, not the
   sandbox. Cross-validated sandbox via
   `python3 .edpa/engine/scripts/backlog.py validate`: 12/12 checks
   PASS, 0 errors, 0 warnings ("All checks passed. Backlog is valid.").
6. Cross-validated via MCP `edpa_status` and `edpa_people` — both
   returned sensible data (against host project, not sandbox; see
   "Issues encountered" below).
7. Staged all artifacts, removed `__pycache__/*.pyc` from staging and
   added `.gitignore` excluding `__pycache__/` and `*.pyc`. Initial
   commit attempt blocked by `commit-msg` hook (no EDPA item ref —
   expected behavior since no backlog items exist yet). Used
   `no-ticket:` escape per hook guidance. Pushed to
   `origin/main` (commit `aea4bfb`, parent `6c0fc8e`).

## MCP outputs

### `edpa_validate` (host project — `/Users/jurby/projects/edpa`)

```
{
  "ok": true,
  "pi_count": 2,
  "iteration_count": 10,
  "errors": [],
  "warnings": [9 warnings about person_no_github + person_unused]
}
```

### `edpa_status` (host project)

```
project: "Medical Platform & Datovy e-shop"
current_pi: "PI-2026-1"
team_size: 9
total_capacity_per_iteration: 400
```

### `edpa_people` (host project)

Returned 9 people (urbanek, tuma, turyna, matousek, pm, d1, d2, do, ux1).
None of these are sandbox fixtures.

### `backlog.py validate` (sandbox — `/tmp/edpa-e2e-20260527-142316-c6ac4db8`)

```
EDPA Backlog Validation
  [PASS] Story assignees present
  [PASS] Story JS values present
  [PASS] Story JS <= 8
  [PASS] Parent references valid
  [PASS] Parent type hierarchy
  [PASS] Iteration assignments
  [PASS] WSJF consistency
  [PASS] No duplicate IDs
  [PASS] CW values valid
  [PASS] Type fields present
  [PASS] Fibonacci values
  [PASS] SAFe status values
Summary: Items: 0, Stories: 0, Errors: 0, Warnings: 0
All checks passed. Backlog is valid.
```

## Issues encountered

- **MCP tools resolve to calling agent's project root, not the sandbox.**
  `edpa_validate`/`edpa_status`/`edpa_people` returned data for
  `/Users/jurby/projects/edpa` (the host EDPA repo this agent is run
  from), not for `/tmp/edpa-e2e-...`. This is expected MCP behavior
  — the EDPA MCP server is bound to the session's project. Cross-
  validation via `backlog.py validate` from inside the sandbox dir
  confirms sandbox state is sound. Downstream Wave B units that need
  sandbox-targeted MCP calls should either (a) run inside a Claude
  session whose project root is the sandbox, or (b) rely on direct
  `.edpa/engine/scripts/` invocations.
- **Skill tool returned doc text, not execution.** Invoking
  `/edpa:edpa-setup` via the Skill tool produced the skill's
  instruction prompt rather than running `project_setup.py`. Used the
  documented fallback (direct python invocation) per coordinator's
  instructions.
- **`--non-interactive` not supported.** `project_setup.py` argparse
  rejected the flag. Dropped it; the script does not require
  interactive input with valid flags.
- **`commit-msg` hook blocked initial commit.** No EDPA item refs
  exist yet at setup time, so the hook correctly blocked. Used
  `no-ticket:` escape (audit trail preserved in commit subject).
- **`__pycache__` was created at install time** and staged by
  `git add -A`. Added `.gitignore` to exclude. Downstream units
  should not see this.

## Sandbox state after

- `.edpa/engine/` vendor: **yes** (36 Python modules + schemas + templates).
- `.github/workflows/edpa-contribution-sync.yml`: **present**.
- `.git/hooks/`: pre-commit, commit-msg, post-commit, pre-push all **present**.
- `.claude/rules/edpa-work-rules.md`: **present**.
- `.edpa/config/people.yaml`: **5 entries** (alice + 4 others, matching
  Wave A fixture).
- `.edpa/config/edpa.yaml`: `project.name: "EDPA E2E Pilot"`,
  `methodology: "EDPA 2.1.2"`.
- `.edpa/config/cw_heuristics.yaml`: **seeded** (defaults).
- `.edpa/config/id_counters.yaml`: **seeded** (0 types tracked).
- `.gitignore`: present (excludes `__pycache__/`, `*.pyc`).
- Commit pushed to remote: **yes** (commit `aea4bfb`).

## E2E recipe results

1. `test -d .edpa/engine/scripts` → **pass**
2. `grep "EDPA E2E Pilot" .edpa/config/edpa.yaml` → **pass**
3. People count → **5** (correct)
4. MCP `edpa_validate` 0 errors → recorded above (host project, not
   sandbox — caveat documented)
5. `test -f .github/workflows/edpa-contribution-sync.yml` → **pass**
6. Second commit pushed → **pass** (`aea4bfb` after `6c0fc8e`)
