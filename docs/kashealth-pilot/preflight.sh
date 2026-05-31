#!/usr/bin/env sh
# EDPA V2 — kashealth pilot pre-flight check (local-first)
# Exits 0 only when every required item is in place. Prints a fix-it
# command for each missing piece so the operator can copy-paste their
# way to a green check before running the engine.
#
# V2 is local-first: `.edpa/backlog/**/*.md` is the source of truth and
# GitHub is OPTIONAL. This preflight therefore checks ONLY the local
# toolchain + a seeded `.edpa/` — no `gh` scopes, no org access, no
# Issue Types, no GitHub Project. `gh` is needed solely for the OPTIONAL
# PR-signal sync workflow (--with-ci); its absence is at most a warning.

set -u
EDITION="${EDPA_EDITION:-V2}"
FAIL=0
WARN=0

c_red() { printf '\033[31m%s\033[0m' "$1"; }
c_grn() { printf '\033[32m%s\033[0m' "$1"; }
c_yel() { printf '\033[33m%s\033[0m' "$1"; }
c_dim() { printf '\033[2m%s\033[0m' "$1"; }

ok()    { printf "  $(c_grn '✓') %s\n" "$1"; }
fail()  { printf "  $(c_red '✗') %s\n" "$1"; FAIL=$((FAIL+1)); }
warn()  { printf "  $(c_yel '⚠') %s\n" "$1"; WARN=$((WARN+1)); }
hint()  { printf "    $(c_dim 'fix:') %s\n" "$1"; }

step() { printf "\n$(c_grn '[%s]') %s\n" "$1" "$2"; }

# --- 1. Toolchain (required: python3 + git) --------------------------------
step 1 "Toolchain"
for cmd in python3 git; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd: $(command -v "$cmd")"
    else
        fail "$cmd not on PATH"
        hint "install $cmd"
    fi
done

# gh is OPTIONAL in V2 — only the --with-ci PR-signal workflow uses it.
if command -v gh >/dev/null 2>&1; then
    ok "gh: $(command -v gh)  (optional — only for --with-ci PR-signal sync)"
else
    warn "gh not on PATH (optional — needed only for the --with-ci PR-signal workflow)"
    hint "install gh ONLY if you want PR-thread signals synced into evidence[]"
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "?")
PY_OK=$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 10) else "no")' 2>/dev/null || echo "no")
if [ "$PY_OK" = "yes" ]; then
    ok "Python $PY_VERSION (>= 3.10)"
else
    fail "Python $PY_VERSION (need >= 3.10)"
    hint "install Python 3.10+ (pyenv / system package manager)"
fi

# Required engine deps. ruamel.yaml is needed for comment-preserving
# YAML writes (backlog.py / capacity_override.py); pyyaml + openpyxl
# for the engine + xlsx export.
for mod in yaml openpyxl; do
    if python3 -c "import $mod" 2>/dev/null; then
        ok "Python module: $mod"
    else
        fail "Python module $mod missing"
        hint "pip3 install pyyaml openpyxl ruamel.yaml   # also installed by install.sh"
    fi
done
if python3 -c "import ruamel.yaml" 2>/dev/null; then
    ok "Python module: ruamel.yaml"
else
    warn "Python module ruamel.yaml missing (comment-preserving YAML writes degrade)"
    hint "pip3 install ruamel.yaml   # also installed by install.sh"
fi

# --- 2. Local working tree state ------------------------------------------
step 2 "Local working tree (current dir)"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    ok "Inside a git repo: $(git rev-parse --show-toplevel)"
    LOCAL_NAME=$(git config user.name || true)
    LOCAL_EMAIL=$(git config user.email || true)
    if [ -n "$LOCAL_NAME" ] && [ -n "$LOCAL_EMAIL" ]; then
        ok "git user.name + user.email: $LOCAL_NAME <$LOCAL_EMAIL>"
    else
        fail "git user.name / user.email not set"
        hint "git config user.name 'Your Name'"
        hint "git config user.email 'you@kashealth.cz'"
        hint "(without these, EDPA auto-commit + post-commit evidence skip silently)"
    fi
else
    warn "Not inside a git repo — re-run preflight from inside kas-platform-v1"
    hint "git init   # EDPA records the audit trail via git commits"
fi

