#!/usr/bin/env bash
# EDPA V2 E2E cleanup — archives sandbox GitHub repo + optionally removes local /tmp dir.
#
# Usage:
#   bash tests/e2e_v2_full/phases/99_cleanup.sh                  # archives, removes local
#   EDPA_E2E_KEEP_SANDBOX=1 bash tests/e2e_v2_full/phases/99_cleanup.sh  # archives, keeps local
#
# Reads sandbox identity from .e2e_state.json in EDPA_E2E_SANDBOX_DIR.

set -euo pipefail

# Default SANDBOX_DIR resolution:
#   1. EDPA_E2E_SANDBOX_DIR env var (set by run_e2e.sh)
#   2. /tmp/edpa-e2e-<tag> derived from /tmp/edpa-e2e-current-run-tag
#      (written by the coordinator pre-flight step)
if [ -z "${EDPA_E2E_SANDBOX_DIR:-}" ] && [ -f /tmp/edpa-e2e-current-run-tag ]; then
  TAG="$(cat /tmp/edpa-e2e-current-run-tag)"
  if [ -n "${TAG}" ]; then
    EDPA_E2E_SANDBOX_DIR="/tmp/edpa-e2e-${TAG}"
  fi
fi
SANDBOX_DIR="${EDPA_E2E_SANDBOX_DIR:-}"

if [ -z "${SANDBOX_DIR}" ]; then
  echo "ERROR: cannot resolve sandbox dir."
  echo "  Set EDPA_E2E_SANDBOX_DIR or write the RUN_TAG to /tmp/edpa-e2e-current-run-tag."
  exit 1
fi

if [ ! -f "${SANDBOX_DIR}/.e2e_state.json" ]; then
  echo "ERROR: ${SANDBOX_DIR}/.e2e_state.json not found"
  exit 1
fi

# Accept either historical key name: repo_full_name (legacy) or gh_repo (current).
REPO_FULL=$(python3 -c "
import json, sys
s = json.load(open('${SANDBOX_DIR}/.e2e_state.json'))
print(s.get('repo_full_name') or s.get('gh_repo') or '')
")
RUN_TAG=$(python3 -c "import json; print(json.load(open('${SANDBOX_DIR}/.e2e_state.json'))['run_tag'])")

if [ -z "${REPO_FULL}" ]; then
  echo "ERROR: .e2e_state.json has neither repo_full_name nor gh_repo"
  exit 1
fi

echo "Cleanup for run: ${RUN_TAG}"
echo "  sandbox dir: ${SANDBOX_DIR}"
echo "  repo: ${REPO_FULL}"

# Archive GitHub repo
echo "Archiving GitHub repo..."
if gh repo view "${REPO_FULL}" --json isArchived --jq .isArchived | grep -q true; then
  echo "  already archived"
else
  gh repo archive "${REPO_FULL}" --yes 2>&1 | tail -3
fi

# Safety check + remove local dir
if [ "${EDPA_E2E_KEEP_SANDBOX:-0}" = "1" ]; then
  echo "EDPA_E2E_KEEP_SANDBOX=1 — keeping local sandbox at ${SANDBOX_DIR}"
else
  case "${SANDBOX_DIR}" in
    /tmp/edpa-e2e-*)
      echo "Removing local sandbox: ${SANDBOX_DIR}"
      rm -rf "${SANDBOX_DIR}"
      ;;
    *)
      echo "SAFETY: refusing to rm SANDBOX_DIR=${SANDBOX_DIR} (not under /tmp/edpa-e2e-*)"
      exit 2
      ;;
  esac
fi

echo "Cleanup complete."
echo "Archived repo URL: https://github.com/${REPO_FULL}"
