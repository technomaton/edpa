# Phase 01 — Install + Seed Config (run log)

Run tag: 20260527-181051-2c56a6a0
Worker: Wave B Unit 6 (agent for RUN_TAG 20260527-181051-2c56a6a0)
Started: 2026-05-27T18:12:15Z
Finished: 2026-05-27T18:14:16Z

## Steps executed

1. Pre-flight check — `gh auth status` confirmed (jurby account, scopes:
   admin:org, gist, project, repo, workflow — all required scopes
   present). `.e2e_state.json` parsed cleanly with run_tag matching
   coordinator. Sandbox contained only `README.md` and `.git/` as
   expected.
2. Initial attempt to run `install.sh` via `ctx_shell` with `cwd`
   parameter inadvertently executed in the host project root
   (`/Users/jurby/projects/edpa`) — the `cwd` param did not take
   effect under the lean-ctx shell wrapper in this session. Detected
   immediately via `pwd` echo + verifying sandbox `.edpa/config/`
   missing. Cleaned up the seven stray untracked artifacts in the host
   repo (`rm -rf` of `.claude/rules/edpa-work-rules.md`,
   `.edpa/changelog.jsonl`, `.edpa/config/cw_heuristics.yaml`,
   `.edpa/config/id_counters.yaml`, `.edpa/engine/`, and
   `.github/workflows/edpa-contribution-sync.yml`). Confirmed host
   repo back to its pre-task state (only pre-existing
   `.claude/worktrees/` untracked). Switched to native Bash with
   explicit `cd <sandbox> && …` chaining for all subsequent commands.
3. Re-ran `EDPA_FORCE_INSTALL=1 bash /Users/jurby/projects/edpa/install.sh`
   in the sandbox — output reported "EDPA 2.1.2 installed" with 36
   Python modules vendored to `.edpa/engine/scripts/`, 1 JSON schema,
   3 YAML templates. Seeded `.edpa/config/people.yaml` and
   `.edpa/config/edpa.yaml` from default templates.
4. Per the documented gotcha (commit `6fe17ac`), did not attempt to
   invoke `/edpa:edpa-setup` via the Skill tool. Went directly to the
   fallback:
   `python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks --with-rules`.
   Outcome: all 6 steps reported `✓`:
   (1) directory tree, (2) config templates left as-is (people.yaml +
   edpa.yaml already present from install.sh seed), cw_heuristics.yaml
   seeded, (3) id_counters.yaml seeded with 0 types tracked (correct
   for fresh sandbox), (4) CI workflow copied, (5) git hooks installed
   (pre-commit, pre-push, commit-msg, post-commit), (6) rules
   installed to `.claude/rules/`. `Root:` resolved correctly to
   `/private/tmp/edpa-e2e-20260527-181051-2c56a6a0` (macOS realpath of
   sandbox).
5. Copied Wave A fixtures from
   `/Users/jurby/projects/edpa/tests/e2e_v2_full/fixtures/{edpa.yaml,people.yaml}`
   into sandbox `.edpa/config/`. Verified `name: "EDPA E2E Pilot"` and
   `len(people) == 5` with IDs `['alice', 'bob-arch', 'bob-pm',
   'carol', 'dave']` (alice + 4 others, Bob carrying two contracts).
