# Onboarding E2E harness

Drives a **fresh-repo sandbox** through EDPA's onboarding paths and asserts
the engine-vendoring outcome. Originally written to reproduce the gap where
the **`/edpa:setup`** path did not vendor `.edpa/engine/` — that gap was
**fixed in 2.1.8** (commit `82d4b9d`, the same commit that introduced this
harness): `project_setup.py` now vendors the engine itself (`vendor_engine()`,
covered by `tests/test_project_setup_vendor.py`). The harness remains as a
manual full-path **regression/diagnostic tool**; it is not wired into pytest
or CI.

## Run

Any `python3` works:

```sh
python3 tests/onboarding/onboarding_e2e.py
python3 tests/onboarding/onboarding_e2e.py --keep   # keep sandboxes
```

Exit `0` = all onboarding paths healthy. Non-zero = a **regression** (see the
report). All checks are **offline** and run in **auto-cleaned temp git
repos** — no network, no GitHub, nothing written outside `/tmp`.

The interactive check (install.sh overwrite prompt) needs `pexpect`; without
it that single check is reported as SKIP (`pip install pexpect` to enable it).
All other checks run under a bare `python3`.

| Check | Drives | Expectation |
|-------|--------|-------------|
| Path A — `install.sh` vendor mechanic (control) | `cp` replica of install.sh's vendor block | PASS |
| Path B — `/edpa:setup` vendors the engine | real `project_setup.py` (skill Step 1) | PASS (fixed in 2.1.8) |
| `install.sh` overwrite prompt | real `install.sh` via **pexpect** | PASS (abort path, offline); SKIP without pexpect |
| SessionStart hook on fresh repo | real `update_engine.sh` | PASS — skips, can't bootstrap |
| SessionStart hook on stale engine | real `update_engine.sh` | PASS — re-vendors (maintenance only) |

### History — the gap this harness found (fixed in 2.1.8)

`plugin/skills/setup/SKILL.md` Step 1 used to run only `project_setup.py`,
which never copied `plugin/edpa/{scripts,schemas,templates}` into
`.edpa/engine/` — while the skill's description and layout diagram both
claimed it vendors. The SessionStart hook (`update_engine.sh`) could not
compensate: on a repo with no `.edpa/engine/` it hits skip #2 and exits
without creating anything. Commit `82d4b9d` (2.1.8) closed the gap by making
`project_setup.py` vendor the engine as its first step; Path B has passed
since. If Path B fails today, that is a regression in `vendor_engine()` —
see `tests/test_project_setup_vendor.py`.

## Live / manual driving — `tmux_drive.sh`

Generic tmux send-keys/capture helper for driving interactive sessions by hand,
or for the heavier full E2E that drives a **nested `claude` session** through the
real `/edpa:setup` slash command (the genuinely interactive part the offline
harness can't reach). See the script header for examples.
