#!/usr/bin/env bash
# scripts/check-remaining-gates.sh
#
# Run the non-destructive checks for the remaining standby-first apply gate and
# the proven FSFO readiness regression. This script never passes destructive
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
RUN_STANDBYFIRST_READINESS=1
RUN_FSFO=1
REQUIRE_ELIGIBLE_MEDIA=0
PROVE_CONFIRMATION_GATE=0
STANDBYFIRST_RESTORE_PRIMARY=1
STANDBYFIRST_ZIP="${STANDBYFIRST_ZIP:-/u01/stage/p39062931_190000_Linux-x86-64.zip}"
STANDBYFIRST_COMPONENT_PATH="${STANDBYFIRST_COMPONENT_PATH:-39062931/39034528}"
STANDBYFIRST_DUAL_HOME_SUFFIX="${STANDBYFIRST_DUAL_HOME_SUFFIX:-dbhome_2}"
STANDBYFIRST_EXPECTED_PRIMARY="${STANDBYFIRST_EXPECTED_PRIMARY:-super}"
STANDBYFIRST_EXPECTED_STANDBY="${STANDBYFIRST_EXPECTED_STANDBY:-super_sby}"

usage() {
  cat <<'EOF'
Usage: scripts/check-remaining-gates.sh [options]

Run only safe, non-destructive checks:
  1. Standby-first media scan for the remaining eligible-media gate.
  2. Standby-first selected-component readiness and execution-plan report.
  3. FSFO/readiness and primary-VM libvirt reachability regression.

Options:
  --dry-run                  Print commands without running them.
  --inventory PATH           Inventory path (default: inventory/hosts.yml).
  --require-eligible-media   Make the media scan fail unless eligible media exists.
  --standbyfirst-zip PATH    Patch zip for selected-component readiness.
  --standbyfirst-component PATH
                             Relative eligible DB RU component path in the zip.
  --standbyfirst-dual-home-suffix SUFFIX
                             Target home suffix for the optional confirmation-gate proof.
  --standbyfirst-expected-primary NAME
                             Require this current primary during readiness.
  --standbyfirst-expected-standby NAME
                             Require this current standby during readiness.
  --no-standbyfirst-expected-roles
                             Do not enforce expected primary/standby roles.
  --prove-confirmation-gate  Prove execute=true still refuses without the confirmation token.
  --no-standbyfirst-restore-primary
                             Omit restore-primary from the confirmation-gate proof.
  --skip-media               Do not run the standby-first media scan.
  --skip-standbyfirst        Do not run selected-component standby-first checks.
  --skip-fsfo                Do not run the FSFO readiness check.
  -h, --help                 Show this help.

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
    --standbyfirst-expected-primary)
      [ "$#" -ge 2 ] || { echo "error: --standbyfirst-expected-primary requires a name" >&2; exit 1; }
      STANDBYFIRST_EXPECTED_PRIMARY="$2"
      shift
      ;;
    --standbyfirst-expected-standby)
      [ "$#" -ge 2 ] || { echo "error: --standbyfirst-expected-standby requires a name" >&2; exit 1; }
      STANDBYFIRST_EXPECTED_STANDBY="$2"
      shift
      ;;
    --no-standbyfirst-expected-roles)
      STANDBYFIRST_EXPECTED_PRIMARY=""
      STANDBYFIRST_EXPECTED_STANDBY=""
      ;;
    --prove-confirmation-gate)
      PROVE_CONFIRMATION_GATE=1
      ;;
    --no-standbyfirst-restore-primary)
      STANDBYFIRST_RESTORE_PRIMARY=0
      ;;
    --skip-media)
      RUN_MEDIA=0
      ;;
    --skip-standbyfirst)
      RUN_STANDBYFIRST_READINESS=0
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

if [ "${RUN_MEDIA}" -eq 0 ] && [ "${RUN_STANDBYFIRST_READINESS}" -eq 0 ] && [ "${RUN_FSFO}" -eq 0 ]; then
  echo "error: all checks are disabled" >&2
  exit 1
fi

