#!/usr/bin/env bash
# scripts/run-tests.sh — run the pytest suite against the KVM lab.
#
# Honours pytest args; defaults to the tests/ directory. The venv is preferred
# if present.

set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

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
export ORACLE_TEST_SSH_USER="${ORACLE_TEST_SSH_USER:-root}"
export ORACLE_TEST_SSH_KEY="${ORACLE_TEST_SSH_KEY:-$HOME/.ssh/lab_oracle}"

echo "[test] Using ${PYTEST}"
echo "[test] Target: ${ORACLE_TEST_HOST}:${ORACLE_TEST_PORT} service=${ORACLE_TEST_SERVICE}"
exec "${PYTEST}" "${@:-tests/}" -v