# --- 3. EDPA engine vendored ----------------------------------------------
step 3 "EDPA engine (.edpa/engine/scripts/)"
if [ -d ".edpa/engine/scripts" ]; then
    N_SCRIPTS=$(find .edpa/engine/scripts -maxdepth 1 -name '*.py' 2>/dev/null | wc -l | tr -d ' ')
    ENGINE_VERSION=$(cat .edpa/engine/VERSION 2>/dev/null | tr -d ' \n' || echo "?")
    ok "Engine vendored: .edpa/engine/scripts/ ($N_SCRIPTS scripts, VERSION $ENGINE_VERSION)"
    if [ ! -f ".edpa/engine/scripts/engine.py" ]; then
        warn "engine.py missing from vendored scripts — vendoring looks incomplete"
        hint "/edpa:setup   (or: curl -fsSL https://edpa.technomaton.com/install.sh | sh)"
    fi
else
    warn "Engine not vendored yet in current dir"
    hint "/edpa:setup --with-ci --with-hooks --with-rules"
    hint "(or non-Claude-Code: curl -fsSL https://edpa.technomaton.com/install.sh | sh)"
    if command -v curl >/dev/null 2>&1; then
        ok "curl available — install.sh path is usable"
    else
        warn "curl not on PATH — use /edpa:setup from Claude Code instead"
    fi
fi

# --- 4. EDPA config seeded -------------------------------------------------
step 4 "EDPA config (.edpa/config/)"
CFG_OK=1
for f in edpa.yaml people.yaml; do
    if [ -f ".edpa/config/$f" ]; then
        ok ".edpa/config/$f present"
    else
        CFG_OK=0
        warn ".edpa/config/$f not present yet"
        hint "/edpa:setup   (seeds it from the engine template)"
    fi
done
# id_counters.yaml is the local-first ID allocator state.
if [ -f ".edpa/config/id_counters.yaml" ]; then
    ok ".edpa/config/id_counters.yaml present (local ID allocator)"
else
    CFG_OK=0
    warn ".edpa/config/id_counters.yaml not present yet"
    hint "/edpa:setup   (seeds counters from existing backlog file IDs)"
fi
# cw_heuristics.yaml carries the signal/gate/yaml_edit weights the engine reads.
if [ -f ".edpa/config/cw_heuristics.yaml" ]; then
    ok ".edpa/config/cw_heuristics.yaml present (CW signal weights)"
else
    warn ".edpa/config/cw_heuristics.yaml not present yet (engine falls back to a minimal default)"
    hint "/edpa:setup   (seeds the documented weights — recommended)"
fi

# project.name sanity — flag if still the template placeholder.
if [ -f ".edpa/config/edpa.yaml" ]; then
    PROJ_NAME=$(python3 -c "import yaml; e=yaml.safe_load(open('.edpa/config/edpa.yaml')) or {}; print((e.get('project') or {}).get('name',''))" 2>/dev/null)
    if [ "$PROJ_NAME" = "My Project" ] || [ -z "$PROJ_NAME" ]; then
        warn "edpa.yaml project.name is still the template placeholder ('$PROJ_NAME')"
        hint "cp ~/projects/edpa/docs/kashealth-pilot/edpa.yaml.example .edpa/config/edpa.yaml"
    else
        ok "edpa.yaml project.name: $PROJ_NAME"
    fi
fi

# --- 5. People registry sanity --------------------------------------------
step 5 "People registry (.edpa/config/people.yaml)"
if [ -f ".edpa/config/people.yaml" ]; then
    N_PEOPLE=$(python3 -c "import yaml; e=yaml.safe_load(open('.edpa/config/people.yaml')) or {}; print(len(e.get('people') or []))" 2>/dev/null || echo "?")
    if [ "$N_PEOPLE" = "0" ] || [ "$N_PEOPLE" = "?" ]; then
        warn "people.yaml has no team members yet"
        hint "cp ~/projects/edpa/docs/kashealth-pilot/people.yaml.example .edpa/config/people.yaml"
    else
        ok "people.yaml: $N_PEOPLE member(s) registered"
    fi
else
    warn "people.yaml not present (covered in step 4)"
fi

# --- Summary ---------------------------------------------------------------
printf "\n"
if [ "$FAIL" -gt 0 ]; then
    printf "$(c_red '✗ %d hard failure(s)'), $(c_yel '%d warning(s)')\n" "$FAIL" "$WARN"
    printf "Resolve the ✗ items above before running the engine.\n"
    exit 1
fi
if [ "$WARN" -gt 0 ]; then
    printf "$(c_grn '✓ ready')  $(c_yel '(%d warning(s) — review before kickoff)')\n" "$WARN"
    printf "Warnings are usually just 'run /edpa:setup first'. No GitHub needed.\n"
    exit 0
fi
printf "$(c_grn '✓ ready') — every check passed. Engine is good to run.\n"
exit 0
