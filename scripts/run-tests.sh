#!/usr/bin/env bash
# scripts/run-tests.sh — run the pytest suite against the KVM lab.
#
# Honours pytest args; defaults to the tests/ directory. The venv is preferred
# if present.

set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

DRY_RUN=0
PYTEST_ARGS=()

usage() {
  cat <<'EOF'
Usage: scripts/run-tests.sh [--dry-run] [pytest args...]

Run pytest with the KVM lab connection defaults used by this repository.

Options:
  --dry-run   Print the resolved environment and pytest command without running.
  -h, --help  Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      PYTEST_ARGS+=("$@")
      break
      ;;
    *)
      PYTEST_ARGS+=("$1")
      ;;
  esac
  shift
done

PYTEST=".venv/bin/pytest"
if [ ! -x "${PYTEST}" ]; then
  PYTEST="$(command -v pytest || true)"
fi
if [ -z "${PYTEST}" ]; then
  echo "error: pytest not found. Run ./scripts/bootstrap-venv.sh first." >&2
  exit 1
fi

# Connection defaults for the lab (override via env).
export ORACLE_TEST_HOST="${ORACLE_TEST_HOST:-superdb.domain.is}"
export ORACLE_TEST_PORT="${ORACLE_TEST_PORT:-1521}"
export ORACLE_TEST_SERVICE="${ORACLE_TEST_SERVICE:-super_svc}"
export ORACLE_TEST_SID="${ORACLE_TEST_SID:-super}"
export ORACLE_TEST_USER="${ORACLE_TEST_USER:-sys}"
export ORACLE_TEST_PASSWORD="${ORACLE_TEST_PASSWORD:-SysPassword1_}"
export ORACLE_TEST_SSH_HOST="${ORACLE_TEST_SSH_HOST:-192.168.87.11}"
export ORACLE_TEST_STANDBY_SSH_HOST="${ORACLE_TEST_STANDBY_SSH_HOST:-192.168.87.12}"
export ORACLE_TEST_OBSERVER_SSH_HOST="${ORACLE_TEST_OBSERVER_SSH_HOST:-192.168.87.13}"
export ORACLE_TEST_SSH_USER="${ORACLE_TEST_SSH_USER:-root}"
export ORACLE_TEST_SSH_KEY="${ORACLE_TEST_SSH_KEY:-$HOME/.ssh/lab_oracle}"
export ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}"
export ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}"

if [ "${#PYTEST_ARGS[@]}" -eq 0 ]; then
  PYTEST_ARGS=(tests/)
fi

echo "[test] Using ${PYTEST}"
echo "[test] Target: ${ORACLE_TEST_HOST}:${ORACLE_TEST_PORT} service=${ORACLE_TEST_SERVICE}"
echo "[test] SSH: primary=${ORACLE_TEST_SSH_HOST} standby=${ORACLE_TEST_STANDBY_SSH_HOST} observer=${ORACLE_TEST_OBSERVER_SSH_HOST}"
echo "[test] Ansible temp: ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP} ANSIBLE_SSH_CONTROL_PATH_DIR=${ANSIBLE_SSH_CONTROL_PATH_DIR} XDG_CACHE_HOME=${XDG_CACHE_HOME}"

if [ "${DRY_RUN}" -eq 1 ]; then
  printf '[test] Command:'
  printf ' %q' "${PYTEST}" "${PYTEST_ARGS[@]}" -v
  printf '\n'
  env | grep -E '^(ORACLE_TEST_|ANSIBLE_LOCAL_TEMP=|ANSIBLE_SSH_CONTROL_PATH_DIR=|XDG_CACHE_HOME=)' | sort
  exit 0
fi

exec "${PYTEST}" "${PYTEST_ARGS[@]}" -v
