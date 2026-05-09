#!/usr/bin/env bash
# EDPA — kashealth pilot pre-flight check
# Exits 0 only when every required item is in place. Prints a fix-it
# command for each missing piece so the operator can copy-paste their
# way to a green check before running project_setup.

set -u
ORG="${KASHEALTH_ORG:-kashealth}"
REPO="${KASHEALTH_REPO:-kas-platform-v1}"
EXPECTED_TYPES=("Initiative" "Epic" "Feature" "Story" "Defect" "Task")
EXPECTED_SCOPES=("admin:org" "project" "repo" "workflow")
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

# --- 1. Toolchain ----------------------------------------------------------
step 1 "Toolchain"
for cmd in python3 git gh; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd: $(command -v "$cmd")"
    else
        fail "$cmd not on PATH"
        hint "install $cmd"
    fi
done

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "?")
PY_OK=$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 10) else "no")' 2>/dev/null || echo "no")
if [ "$PY_OK" = "yes" ]; then
    ok "Python $PY_VERSION (>= 3.10)"
else
    fail "Python $PY_VERSION (need >= 3.10)"
fi

for mod in yaml openpyxl mcp; do
    if python3 -c "import $mod" 2>/dev/null; then
        ok "Python module: $mod"
    else
        warn "Python module $mod missing"
        hint "pip3 install $mod   # also installed automatically by install.sh"
    fi
done

# --- 2. gh auth + scopes ---------------------------------------------------
step 2 "GitHub CLI authentication"
GH_STATUS=$(gh auth status 2>&1 || true)
if printf '%s' "$GH_STATUS" | grep -q "Logged in to github.com"; then
    GH_USER=$(printf '%s' "$GH_STATUS" | grep -oE 'account [^ ]+' | head -1 | awk '{print $2}')
    ok "Authenticated as: $GH_USER"
else
    fail "gh not authenticated"
    hint "gh auth login"
fi

SCOPES_LINE=$(printf '%s' "$GH_STATUS" | grep -i "Token scopes" | head -1)
for scope in "${EXPECTED_SCOPES[@]}"; do
    if printf '%s' "$SCOPES_LINE" | grep -q "$scope"; then
        ok "scope: $scope"
    else
        fail "scope missing: $scope"
        hint "gh auth refresh -h github.com -s ${scope//,/}"
    fi
done

