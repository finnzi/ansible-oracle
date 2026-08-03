#!/usr/bin/env bash
# scripts/run-dual-db-upgrade.sh
#
# Guarded standalone dual-home upgrade helper (prepare + optional cutover).
# Default is readiness/prepare-only. Destructive cutover requires:
#   --cutover --confirm CUTOVER_TO_UPGRADE_HOME

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

INVENTORY="${INVENTORY:-inventory/hosts.yml}"
ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}"
ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-}"

DRY_RUN=0
APPLY=0
FORCE_REBUILD=0
CUTOVER=0
CONFIRM=""
DUAL_HOME_SUFFIX="${DUAL_HOME_SUFFIX:-dbhome_2}"
UPGRADE_ZIP="${UPGRADE_ZIP:-/u01/stage/p39618649_190000_Linux-x86-64.zip}"
UPGRADE_COMPONENT_PATH="${UPGRADE_COMPONENT_PATH:-39618649/39472050}"

usage() {
  cat <<'EOF'
Usage: scripts/run-dual-db-upgrade.sh [options]

Standalone dual-home upgrade against the 19.32 DB RU combo by default.

Phases:
  readiness (default)  Plan/facts only (no detach/install/patch).
  --apply              Rebuild unused home path if needed (detach+remove when not
                       already at target RU), clean-install same folder, apply
                       upgrade RU, deploy network/admin; do not switch Restart.
  --force-rebuild      With --apply, always detach/remove unused home first.
  --cutover            Planned Restart switch + datapatch (requires --confirm).

Options:
  --dry-run            Print commands without running them.
  --apply              Rebuild/install/patch unused home (no Restart switch).
  --force-rebuild      Always rebuild unused path even if already at target RU.
  --cutover            Execute planned cutover after prepare.
  --confirm TOKEN      Required for cutover: CUTOVER_TO_UPGRADE_HOME.
  --inventory PATH     Inventory path (default: inventory/hosts.yml).
  --dual-home-suffix SUFFIX
                       Target home suffix (default: dbhome_2).
  --upgrade-zip PATH   Staged upgrade zip path inside guests.
  --upgrade-component PATH
                       Eligible DB RU component path (default: 39618649/39472050).
  -h, --help           Show this help.

Examples:
  # Readiness / version report only
  scripts/run-dual-db-upgrade.sh

  # Clean rebuild of dbhome_2 + 19.32 + net files (DB stays on current home)
  scripts/run-dual-db-upgrade.sh --apply

  # Force rebuild even if already at 19.32
  scripts/run-dual-db-upgrade.sh --apply --force-rebuild

  # Planned cutover window
  scripts/run-dual-db-upgrade.sh --cutover --confirm CUTOVER_TO_UPGRADE_HOME
EOF
}

resolve_playbook() {
  if [ -n "${ANSIBLE_PLAYBOOK}" ]; then
    printf '%s\n' "${ANSIBLE_PLAYBOOK}"
    return 0
  fi
  if [ -x "${REPO_DIR}/.venv/bin/ansible-playbook" ]; then
    printf '%s\n' "${REPO_DIR}/.venv/bin/ansible-playbook"
    return 0
  fi
  command -v ansible-playbook
}

run_cmd() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '+ %s\n' "$*"
    return 0
  fi
  "$@"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --apply) APPLY=1 ;;
    --force-rebuild) FORCE_REBUILD=1 ;;
    --cutover) CUTOVER=1 ;;
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
    --dual-home-suffix)
      [ "$#" -ge 2 ] || { echo "error: --dual-home-suffix requires a suffix" >&2; exit 1; }
      DUAL_HOME_SUFFIX="$2"
      shift
      ;;
    --upgrade-zip)
      [ "$#" -ge 2 ] || { echo "error: --upgrade-zip requires a path" >&2; exit 1; }
      UPGRADE_ZIP="$2"
      shift
      ;;
    --upgrade-component)
      [ "$#" -ge 2 ] || { echo "error: --upgrade-component requires a path" >&2; exit 1; }
      UPGRADE_COMPONENT_PATH="$2"
      shift
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

if [ "${CUTOVER}" -eq 1 ] && [ "${CONFIRM}" != "CUTOVER_TO_UPGRADE_HOME" ]; then
  echo "error: cutover requires --confirm CUTOVER_TO_UPGRADE_HOME" >&2
  exit 1
fi

PLAYBOOK="$(resolve_playbook)"
export ANSIBLE_LOCAL_TEMP ANSIBLE_SSH_CONTROL_PATH_DIR XDG_CACHE_HOME

echo "[upgrade] prepare dual-home target suffix=${DUAL_HOME_SUFFIX} apply=${APPLY}"
prepare_args=(
  env "ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP}"
  "ANSIBLE_SSH_CONTROL_PATH_DIR=${ANSIBLE_SSH_CONTROL_PATH_DIR}"
  "XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  "${PLAYBOOK}" -i "${INVENTORY}"
  playbooks/07-upgrade-dual-db-prepare.yml
  -e "oracle_patch_dual_home_suffix=${DUAL_HOME_SUFFIX}"
  -e "oracle_patch_db_zip=${UPGRADE_ZIP}"
  -e "oracle_patch_zip=${UPGRADE_ZIP}"
  -e "oracle_patch_apply_component_path=${UPGRADE_COMPONENT_PATH}"
)
if [ "${APPLY}" -eq 1 ]; then
  prepare_args+=(-e oracle_patch_apply_enabled=true)
fi
if [ "${FORCE_REBUILD}" -eq 1 ]; then
  prepare_args+=(-e oracle_upgrade_prepare_force_rebuild=true)
fi
run_cmd "${prepare_args[@]}"

if [ "${CUTOVER}" -eq 1 ]; then
  echo "[upgrade] planned cutover to ${DUAL_HOME_SUFFIX}"
  run_cmd env \
    "ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP}" \
    "ANSIBLE_SSH_CONTROL_PATH_DIR=${ANSIBLE_SSH_CONTROL_PATH_DIR}" \
    "XDG_CACHE_HOME=${XDG_CACHE_HOME}" \
    "${PLAYBOOK}" -i "${INVENTORY}" \
    playbooks/07-upgrade-dual-db-cutover.yml \
    -e "oracle_patch_dual_home_suffix=${DUAL_HOME_SUFFIX}" \
    -e "oracle_patch_db_zip=${UPGRADE_ZIP}" \
    -e "oracle_patch_zip=${UPGRADE_ZIP}" \
    -e "oracle_patch_apply_component_path=${UPGRADE_COMPONENT_PATH}" \
    -e oracle_upgrade_cutover_execute=true \
    -e "oracle_upgrade_cutover_confirm=${CONFIRM}"
fi

echo "[upgrade] done"