if [ "${PROVE_CONFIRMATION_GATE}" -eq 1 ] && [ "${RUN_STANDBYFIRST_READINESS}" -eq 0 ]; then
  echo "error: --prove-confirmation-gate requires standby-first checks; remove --skip-standbyfirst" >&2
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

run_expected_refusal() {
  local label="$1"
  shift
  local output_file
  local rc

  echo "[remaining-gates] ${label}"
  if [ "${DRY_RUN}" -eq 1 ]; then
    print_command "$@"
    return 0
  fi

  output_file="$(mktemp)"
  set +e
  "$@" >"${output_file}" 2>&1
  rc=$?
  set -e
  cat "${output_file}"
  if [ "${rc}" -eq 0 ]; then
    rm -f "${output_file}"
    echo "error: expected standby-first command to refuse without confirmation" >&2
    exit 1
  fi
  if ! grep -F "Standby-first patch execution installs/patches" "${output_file}" >/dev/null; then
    rm -f "${output_file}"
    echo "error: standby-first command failed, but not at the confirmation gate" >&2
    exit 1
  fi
  rm -f "${output_file}"
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

if [ "${RUN_STANDBYFIRST_READINESS}" -eq 1 ]; then
  # Component path peels an SF DB RU out of a combo zip — opt-in only.
  readiness_cmd=(
    "${base_cmd[@]}" \
    playbooks/07-patch-standbyfirst.yml \
    -e "oracle_patch_zip=${STANDBYFIRST_ZIP}" \
    -e "oracle_patch_apply_component_path=${STANDBYFIRST_COMPONENT_PATH}" \
    -e oracle_patch_standbyfirst_allow_component_only=true \
    -e "oracle_patch_dual_home_suffix=${STANDBYFIRST_DUAL_HOME_SUFFIX}"
  )
  if [ -n "${STANDBYFIRST_EXPECTED_PRIMARY}" ]; then
    readiness_cmd+=(-e "oracle_patch_standbyfirst_expected_primary=${STANDBYFIRST_EXPECTED_PRIMARY}")
  fi
  if [ -n "${STANDBYFIRST_EXPECTED_STANDBY}" ]; then
    readiness_cmd+=(-e "oracle_patch_standbyfirst_expected_standby=${STANDBYFIRST_EXPECTED_STANDBY}")
  fi
  run_command \
    "Standby-first selected-component readiness" \
    "${readiness_cmd[@]}"

  if [ "${PROVE_CONFIRMATION_GATE}" -eq 1 ]; then
    confirmation_cmd=(
      "${base_cmd[@]}" \
      playbooks/07-patch-standbyfirst.yml \
      -e "oracle_patch_zip=${STANDBYFIRST_ZIP}" \
      -e "oracle_patch_apply_component_path=${STANDBYFIRST_COMPONENT_PATH}" \
      -e oracle_patch_standbyfirst_allow_component_only=true \
      -e "oracle_patch_dual_home_suffix=${STANDBYFIRST_DUAL_HOME_SUFFIX}" \
      -e oracle_patch_standbyfirst_execute=true
    )
    if [ -n "${STANDBYFIRST_EXPECTED_PRIMARY}" ]; then
      confirmation_cmd+=(-e "oracle_patch_standbyfirst_expected_primary=${STANDBYFIRST_EXPECTED_PRIMARY}")
    fi
    if [ -n "${STANDBYFIRST_EXPECTED_STANDBY}" ]; then
      confirmation_cmd+=(-e "oracle_patch_standbyfirst_expected_standby=${STANDBYFIRST_EXPECTED_STANDBY}")
    fi
    if [ "${STANDBYFIRST_RESTORE_PRIMARY}" -eq 1 ]; then
      confirmation_cmd+=(-e oracle_patch_standbyfirst_restore_primary=true)
    fi
    run_expected_refusal \
      "Standby-first missing-confirmation refusal" \
      "${confirmation_cmd[@]}"
  fi
fi

if [ "${RUN_FSFO}" -eq 1 ]; then
  run_command \
    "FSFO readiness and libvirt primary-VM check" \
    "${base_cmd[@]}" \
    playbooks/08-failover-reinstate.yml
fi
