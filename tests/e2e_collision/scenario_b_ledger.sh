#!/usr/bin/env bash
# EDPA Collision Scenario B — cut-over to the remote ID ledger (ADR-014).
#
# Hermetic: a local bare repository plays `origin`, so unlike scenario_a.sh
# this needs no GitHub account and creates nothing outside a temp dir.
# It drives the real thing end to end — project_setup.py installs the real
# git hooks, items are created with backlog.py, commits and pushes run the
# hooks — for two developers, a stale worktree and one leftover pre-ledger
# collision:
#
#   1. project on main under the local counter
#   2. BEFORE  worktrees of one clone share a sequence; a second developer
#              still mints the same number
#   3. CUT-OVER  id_counter.py init-remote + one opt-in commit
#   4. AFTER   main checkout, a worktree WITHOUT the opt-in commit, two
#              worktrees creating at the same instant, and a developer who
#              only fetched the opt-in all reserve distinct IDs
#   5. the hooks block an item the ledger does not back
#   6. post-cut-over ticket branches merge with no ID or counter conflict
#   7. the leftover collision is blocked at push and repaired from the ledger
#
# Usage:  bash tests/e2e_collision/scenario_b_ledger.sh [--keep]
# Exit:   0 when every expectation holds, 1 otherwise.
set -u

EDPA_REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
W="$(mktemp -d "${TMPDIR:-/tmp}/edpa-ledger-e2e.XXXXXX")"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
cleanup() { [ "$KEEP" = 1 ] && echo "kept: $W" || rm -rf "$W"; }
trap cleanup EXIT
cd "$W"

# Keep the developer's own git config (hooks path, signing) out of it.
export GIT_CONFIG_GLOBAL="$W/gitconfig" GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
: > "$GIT_CONFIG_GLOBAL"
unset EDPA_ID_AUTHORITY

SETUP="python3 $EDPA_REPO/plugin/edpa/scripts/project_setup.py"
FAILS=0
say() { printf '\n== %s\n' "$*"; }
ok()  { printf '   OK    %s\n' "$*"; }
bad() { printf '   FAIL  %s\n' "$*"; FAILS=$((FAILS + 1)); }
expect() { if [ "$2" = "$3" ]; then ok "$1 ($3)"; else bad "$1 — expected '$2', got '$3'"; fi; }
allocator() { ( cd "$1" && shift && python3 .edpa/engine/scripts/id_counter.py "$@" ); }
add() { # add <checkout> <Type> <title> [parent] -> the new ID, or the error text
  local out id
  out=$(cd "$1" && python3 .edpa/engine/scripts/backlog.py add --type "$2" --title "$3" ${4:+--parent "$4"} 2>&1)
  id=$(printf '%s\n' "$out" | sed -n 's/.*Created (local): \([A-Z]*-[0-9]*\).*/\1/p' | head -1)
  if [ -n "$id" ]; then echo "$id"; else printf '%s' "$out" | grep -v '^$' | tail -3 | tr '\n' ' '; fi
}
mkclone() {
  git clone -q origin.git "$1" 2>/dev/null
  git -C "$1" config user.name "$1"
  git -C "$1" config user.email "$1@edpa-test.local"
  git -C "$1" config commit.gpgsign false
}
story_file() { # story_file <checkout> <ID> <title>
  printf -- "---\nid: %s\ntype: Story\ntitle: %s\nstatus: Funnel\nparent: F-1\ncreated_at: '2026-10-08T10:00:00Z'\n---\n" \
    "$2" "$3" > "$1/.edpa/backlog/stories/$2.md"
}

say "1. project on main, local counter, real hooks"
git init -q --bare -b main origin.git
mkclone anna
( cd anna && git commit -q --allow-empty -m "chore(no-ticket): init" && $SETUP --root . --with-hooks >/dev/null 2>&1 \
  && git add -A && git commit -q -m "chore(no-ticket): edpa setup" )
expect "git hooks installed" "4" "$(ls anna/.git/hooks | grep -c -E '^(pre-commit|commit-msg|post-commit|pre-push)$')"
expect "first Initiative" "I-1" "$(add anna Initiative "Platform")"
expect "first Epic"       "E-1" "$(add anna Epic "Core" I-1)"
expect "first Feature"    "F-1" "$(add anna Feature "Search" E-1)"
expect "first Story"      "S-1" "$(add anna Story "Index documents" F-1)"
( cd anna && git push -q origin HEAD:main 2>/dev/null )

say "2. BEFORE — one clone shares a sequence, a second developer collides"
git -C anna worktree add -q ../wt-search -b feat/search
git -C anna worktree add -q ../wt-stale -b feat/stale
mkclone boris
( cd boris && $SETUP --root . --with-hooks >/dev/null 2>&1 )
expect "worktree of the same clone" "S-2" "$(add wt-search Story "Query parser" F-1)"
expect "the other developer mints the SAME number" "S-2" "$(add boris Story "Synonyms" F-1)"
( cd anna && git merge -q --no-edit feat/search && git push -q origin HEAD:main 2>/dev/null )

say "3. CUT-OVER — one command, one commit"
allocator anna init-remote --apply --write-config | sed 's/^/   | /'
expect "the opt-in touches only edpa.yaml" "M .edpa/config/edpa.yaml" "$(git -C anna status --porcelain | sed 's/^ *//')"
( cd anna && git add -A .edpa && git commit -q -m "chore(no-ticket): reserve ticket IDs in the shared ledger" \
  && git push -q origin HEAD:main 2>/dev/null )

