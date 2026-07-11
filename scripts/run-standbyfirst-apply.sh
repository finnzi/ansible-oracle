#!/usr/bin/env bash
# scripts/run-standbyfirst-apply.sh
#
# Run the final Data Guard standby-first patch apply gate. This script is
# intentionally separate from check-remaining-gates.sh because it passes the
# destructive standby-first confirmation token when explicitly requested.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

INVENTORY="${INVENTORY:-inventory/hosts.yml}"
ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}"
ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-}"

DRY_RUN=0
EXECUTE=0
CONFIRM=""
RUN_PREFLIGHT=1
RUN_POSTCHECK=1
RESTORE_PRIMARY=1
STANDBYFIRST_ZIP="${STANDBYFIRST_ZIP:-/u01/stage/p39062931_190000_Linux-x86-64.zip}"
STANDBYFIRST_COMPONENT_PATH="${STANDBYFIRST_COMPONENT_PATH:-39062931/39034528}"
STANDBYFIRST_DUAL_HOME_SUFFIX="${STANDBYFIRST_DUAL_HOME_SUFFIX:-db_home2}"
STANDBYFIRST_EXPECTED_PRIMARY="${STANDBYFIRST_EXPECTED_PRIMARY:-super}"
STANDBYFIRST_EXPECTED_STANDBY="${STANDBYFIRST_EXPECTED_STANDBY:-super_sby}"

usage() {
  cat <<'EOF'
Usage: scripts/run-standbyfirst-apply.sh --execute --confirm PATCH_STANDBY_FIRST [options]

Run the final confirmed Data Guard standby-first patch apply. By default this
uses the staged 19.31 DB RU component that the media scanner reports as
standby-first eligible, targets db_home2, and restores the original primary
after both Data Guard homes are patched.

Options:
  --dry-run                  Print commands without running them.
  --execute                  Required before any apply command is run.
  --confirm TOKEN            Required exact token: PATCH_STANDBY_FIRST.
  --inventory PATH           Inventory path (default: inventory/hosts.yml).
  --standbyfirst-zip PATH    Patch zip to apply.
  --standbyfirst-component PATH
                             Relative eligible DB RU component path in the zip.
  --standbyfirst-dual-home-suffix SUFFIX
                             Target home suffix (default: db_home2).
  --expected-primary NAME    Required current primary before apply (default: super).
  --expected-standby NAME    Required current standby before apply (default: super_sby).
  --no-restore-primary       Do not switch back to the original primary.
  --skip-preflight           Do not run the safe remaining-gates preflight first.
  --skip-postcheck           Do not run the safe post-apply readiness check.
  -h, --help                 Show this help.

This script runs scripts/check-remaining-gates.sh --prove-confirmation-gate
first unless --skip-preflight is set. After the confirmed apply succeeds, it
runs a safe standby-first readiness check unless --skip-postcheck is set. The
underlying playbook still enforces
oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --execute)
      EXECUTE=1
      ;;
    --confirm)
      [ "$#" -ge 2 ] || { echo "error: --confirm requires a token" >&2; exit 1; }
      CONFIRM="$2"
      shift
      ;;
    --inventory)
      [ "$#" -ge 2 ] || { echo "error: --inventory requires a path" >&2; exit 1; }
      INVENTORY="$2"
      shift
      ;;
    --standbyfirst-zip)
      [ "$#" -ge 2 ] || { echo "error: --standbyfirst-zip requires a path" >&2; exit 1; }
      STANDBYFIRST_ZIP="$2"
      shift
      ;;
    --standbyfirst-component)
      [ "$#" -ge 2 ] || { echo "error: --standbyfirst-component requires a path" >&2; exit 1; }
      STANDBYFIRST_COMPONENT_PATH="$2"
      shift
      ;;
    --standbyfirst-dual-home-suffix)
      [ "$#" -ge 2 ] || { echo "error: --standbyfirst-dual-home-suffix requires a suffix" >&2; exit 1; }
      STANDBYFIRST_DUAL_HOME_SUFFIX="$2"
      shift
      ;;
    --expected-primary)
      [ "$#" -ge 2 ] || { echo "error: --expected-primary requires a name" >&2; exit 1; }
      STANDBYFIRST_EXPECTED_PRIMARY="$2"
      shift
      ;;
    --expected-standby)
      [ "$#" -ge 2 ] || { echo "error: --expected-standby requires a name" >&2; exit 1; }
      STANDBYFIRST_EXPECTED_STANDBY="$2"
      shift
      ;;
    --no-restore-primary)
      RESTORE_PRIMARY=0
      ;;
    --skip-preflight)
      RUN_PREFLIGHT=0
      ;;
    --skip-postcheck)
      RUN_POSTCHECK=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [ "${EXECUTE}" -ne 1 ]; then
  echo "error: confirmed standby-first apply requires --execute" >&2
  usage >&2
  exit 1
