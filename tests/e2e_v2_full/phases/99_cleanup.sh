#!/usr/bin/env bash
# EDPA V2 E2E cleanup — archives sandbox GitHub repo + optionally removes local /tmp dir.
#
# Usage:
#   bash tests/e2e_v2_full/phases/99_cleanup.sh                  # archives, removes local
#   EDPA_E2E_KEEP_SANDBOX=1 bash tests/e2e_v2_full/phases/99_cleanup.sh  # archives, keeps local
#
# Reads sandbox identity from .e2e_state.json in EDPA_E2E_SANDBOX_DIR.

set -euo pipefail

SANDBOX_DIR="${EDPA_E2E_SANDBOX_DIR:-/tmp/edpa-e2e-20260527-142316-c6ac4db8}"

if [ ! -f "${SANDBOX_DIR}/.e2e_state.json" ]; then
  echo "ERROR: ${SANDBOX_DIR}/.e2e_state.json not found"
  exit 1
fi

REPO_FULL=$(python3 -c "import json; print(json.load(open('${SANDBOX_DIR}/.e2e_state.json'))['repo_full_name'])")
RUN_TAG=$(python3 -c "import json; print(json.load(open('${SANDBOX_DIR}/.e2e_state.json'))['run_tag'])")

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