say "4. AFTER — every path draws from the ledger"
expect "main checkout, numbering continues right after the floor" "S-3" "$(add anna Story "Facets" F-1)"
expect "worktree WITHOUT the opt-in commit" "S-4" "$(add wt-stale Story "Boosting" F-1)"
git -C anna worktree add -q ../wt-a -b feat/a
git -C anna worktree add -q ../wt-b -b feat/b
( add wt-a Story "Parallel A" F-1 > "$W/a.id" ) & ( add wt-b Story "Parallel B" F-1 > "$W/b.id" ) & wait
PA=$(cat "$W/a.id"); PB=$(cat "$W/b.id")
case "$PA $PB" in "S-5 S-6"|"S-6 S-5") ok "two worktrees at the same instant ($PA, $PB)";; *) bad "parallel creation gave '$PA' and '$PB'";; esac
( cd boris && git fetch -q origin )
expect "developer who only FETCHED the opt-in" "S-7" "$(add boris Story "Typos" F-1)"
for wt in wt-stale wt-a wt-b; do
  expect "$wt: commits touching id_counters.yaml" "0" "$(git -C "$wt" log --format= --name-only main..HEAD | grep -c id_counters.yaml)"
done

say "5. the hooks stop what the ledger does not back"
story_file anna S-40 "hand made"
( cd anna && git add .edpa/backlog/stories/S-40.md
  if git commit -q -m "feat(S-40): hand made" 2>"$W/hook.err"; then bad "a hand-made S-40 was committed"
  elif grep -q "S-40 has no reservation in the ID ledger" "$W/hook.err"; then ok "pre-commit: S-40 has no reservation"
  else bad "pre-commit blocked S-40 for another reason: $(tail -2 "$W/hook.err" | tr '\n' ' ')"; fi
  git reset -q --hard HEAD; git clean -qfd .edpa/backlog )
STALE=$(cd anna && EDPA_ID_AUTHORITY=local python3 .edpa/engine/scripts/id_counter.py next --type Story)
story_file anna "$STALE" "minted by an outdated allocator"
( cd anna && git add -A .edpa
  if git commit -q -m "feat($STALE): outdated allocator" 2>"$W/hook2.err"; then bad "$STALE minted outside the ledger was committed"
  elif grep -q "reserved in the ID ledger for a different item" "$W/hook2.err"; then ok "pre-commit: $STALE belongs to someone else's reservation"
  else bad "pre-commit blocked $STALE for another reason: $(tail -2 "$W/hook2.err" | tr '\n' ' ')"; fi
  git reset -q --hard HEAD; git clean -qfd .edpa/backlog )

say "6. post-cut-over ticket branches merge cleanly"
( cd anna && for b in feat/stale feat/a feat/b; do
    git merge -q --no-edit "$b" >"$W/merge.out" 2>&1 || { bad "merge $b: $(grep -m1 CONFLICT "$W/merge.out")"; git merge --abort; }
  done
  expect "conflicts after merging three ticket branches" "0" "$(git diff --name-only --diff-filter=U | wc -l | tr -d ' ')"
  git push -q origin HEAD:main 2>/dev/null || bad "push of main was rejected" )

say "7. the leftover pre-ledger collision is blocked, then repaired from the ledger"
( cd boris
  if git push -q origin HEAD:refs/heads/feat/boris 2>"$W/push.err"; then bad "the colliding S-2 was pushed"
  elif grep -q "S-2 already exists on refs/remotes/origin/main as a different item" "$W/push.err"; then ok "pre-push: S-2 is a different item upstream"
  else bad "pre-push failed for another reason: $(tail -3 "$W/push.err" | tr '\n' ' ')"; fi
  python3 .edpa/engine/scripts/renumber_collisions.py --apply >"$W/renumber.out" 2>&1
  expect "renumbered to a ledger reservation" "S-1 S-7 S-8" "$(ls .edpa/backlog/stories | sed 's/\.md//' | sort -t- -k2 -n | tr '\n' ' ' | sed 's/ $//')"
  expect "renumber left the tracked counter alone" "0" "$(git status --porcelain | grep -c id_counters.yaml)"
  git add -A .edpa
  git commit -q -m "chore(no-ticket): renumber my colliding story" 2>"$W/commit.err" && ok "renamed item passes pre-commit" \
    || bad "commit after renumber: $(tail -2 "$W/commit.err" | tr '\n' ' ')"
  git push -q origin HEAD:refs/heads/feat/boris 2>"$W/push2.err" && ok "push after renumber passes" \
    || bad "push after renumber: $(grep ' - ' "$W/push2.err" | head -2 | tr '\n' ' ')" )

say "8. result"
( cd anna && git pull -q origin main 2>/dev/null
  expect "stories on main" "S-1 S-2 S-3 S-4 S-5 S-6" "$(ls .edpa/backlog/stories | sed 's/\.md//' | sort -t- -k2 -n | tr '\n' ' ' | sed 's/ $//')" )
allocator anna doctor | sed 's/^/   | /'
expect "doctor" "0" "$(allocator anna doctor >/dev/null 2>&1; echo $?)"
allocator anna status --refresh >/dev/null 2>&1
git -C anna log refs/edpa/cache/ids --format='   ledger: %s  [%an]' | head -8

echo
if [ "$FAILS" = 0 ]; then echo "SCENARIO B PASSED"; exit 0; fi
echo "SCENARIO B: $FAILS FAILURE(S)"; exit 1
