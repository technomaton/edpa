#!/usr/bin/env bash
# EDPA V2 — Full End-to-End Test Harness
#
# Top-level orchestrator for the multi-PI E2E exercise. Discovers phase
# scripts under tests/e2e_v2_full/phases/ and runs them in lexicographic
# order. Each phase is either a .sh (bash) or .py (python3) file.
#
# Missing phases are skipped (reported, no failure) so the harness can
# evolve incrementally. Non-zero exit from any executed phase aborts
# the run.
#
# See tests/e2e_v2_full/README.md for prerequisites, env vars, phase
# numbering, and cleanup expectations.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash tests/e2e_v2_full/run_e2e.sh [--help]

Runs the EDPA V2 full E2E test (2 PIs x 5 iterations each).

Environment variables (all optional):
  EDPA_E2E_RUN_TAG       Unique tag for this run.
                         Default: $(date -u +%Y%m%d-%H%M%S)-<openssl rand>
  EDPA_E2E_SANDBOX_DIR   Local sandbox project root.
                         Default: /tmp/edpa-e2e-${EDPA_E2E_RUN_TAG}
  EDPA_E2E_GH_OWNER      GitHub org/user for the sandbox repo.
                         Default: technomaton
  EDPA_E2E_CI_MODE       hybrid | real | synthetic.
                         Default: hybrid
  EDPA_E2E_DRY_RUN       0 | 1 — print phase plan only.
                         Default: 0
  EDPA_E2E_KEEP_SANDBOX  0 | 1 — keep local sandbox after the run.
                         Default: 0
  EDPA_REPO_ROOT         Override EDPA repo root detection.
                         Default: $(git rev-parse --show-toplevel)

Examples:
  bash tests/e2e_v2_full/run_e2e.sh
  EDPA_E2E_DRY_RUN=1 bash tests/e2e_v2_full/run_e2e.sh
  EDPA_E2E_CI_MODE=synthetic bash tests/e2e_v2_full/run_e2e.sh
USAGE
}

# --- Argument parsing (only --help is recognised) ---
for arg in "${@:-}"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    "")
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# --- Resolve harness location + EDPA repo root ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PHASES_DIR="${SCRIPT_DIR}/phases"

if [[ -n "${EDPA_REPO_ROOT:-}" ]]; then
  REPO_ROOT="${EDPA_REPO_ROOT}"
else
  if ! REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"; then
    echo "ERROR: cannot resolve EDPA repo root from ${SCRIPT_DIR}." >&2
    echo "       Set EDPA_REPO_ROOT or run from inside a checkout of the EDPA repo." >&2
    exit 1
  fi
fi

# --- Generate RUN_TAG if not provided ---
if [[ -z "${EDPA_E2E_RUN_TAG:-}" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not found on PATH — required for RUN_TAG generation." >&2
    echo "       Either install openssl or set EDPA_E2E_RUN_TAG explicitly." >&2
    exit 1
  fi
  RUN_TAG="$(date -u +%Y%m%d-%H%M%S)-$(openssl rand -hex 4)"
else
  RUN_TAG="${EDPA_E2E_RUN_TAG}"
fi

# --- Resolve remaining env vars with defaults ---
SANDBOX_DIR="${EDPA_E2E_SANDBOX_DIR:-/tmp/edpa-e2e-${RUN_TAG}}"
GH_OWNER="${EDPA_E2E_GH_OWNER:-technomaton}"
CI_MODE="${EDPA_E2E_CI_MODE:-hybrid}"
DRY_RUN="${EDPA_E2E_DRY_RUN:-0}"
KEEP_SANDBOX="${EDPA_E2E_KEEP_SANDBOX:-0}"

# --- Validate CI_MODE ---
case "${CI_MODE}" in
  hybrid|real|synthetic) ;;
  *)
    echo "ERROR: EDPA_E2E_CI_MODE must be 'hybrid', 'real', or 'synthetic' (got: '${CI_MODE}')." >&2
    exit 1
    ;;
esac

# --- Validate boolean-shaped vars ---
for var_name in DRY_RUN KEEP_SANDBOX; do
  # shellcheck disable=SC1083
  val="$(eval "echo \"\${$var_name}\"")"
  case "${val}" in
    0|1) ;;
    *)
      echo "ERROR: ${var_name} must be 0 or 1 (got: '${val}')." >&2
      exit 1
      ;;
  esac
done