6. Validated via `python3 .edpa/engine/scripts/backlog.py validate`
   from sandbox cwd: 12/12 checks PASS, 0 errors, 0 warnings ("All
   checks passed. Backlog is valid."). MCP `edpa_validate` not
   invoked from this agent because it targets the host project (per
   commit `7f369bf`), not the sandbox — direct CLI is the
   sandbox-authoritative path.
7. Wrote `.gitignore` excluding `__pycache__/`, `*.pyc`, `.e2e_*`
   (the third entry is for next units' driver scripts per briefing).
8. Created the GitHub sandbox repo
   `technomaton/edpa-e2e-20260527-181051-2c56a6a0` (private, with
   description, `--source=.`, `--remote=origin`, `--push=false`).
9. Staged all artifacts with `git add -A`; verified no `__pycache__`
   or `.pyc` files made it into staging (none present after install
   in this run). Initial commit went through under the
   `commit-msg` hook because the subject starts with `no-ticket:`
   (no EDPA item refs exist yet, which is expected at setup time).
   Commit `bc20d80`, parent `624bb31`. Renamed branch to `main`
   (`git branch -M main`) and pushed with `-u origin main`.
   Remote tracking established.

## MCP outputs

### Note on MCP scope

EDPA MCP tools (`edpa_validate`, `edpa_status`, `edpa_people`, …) bind
to the **calling agent's session project root**, which for this agent
is `/Users/jurby/projects/edpa` (the host EDPA repo we're testing
from). They do **not** target the sandbox at
`/tmp/edpa-e2e-20260527-181051-2c56a6a0`. Per commit `7f369bf` this is
the documented MCP single-project scope limitation. I therefore did
not invoke MCP validation tools for this phase — direct CLI invocation
of `.edpa/engine/scripts/backlog.py validate` from inside the sandbox
is the authoritative validation path for downstream Wave B units.

### `backlog.py validate` (sandbox — `/tmp/edpa-e2e-20260527-181051-2c56a6a0`)

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

- **`ctx_shell` `cwd` parameter did not isolate execution** — first
  install.sh invocation ran in host project root despite explicit
  `cwd` argument. Detected via `pwd` echo (returned
  `/Users/jurby/projects/edpa`). Cleaned the 7 stray host-repo
  untracked artifacts and retried with native Bash + `cd <sandbox> &&`
  chaining, which worked correctly. Downstream units should prefer
  native `Bash` with explicit `cd` for any sandbox-targeted execution,
  or run from a Claude Code session whose project root is the
  sandbox itself.
- **MCP tools resolve to calling agent's project root, not the
  sandbox** — same constraint as prior run (commit `7f369bf`).
  Documented in MCP outputs section.
- **Skill tool returned doc text, not execution** (prior known
  gotcha, commit `6fe17ac`). Skipped Skill invocation entirely and
  went directly to `python3 .edpa/engine/scripts/project_setup.py`.
- **`commit-msg` hook requires EDPA item ref or `no-ticket:`
  escape** — used `no-ticket:` prefix for the install commit, per
  briefing's prescribed command. Hook accepted on first try.
- **No `__pycache__` created during install in this run** — the
  cleanup step `git restore --staged "**/__pycache__/"` was a no-op
  here. `.gitignore` still wisely includes the patterns as a safety
  net for downstream units.

## Sandbox state after

- `.edpa/engine/` vendor: **yes** (36 Python modules + schemas + 3
  templates + 1 GitHub workflow template + rules).
- `.github/workflows/edpa-contribution-sync.yml`: **present**.
- `.git/hooks/`: pre-commit, commit-msg, post-commit, pre-push all
  **present** (executable, mode 755).
- `.claude/rules/edpa-work-rules.md`: **present**.
- `.edpa/config/people.yaml`: **5 entries** (alice, bob-arch, bob-pm,
  carol, dave — matching Wave A fixture).
- `.edpa/config/edpa.yaml`: `project.name: "EDPA E2E Pilot"`,
  `methodology: "EDPA 2.1.2"`.
- `.edpa/config/cw_heuristics.yaml`: **seeded** (defaults).
- `.edpa/config/id_counters.yaml`: **seeded** (0 types tracked).
- `.gitignore`: present (excludes `__pycache__/`, `*.pyc`, `.e2e_*`).
- Local branch: `main` (was `master`, renamed).
- Commit pushed to remote: **yes** (commit `bc20d807c5b0a23ff95811f8ffa2a8786d015415`
  short `bc20d80`, parent `624bb31`). Tracking `origin/main`.

## E2E recipe results

1. `test -d .edpa/engine/scripts` → **PASS**
2. `test -f .github/workflows/edpa-contribution-sync.yml` → **PASS**
3. All 4 git hooks present (pre-commit, commit-msg, post-commit,
   pre-push) → **PASS**
4. `grep -q "EDPA E2E Pilot" .edpa/config/edpa.yaml` → **PASS**
5. People count via PyYAML → **5** (correct)
6. `python3 .edpa/engine/scripts/backlog.py validate` exit 0 → **PASS**
7. `git log --oneline | head -5` shows `bc20d80` (mine) on top of
   `624bb31` (initial) → **PASS**
8. `gh repo view technomaton/edpa-e2e-20260527-181051-2c56a6a0 --json
   name --jq .name` → returns `edpa-e2e-20260527-181051-2c56a6a0`
   → **PASS**

All 8 checks pass. Phase 01 done.
