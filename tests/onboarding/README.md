# Onboarding E2E harness

Drives a **fresh-repo sandbox** through EDPA's two onboarding paths and asserts
the engine-vendoring outcome. Reproduces the gap where the **`/edpa:setup`**
path does not vendor `.edpa/engine/` — only **`curl|sh install.sh`** does.

## Run

Use the interpreter that has `pexpect` (miniconda on this machine):

```sh
/opt/miniconda3/bin/python3 tests/onboarding/onboarding_e2e.py
/opt/miniconda3/bin/python3 tests/onboarding/onboarding_e2e.py --keep   # keep sandboxes
```

Exit `0` = all paths healthy. Non-zero = a gap reproduced (see the report).
All checks are **offline** and run in **auto-cleaned temp git repos** — no
network, no GitHub, nothing written outside `/tmp`.

| Check | Drives | Expectation |
|-------|--------|-------------|
| Path A — `install.sh` vendor mechanic (control) | `cp` replica of `install.sh:154-169` | PASS |
| Path B — `/edpa:setup` vendors the engine | real `project_setup.py` (skill Step 1) | **FAILS** — documents the gap |
| `install.sh` overwrite prompt | real `install.sh` via **pexpect** | PASS (abort path, offline) |
| SessionStart hook on fresh repo | real `update_engine.sh` | PASS — skips, can't bootstrap |
| SessionStart hook on stale engine | real `update_engine.sh` | PASS — re-vendors (maintenance only) |

### The gap, in one line

`plugin/skills/edpa-setup/SKILL.md` Step 1 runs only `project_setup.py`, which
never copies `plugin/edpa/{scripts,schemas,templates} → .edpa/engine/` — yet the
skill's description and layout diagram both claim it vendors. The SessionStart
hook (`update_engine.sh`) can't compensate: on a repo with no `.edpa/engine/` it
hits skip #2 and exits without creating anything.

## Live / manual driving — `tmux_drive.sh`

Generic tmux send-keys/capture helper for driving interactive sessions by hand,
or for the heavier full E2E that drives a **nested `claude` session** through the
real `/edpa:setup` slash command (the genuinely interactive part the offline
harness can't reach). See the script header for examples.
