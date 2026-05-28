#!/usr/bin/env bash
# EDPA Collision Scenario A — basic dual Story collision end-to-end test.
set -euo pipefail

RUN_TAG="$(date -u +%Y%m%d-%H%M%S)-$(openssl rand -hex 3)"
REPO_NAME="edpa-collision-test-${RUN_TAG}"
GH_OWNER="technomaton"
GH_REPO="${GH_OWNER}/${REPO_NAME}"
WORK_DIR="/tmp/edpa-collision-${RUN_TAG}"
INIT_DIR="${WORK_DIR}/init"
ALICE_DIR="${WORK_DIR}/alice"
BOB_DIR="${WORK_DIR}/bob"
EDPA_REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

echo "================================================================="
echo "Scenario A — Basic dual Story collision"
echo "================================================================="
echo "RUN_TAG    : ${RUN_TAG}"
echo "GH repo    : ${GH_REPO}"
echo "Work dir   : ${WORK_DIR}"
echo "================================================================="

mkdir -p "${WORK_DIR}"

echo ""
echo ">>> Phase 1: Init sandbox with minimal EDPA structure"
mkdir -p "${INIT_DIR}"
cd "${INIT_DIR}"

git init -q -b main
git config user.email "init@edpa-test.local"
git config user.name "EDPA Test Init"
git config commit.gpgsign false

mkdir -p .edpa/backlog/{initiatives,epics,features,stories,defects,events,risks}
mkdir -p .edpa/config

cat > .edpa/config/id_counters.yaml <<EOF
counters:
  Story: 4
EOF

for n in 1 2 3 4; do
  cat > ".edpa/backlog/stories/S-${n}.md" <<EOF
---
id: S-${n}
type: Story
title: Initial story ${n}
status: Done
---
Initial seed story ${n}.
EOF
done

mkdir -p .edpa/engine/scripts
cp "${EDPA_REPO}/plugin/edpa/scripts/renumber_collisions.py" .edpa/engine/scripts/
cp "${EDPA_REPO}/plugin/edpa/scripts/id_counter.py" .edpa/engine/scripts/

cat > README.md <<EOF
# EDPA Collision Test — ${RUN_TAG}

Throwaway sandbox for testing ID collision resolution.
EOF

# Ignore Python compile artifacts (otherwise renumber_collisions invocation
# generates __pycache__/*.pyc that get tracked)
cat > .gitignore <<'EOF'
__pycache__/
*.pyc
*.pyo
EOF

git add -A
git commit -q -m "initial: seed EDPA backlog + counters + renumber script"

gh repo create "${GH_REPO}" --private --source=. --remote=origin \
  --description "EDPA collision test sandbox — Scenario A · ${RUN_TAG}" \
  --push >/dev/null 2>&1
echo "✓ GH repo created + initial push: ${GH_REPO}"

echo ""
echo ">>> Phase 2: Alice clones, allocates S-5 (Auth), opens PR"
gh repo clone "${GH_REPO}" "${ALICE_DIR}" -- -q
cd "${ALICE_DIR}"
git config user.email "alice@edpa-test.local"
git config user.name "Alice"
git config commit.gpgsign false
git checkout -q -b feature/auth-story

cat > .edpa/config/id_counters.yaml <<EOF
counters:
  Story: 5
EOF
cat > .edpa/backlog/stories/S-5.md <<EOF
---
id: S-5
type: Story
title: "Auth: JWT validation"
assignee: alice
status: Implementing
---
Add JWT validation middleware for the Auth feature.
EOF
git add -A
git commit -q -m "feat(S-5): add Auth JWT validation story"
git push -q origin feature/auth-story
PR_ALICE_URL=$(gh pr create --title "feat(S-5): add Auth JWT validation story" \
  --body "Implements S-5 for Auth feature." --base main --head feature/auth-story 2>&1 | grep -o 'https://[^ ]*')
PR_ALICE_NUM=$(basename "$PR_ALICE_URL")
echo "✓ Alice PR #${PR_ALICE_NUM}: ${PR_ALICE_URL}"

echo ""
echo ">>> Phase 3: Bob clones (PARALLEL, BEFORE alice merges) and allocates S-5 too"
gh repo clone "${GH_REPO}" "${BOB_DIR}" -- -q
cd "${BOB_DIR}"
git config user.email "bob@edpa-test.local"
git config user.name "Bob"
git config commit.gpgsign false
git checkout -q -b feature/reports-story