fi

if [ "${CONFIRM}" != "PATCH_STANDBY_FIRST" ]; then
  echo "error: confirmed standby-first apply requires --confirm PATCH_STANDBY_FIRST" >&2
  exit 1
fi

if [ -z "${ANSIBLE_PLAYBOOK}" ]; then
  if [ -x ".venv/bin/ansible-playbook" ]; then
    ANSIBLE_PLAYBOOK=".venv/bin/ansible-playbook"
  else
    ANSIBLE_PLAYBOOK="ansible-playbook"
  fi
fi

print_command() {
  local arg
  for arg in "$@"; do
    printf '%q ' "${arg}"
  done
  printf '\n'
}

run_command() {
  local label="$1"
  shift

  echo "[standbyfirst-apply] ${label}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    print_command "$@"
  else
    "$@"
  fi
}

if [ "${RUN_PREFLIGHT}" -eq 1 ]; then
  preflight_cmd=(
    scripts/check-remaining-gates.sh \
    --skip-fsfo \
    --standbyfirst-zip "${STANDBYFIRST_ZIP}" \
    --standbyfirst-component "${STANDBYFIRST_COMPONENT_PATH}" \
    --standbyfirst-dual-home-suffix "${STANDBYFIRST_DUAL_HOME_SUFFIX}" \
    --standbyfirst-expected-primary "${STANDBYFIRST_EXPECTED_PRIMARY}" \
    --standbyfirst-expected-standby "${STANDBYFIRST_EXPECTED_STANDBY}" \
    --prove-confirmation-gate \
    --inventory "${INVENTORY}"
  )
  if [ "${RESTORE_PRIMARY}" -eq 0 ]; then
    preflight_cmd+=(--no-standbyfirst-restore-primary)
  fi
  run_command \
    "safe preflight" \
    "${preflight_cmd[@]}"
fi

apply_cmd=(
  env
  "ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP}"
  "ANSIBLE_SSH_CONTROL_PATH_DIR=${ANSIBLE_SSH_CONTROL_PATH_DIR}"
  "XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  "${ANSIBLE_PLAYBOOK}"
  -i
  "${INVENTORY}"
  playbooks/07-patch-standbyfirst.yml
  -e
  "oracle_patch_zip=${STANDBYFIRST_ZIP}"
  -e
  "oracle_patch_apply_component_path=${STANDBYFIRST_COMPONENT_PATH}"
  -e
  "oracle_patch_dual_home_suffix=${STANDBYFIRST_DUAL_HOME_SUFFIX}"
  -e
  "oracle_patch_standbyfirst_expected_primary=${STANDBYFIRST_EXPECTED_PRIMARY}"
  -e
  "oracle_patch_standbyfirst_expected_standby=${STANDBYFIRST_EXPECTED_STANDBY}"
  -e
  oracle_patch_standbyfirst_execute=true
  -e
  "oracle_patch_standbyfirst_confirm=${CONFIRM}"
)

if [ "${RESTORE_PRIMARY}" -eq 1 ]; then
  apply_cmd+=(-e oracle_patch_standbyfirst_restore_primary=true)
fi

run_command "confirmed standby-first apply" "${apply_cmd[@]}"

if [ "${RUN_POSTCHECK}" -eq 1 ]; then
  postcheck_expected_primary="${STANDBYFIRST_EXPECTED_PRIMARY}"
  postcheck_expected_standby="${STANDBYFIRST_EXPECTED_STANDBY}"
  if [ "${RESTORE_PRIMARY}" -eq 0 ]; then
    postcheck_expected_primary="${STANDBYFIRST_EXPECTED_STANDBY}"
    postcheck_expected_standby="${STANDBYFIRST_EXPECTED_PRIMARY}"
  fi

  postcheck_cmd=(
    scripts/check-remaining-gates.sh \
    --skip-media \
    --skip-fsfo \
    --standbyfirst-zip "${STANDBYFIRST_ZIP}" \
    --standbyfirst-component "${STANDBYFIRST_COMPONENT_PATH}" \
    --standbyfirst-dual-home-suffix "${STANDBYFIRST_DUAL_HOME_SUFFIX}" \
    --standbyfirst-expected-primary "${postcheck_expected_primary}" \
    --standbyfirst-expected-standby "${postcheck_expected_standby}" \
    --inventory "${INVENTORY}"
  )
  run_command \
    "safe post-apply readiness" \
    "${postcheck_cmd[@]}"
fi