# --- Export resolved values so phase scripts can pick them up ---
export EDPA_E2E_RUN_TAG="${RUN_TAG}"
export EDPA_E2E_SANDBOX_DIR="${SANDBOX_DIR}"
export EDPA_E2E_GH_OWNER="${GH_OWNER}"
export EDPA_E2E_CI_MODE="${CI_MODE}"
export EDPA_E2E_DRY_RUN="${DRY_RUN}"
export EDPA_E2E_KEEP_SANDBOX="${KEEP_SANDBOX}"
export EDPA_REPO_ROOT="${REPO_ROOT}"

# --- Banner ---
REPO_TARGET="${GH_OWNER}/edpa-e2e-${RUN_TAG}"
echo "======================================================================"
echo "EDPA V2 — Full E2E Test"
echo "======================================================================"
echo "RUN_TAG          : ${RUN_TAG}"
echo "SANDBOX_DIR      : ${SANDBOX_DIR}"
echo "EDPA repo root   : ${REPO_ROOT}"
echo "GH sandbox repo  : ${REPO_TARGET}"
echo "CI_MODE          : ${CI_MODE}"
echo "DRY_RUN          : ${DRY_RUN}"
echo "KEEP_SANDBOX     : ${KEEP_SANDBOX}"
echo "Phases dir       : ${PHASES_DIR}"
echo "======================================================================"
echo ""

# --- Discover phase scripts ---
declare -a PHASE_FILES=()
if [[ -d "${PHASES_DIR}" ]]; then
  # `find` + `sort` keeps lexicographic order across .sh and .py files.
  # We avoid `mapfile` because it varies between bash 3 (macOS default)
  # and bash 4+. Read newline-delimited paths into the array manually.
  while IFS= read -r line; do
    [[ -n "${line}" ]] && PHASE_FILES+=("${line}")
  done < <(find "${PHASES_DIR}" -mindepth 1 -maxdepth 1 -type f \
              \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | LC_ALL=C sort)
else
  echo "[INFO] phases directory does not exist yet: ${PHASES_DIR}"
  echo "       (this is OK during incremental development — nothing to run)"
  echo ""
fi

# --- Execute (or simulate) phases ---
EXECUTED=0
SKIPPED=0
TOTAL_START="$(date +%s)"

for phase_path in "${PHASE_FILES[@]:-}"; do
  [[ -z "${phase_path}" ]] && continue
  phase_name="$(basename "${phase_path}")"

  if [[ ! -f "${phase_path}" ]]; then
    echo "[SKIP] ${phase_name} (script not present)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[DRY-RUN] would execute: ${phase_name}"
    continue
  fi

  echo "----------------------------------------------------------------------"
  echo "[RUN] ${phase_name}"
  echo "----------------------------------------------------------------------"
  phase_start="$(date +%s)"

  case "${phase_name}" in
    *.sh)
      if ! bash "${phase_path}"; then
        rc=$?
        echo ""
        echo "ERROR: phase ${phase_name} failed (exit ${rc})." >&2
        exit 1
      fi
      ;;
    *.py)
      if ! python3 "${phase_path}"; then
        rc=$?
        echo ""
        echo "ERROR: phase ${phase_name} failed (exit ${rc})." >&2
        exit 1
      fi
      ;;
    *)
      echo "[SKIP] ${phase_name} (unsupported extension)"
      SKIPPED=$((SKIPPED + 1))
      continue
      ;;
  esac

  phase_end="$(date +%s)"
  phase_dur=$((phase_end - phase_start))
  echo "[DONE] ${phase_name} (${phase_dur}s)"
  echo ""
  EXECUTED=$((EXECUTED + 1))
done

# --- Summary ---
TOTAL_END="$(date +%s)"
TOTAL_DUR=$((TOTAL_END - TOTAL_START))

echo "======================================================================"
echo "Summary"
echo "======================================================================"
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "Mode             : DRY-RUN (nothing was executed)"
  echo "Phases listed    : ${#PHASE_FILES[@]}"
else
  echo "Phases executed  : ${EXECUTED}"
  echo "Phases skipped   : ${SKIPPED}"
  echo "Total wall time  : ${TOTAL_DUR}s"
fi
echo "RUN_TAG          : ${RUN_TAG}"
echo "Sandbox          : ${SANDBOX_DIR}"
if [[ "${KEEP_SANDBOX}" == "1" ]]; then
  echo "Sandbox retained (EDPA_E2E_KEEP_SANDBOX=1)."
fi
echo "======================================================================"