cat > .edpa/config/id_counters.yaml <<EOF
counters:
  Story: 5
EOF
cat > .edpa/backlog/stories/S-5.md <<EOF
---
id: S-5
type: Story
title: "Reports: PDF export"
assignee: bob
status: Implementing
---
Add PDF export to the Reports feature.
EOF
git add -A
git commit -q -m "feat(S-5): add Reports PDF export story"
git push -q origin feature/reports-story
PR_BOB_URL=$(gh pr create --title "feat(S-5): add Reports PDF export story" \
  --body "Implements S-5 for Reports feature." --base main --head feature/reports-story 2>&1 | grep -o 'https://[^ ]*')
PR_BOB_NUM=$(basename "$PR_BOB_URL")
echo "✓ Bob PR #${PR_BOB_NUM}: ${PR_BOB_URL}"

echo ""
echo ">>> Phase 4: Alice's PR #${PR_ALICE_NUM} merges first (squash)"
gh pr merge "${PR_ALICE_NUM}" --repo "${GH_REPO}" --squash --delete-branch >/dev/null 2>&1
echo "✓ Alice PR #${PR_ALICE_NUM} merged"

sleep 1
gh api "repos/${GH_REPO}/contents/.edpa/backlog/stories/S-5.md" --jq .name >/dev/null
echo "✓ main has .edpa/backlog/stories/S-5.md (Auth content)"

echo ""
echo ">>> Phase 5: Bob's PR #${PR_BOB_NUM} mergeability"
sleep 3
BOB_MERGEABLE=$(gh pr view "${PR_BOB_NUM}" --repo "${GH_REPO}" --json mergeable --jq .mergeable)
echo "  mergeable: ${BOB_MERGEABLE}"
if [ "${BOB_MERGEABLE}" = "CONFLICTING" ]; then
  echo "✓ Conflict detected (expected)"
fi

echo ""
echo ">>> Phase 6: Bob runs renumber_collisions.py"
cd "${BOB_DIR}"
git fetch -q origin main

RENUMBER_OUT=$(python3 .edpa/engine/scripts/renumber_collisions.py --apply 2>&1)
echo "${RENUMBER_OUT}" | sed 's/^/  /'

if [ ! -f .edpa/backlog/stories/S-5.md ] && [ -f .edpa/backlog/stories/S-6.md ]; then
  echo "✓ S-5.md renamed → S-6.md"
else
  echo "✗ FAIL: S-5.md should be gone, S-6.md should exist"
  ls .edpa/backlog/stories/
  exit 1
fi

if grep -q "^id: S-6$" .edpa/backlog/stories/S-6.md; then
  echo "✓ S-6.md has id: S-6"
fi

COUNTER=$(grep "Story:" .edpa/config/id_counters.yaml | awk '{print $2}')
if [ "${COUNTER}" = "6" ]; then
  echo "✓ id_counters.yaml: Story=6"
fi

echo ""
echo ">>> Phase 7: Bob commits + merges main (resolves id_counters)"
git add -A
git commit -q -m "renumber(S-5→S-6): collision with main"
echo "  Renumber committed."

MERGE_OUT=$(git merge --no-edit origin/main 2>&1 || true)
echo "${MERGE_OUT}" | sed 's/^/  /'

if echo "${MERGE_OUT}" | grep -q "CONFLICT"; then
  CONFLICTED=$(git diff --name-only --diff-filter=U)
  echo "  Conflicted files: ${CONFLICTED}"
  if echo "${CONFLICTED}" | grep -q "id_counters.yaml"; then
    cat > .edpa/config/id_counters.yaml <<EOF
counters:
  Story: 6
EOF
    git add .edpa/config/id_counters.yaml
    echo "  → resolved id_counters.yaml (took max: 6)"
  fi
  STILL=$(git diff --name-only --diff-filter=U)
  if [ -n "${STILL}" ]; then
    echo "✗ Unresolved: ${STILL}"; exit 1
  fi
  git commit -q --no-edit -m "Merge 'main' into feature/reports-story"
  echo "  ✓ Merge resolved"
elif echo "${MERGE_OUT}" | grep -q "Already up to date"; then
  echo "  (no merge needed — branch already includes main)"
else
  echo "  ✓ Auto-merge succeeded (no conflict)"
fi