# --- 3. Org access + members ----------------------------------------------
step 3 "Org access ($ORG)"
ORG_MEMBERS=$(gh api "orgs/$ORG/members" 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(" ".join([m["login"] for m in d]))
except Exception:
    print("")
')
if [ -n "$ORG_MEMBERS" ]; then
    ok "$ORG members: $ORG_MEMBERS"
else
    fail "Cannot list members of $ORG"
    hint "Check that you are an owner / member of the $ORG org"
fi

# --- 4. Target repo --------------------------------------------------------
step 4 "Target repo ($ORG/$REPO)"
REPO_INFO=$(gh repo view "$ORG/$REPO" --json name,defaultBranchRef,visibility 2>&1)
if printf '%s' "$REPO_INFO" | grep -q '"name"'; then
    REPO_BRANCH=$(printf '%s' "$REPO_INFO" | python3 -c 'import json,sys; print(json.load(sys.stdin)["defaultBranchRef"]["name"])')
    REPO_VIS=$(printf '%s' "$REPO_INFO" | python3 -c 'import json,sys; print(json.load(sys.stdin)["visibility"])')
    ok "$ORG/$REPO ($REPO_VIS, default=$REPO_BRANCH)"
else
    fail "$ORG/$REPO not accessible"
    hint "Check that the repo exists and your token has read access"
fi

# --- 5. Org Issue Types ---------------------------------------------------
step 5 "Org-level Issue Types"
TYPES_JSON=$(gh api graphql -f query="{ organization(login: \"$ORG\") { issueTypes(first: 20) { nodes { name } } } }" 2>/dev/null || true)
if [ -n "$TYPES_JSON" ]; then
    PRESENT_TYPES=$(printf '%s' "$TYPES_JSON" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    nodes = d["data"]["organization"]["issueTypes"]["nodes"]
    print(" ".join(n["name"] for n in nodes))
except Exception:
    print("")
')
    for t in "${EXPECTED_TYPES[@]}"; do
        if printf '%s' "$PRESENT_TYPES" | grep -qw "$t"; then
            ok "Issue Type: $t"
        else
            fail "Issue Type missing: $t"
            hint "python3 plugin/edpa/scripts/issue_types.py setup --org $ORG"
        fi
    done
else
    fail "Could not query org Issue Types (GraphQL failed)"
    hint "gh api graphql -f query='...issueTypes...'  # debug manually"
fi

# --- 6. Existing Projects (sanity — pilot expects 0 conflicts) -------------
step 6 "Existing GitHub Projects (info only)"
PROJ_TITLES=$(gh project list --owner "$ORG" --format json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(" ".join("#" + str(p["number"]) + ":" + p["title"] for p in d.get("projects", [])))
except Exception:
    print("")
')
if [ -n "$PROJ_TITLES" ]; then
    warn "Existing projects: $PROJ_TITLES"
    hint "Pick a unique --project-title for project_setup.py to avoid clashes"
else
    ok "No existing projects in $ORG (clean slate)"
fi

# --- 7. Local working tree state ------------------------------------------
step 7 "Local working tree (current dir)"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    ok "Inside a git repo: $(git rev-parse --show-toplevel)"
    LOCAL_NAME=$(git config user.name || true)
    LOCAL_EMAIL=$(git config user.email || true)
    if [ -n "$LOCAL_NAME" ] && [ -n "$LOCAL_EMAIL" ]; then
        ok "git user.name + user.email: $LOCAL_NAME <$LOCAL_EMAIL>"
    else
        fail "git user.name / user.email not set"
        hint "git config --global user.name 'Your Name'"
        hint "git config --global user.email 'you@kashealth.cz'"
        hint "(without these, EDPA auto-commit feature in v1.8.1+ skips silently)"
    fi
else
    warn "Not inside a git repo — re-run preflight from inside kas-platform-v1"
fi

# --- 8. EDPA install state -------------------------------------------------
step 8 "EDPA plugin state"
if [ -d ".claude/edpa/scripts" ]; then
    PLUGIN_VERSION=$(python3 -c 'import json; print(json.load(open(".claude/.claude-plugin/plugin.json"))["version"])' 2>/dev/null || echo "?")
    ok "Plugin installed: v$PLUGIN_VERSION"
    # Look up the latest published release dynamically. A hardcoded
    # version would silently lie to operators on every release bump
    # and (worse) flag a perfectly current install as "outdated" on
    # day 1 of the pilot.
    LATEST=$(gh release list --repo technomaton/edpa --limit 1 --json tagName \
        --jq '.[0].tagName' 2>/dev/null | sed 's/^v//')
    if [ -n "$LATEST" ] && [ "$PLUGIN_VERSION" != "$LATEST" ]; then
        warn "Plugin version $PLUGIN_VERSION (latest published: $LATEST)"
        hint "curl -fsSL https://edpa.technomaton.com/install.sh | sh   # to upgrade"
    fi
else
    warn "EDPA plugin not yet installed in current dir"
    hint "curl -fsSL https://edpa.technomaton.com/install.sh | sh"
fi

if [ -f ".edpa/config/edpa.yaml" ]; then
    SYNC_ORG=$(python3 -c "import yaml; e=yaml.safe_load(open('.edpa/config/edpa.yaml')); print((e.get('sync') or {}).get('github_org', ''))")
    SYNC_REPO=$(python3 -c "import yaml; e=yaml.safe_load(open('.edpa/config/edpa.yaml')); print((e.get('sync') or {}).get('github_repo', ''))")
    if [ "$SYNC_ORG" = "$ORG" ] && [ "$SYNC_REPO" = "$REPO" ]; then
        ok "edpa.yaml sync.github_org/repo = $ORG/$REPO"
    elif [ -n "$SYNC_ORG$SYNC_REPO" ]; then
        warn "edpa.yaml points at $SYNC_ORG/$SYNC_REPO (expected $ORG/$REPO)"
        hint "edit .edpa/config/edpa.yaml or copy from docs/kashealth-pilot/edpa.yaml.example"
    else
        warn ".edpa/config/edpa.yaml has no sync.github_org / sync.github_repo set"
        hint "cp ~/projects/edpa/docs/kashealth-pilot/edpa.yaml.example .edpa/config/edpa.yaml"
    fi
else
    warn ".edpa/config/edpa.yaml not present yet"
    hint "(install.sh creates it from template)"
fi

# --- Summary ---------------------------------------------------------------
printf "\n"
if [ "$FAIL" -gt 0 ]; then
    printf "$(c_red '✗ %d hard failure(s)'), $(c_yel '%d warning(s)')\n" "$FAIL" "$WARN"
    printf "Resolve the ✗ items above before running project_setup.py.\n"
    exit 1
fi
if [ "$WARN" -gt 0 ]; then
    printf "$(c_grn '✓ ready')  $(c_yel '(%d warning(s) — review before kickoff)')\n" "$WARN"
    exit 0
fi
printf "$(c_grn '✓ ready') — every check passed. You can now run project_setup.py.\n"
exit 0
