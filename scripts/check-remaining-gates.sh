#!/usr/bin/env bash
# scripts/check-remaining-gates.sh
#
# Run the non-destructive checks for the remaining eligible-media gate and the
# proven FSFO readiness regression. This script never passes destructive
# execution confirmation variables.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

INVENTORY="${INVENTORY:-inventory/hosts.yml}"
ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}"
ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-}"

DRY_RUN=0
RUN_MEDIA=1
RUN_FSFO=1
REQUIRE_ELIGIBLE_MEDIA=0

usage() {
  cat <<'EOF'
Usage: scripts/check-remaining-gates.sh [options]

Run only safe, non-destructive checks:
  1. Standby-first media scan for the remaining eligible-media gate.
  2. FSFO/readiness and primary-VM libvirt reachability regression.

Options:
  --dry-run                 Print commands without running them.
  --inventory PATH          Inventory path (default: inventory/hosts.yml).
  --require-eligible-media  Make the media scan fail unless an eligible zip exists.
  --skip-media              Do not run the standby-first media scan.
  --skip-fsfo               Do not run the FSFO readiness check.
  -h, --help                Show this help.

This script intentionally does not set any destructive execution confirmation
variables. Use REMAINING_GATES.md for the final confirmed commands.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --inventory)
      [ "$#" -ge 2 ] || { echo "error: --inventory requires a path" >&2; exit 1; }
      INVENTORY="$2"
      shift
      ;;
    --require-eligible-media)
      REQUIRE_ELIGIBLE_MEDIA=1
      ;;
    --skip-media)
      RUN_MEDIA=0
      ;;
    --skip-fsfo)
      RUN_FSFO=0
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

if [ "${RUN_MEDIA}" -eq 0 ] && [ "${RUN_FSFO}" -eq 0 ]; then
  echo "error: both checks are disabled" >&2
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

  echo "[remaining-gates] ${label}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    print_command "$@"
  else
    "$@"
  fi
}

base_cmd=(
  env
  "ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP}"
  "ANSIBLE_SSH_CONTROL_PATH_DIR=${ANSIBLE_SSH_CONTROL_PATH_DIR}"
  "XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  "${ANSIBLE_PLAYBOOK}"
  -i
  "${INVENTORY}"
)

if [ "${RUN_MEDIA}" -eq 1 ]; then
  media_cmd=(
    "${base_cmd[@]}"
    playbooks/07-patch-standbyfirst-media.yml
  )
  if [ "${REQUIRE_ELIGIBLE_MEDIA}" -eq 1 ]; then
    media_cmd+=(-e oracle_patch_standbyfirst_media_require_eligible=true)
  fi
  run_command "Standby-first media scan" "${media_cmd[@]}"
fi

if [ "${RUN_FSFO}" -eq 1 ]; then
  run_command \
    "FSFO readiness and libvirt primary-VM check" \
    "${base_cmd[@]}" \
    playbooks/08-failover-reinstate.yml
fi