git push -q origin feature/reports-story
echo "  ✓ Pushed feature/reports-story"

echo ""
echo ">>> Phase 8: Bob's PR re-check + squash merge"
# Poll mergeability — GH returns STALE CONFLICTING value initially even
# after the conflict was resolved. Real recompute can take ~30s.
# Don't break on CONFLICTING for first 6 attempts (~30s); only on MERGEABLE.
# Query the verbose form to potentially trigger background recompute.
for i in 1 2 3 4 5 6 7 8 9 10; do
  GH_STATE=$(gh pr view "${PR_BOB_NUM}" --repo "${GH_REPO}" \
    --json mergeable,mergeStateStatus 2>&1)
  BOB_MERGEABLE_2=$(echo "${GH_STATE}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mergeable','?'))")
  BOB_STATE=$(echo "${GH_STATE}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mergeStateStatus','?'))")
  echo "  attempt ${i}: mergeable=${BOB_MERGEABLE_2} state=${BOB_STATE}"
  if [ "${BOB_MERGEABLE_2}" = "MERGEABLE" ]; then break; fi
  # For first 6 attempts, ignore CONFLICTING (likely stale cache).
  # After 6 attempts: accept the answer.
  if [ "${i}" -ge 6 ] && [ "${BOB_MERGEABLE_2}" = "CONFLICTING" ]; then break; fi
  sleep 5
done

if [ "${BOB_MERGEABLE_2}" = "MERGEABLE" ]; then
  gh pr merge "${PR_BOB_NUM}" --repo "${GH_REPO}" --squash --delete-branch >/dev/null 2>&1
  echo "✓ Bob PR #${PR_BOB_NUM} merged"
else
  echo "✗ Bob's PR still ${BOB_MERGEABLE_2}, expected MERGEABLE"
  gh pr view "${PR_BOB_NUM}" --repo "${GH_REPO}"
  exit 1
fi

echo ""
echo ">>> Phase 9: Verify final state on main"
FINAL_DIR="${WORK_DIR}/final"
gh repo clone "${GH_REPO}" "${FINAL_DIR}" -- -q
cd "${FINAL_DIR}"

S5_TITLE=$(grep "^title:" .edpa/backlog/stories/S-5.md | sed 's/title: //; s/"//g')
S6_TITLE=$(grep "^title:" .edpa/backlog/stories/S-6.md | sed 's/title: //; s/"//g')
COUNTER_FINAL=$(grep "Story:" .edpa/config/id_counters.yaml | awk '{print $2}')

echo "  S-5 title:    ${S5_TITLE}"
echo "  S-6 title:    ${S6_TITLE}"
echo "  Counter:      Story=${COUNTER_FINAL}"
echo "  Total stories: $(ls .edpa/backlog/stories/*.md | wc -l | tr -d ' ')"

ERRORS=0
[ -f .edpa/backlog/stories/S-5.md ] || { echo "✗ S-5.md missing"; ERRORS=$((ERRORS+1)); }
[ -f .edpa/backlog/stories/S-6.md ] || { echo "✗ S-6.md missing"; ERRORS=$((ERRORS+1)); }
[ "${S5_TITLE}" = "Auth: JWT validation" ] || { echo "✗ S-5 title: ${S5_TITLE}"; ERRORS=$((ERRORS+1)); }
[ "${S6_TITLE}" = "Reports: PDF export" ] || { echo "✗ S-6 title: ${S6_TITLE}"; ERRORS=$((ERRORS+1)); }
[ "${COUNTER_FINAL}" = "6" ] || { echo "✗ Counter: ${COUNTER_FINAL}"; ERRORS=$((ERRORS+1)); }

if [ "${ERRORS}" -eq 0 ]; then
  echo ""
  echo "================================================================="
  echo "✓ SCENARIO A PASS"
  echo "================================================================="
else
  echo "✗ SCENARIO A FAIL — ${ERRORS} assertions"
  exit 1
fi

echo ""
echo ">>> Phase 10: Cleanup"
gh repo archive "${GH_REPO}" --yes >/dev/null 2>&1 || echo "  (archive failed)"
echo "  Archived: ${GH_REPO}"
if [ "${KEEP_WORK_DIR:-0}" != "1" ]; then
  rm -rf "${WORK_DIR}"
  echo "  Removed: ${WORK_DIR}"
fi
echo ""
echo "Done."
