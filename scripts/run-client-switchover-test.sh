#!/usr/bin/env bash
# Prove OCI TAF SELECT continuity through a planned Data Guard switchover.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INVENTORY="${ORACLE_INVENTORY:-${REPO_DIR}/inventory/hosts.yml}"
SSH_KEY="${ORACLE_TEST_SSH_KEY:-${HOME}/.ssh/lab_oracle}"
CLIENT_HOST="${ORACLE_TEST_OBSERVER_SSH_HOST:-192.168.87.13}"
CLIENT_USER="${ORACLE_CLIENT_TEST_USER:-client_ha_test}"
CLIENT_PASSWORD="${ORACLE_CLIENT_TEST_PASSWORD:-ClientHaTest1_}"
SYS_PASSWORD="${ORACLE_TEST_PASSWORD:-SysPassword1_}"
EXECUTE=0
CONFIRM=""
RESTORE=1
ROWS="${ORACLE_CLIENT_TEST_ROWS:-5000}"

usage() {
  cat <<'EOF'
Usage: scripts/run-client-switchover-test.sh [options]

Safe by default: validates prerequisites and prints the destructive command.

Options:
  --execute                         Run the switchover continuity proof
  --confirm CLIENT_SWITCHOVER       Required with --execute
  --no-restore-primary              Leave the new primary in place
  -h, --help                        Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute) EXECUTE=1 ;;
    --confirm) shift; CONFIRM="${1:-}" ;;
    --no-restore-primary) RESTORE=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[ -f "$INVENTORY" ] || { echo "error: inventory not found: $INVENTORY" >&2; exit 1; }
[ -f "$SSH_KEY" ] || { echo "error: SSH key not found: $SSH_KEY" >&2; exit 1; }
command -v ssh >/dev/null || { echo "error: ssh is required" >&2; exit 1; }

SSH=(ssh -F /dev/null -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes "root@${CLIENT_HOST}")
remote_oracle() {
  "${SSH[@]}" "su - oracle -c $(printf '%q' "$1")"
}

echo "[client-ha] Reconciling role-based services and client aliases"
ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}" \
ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}" \
XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}" \
  "${REPO_DIR}/.venv/bin/ansible-playbook" -i "$INVENTORY" \
  "${REPO_DIR}/playbooks/08-client-availability.yml"

client_home=/observer/app/oracle/client_home1
client_env="export ORACLE_HOME=${client_home} TNS_ADMIN=${client_home}/network/admin"
primary="$(remote_oracle "$client_env; ${client_home}/bin/dgmgrl -silent dgmonitor/DgPassword1_@super_dgb <<'DGMGRL'
show configuration;
exit;
DGMGRL" | sed -n "s/^[[:space:]]*\([^[:space:]]*\)[[:space:]]*- Primary database/\1/p" | head -1)"

case "$primary" in
  super) target=super_sby ;;
  super_sby) target=super ;;
  *) echo "error: could not determine current broker primary" >&2; exit 1 ;;
esac
echo "[client-ha] Broker primary=${primary}; switchover target=${target}"

remote_oracle "$client_env; ${client_home}/bin/tnsping super_primary >/dev/null; ${client_home}/bin/tnsping super_standby >/dev/null"
if [ "$EXECUTE" -ne 1 ]; then
  echo "[client-ha] Preflight passed. Destructive proof requires:"
  echo "  scripts/run-client-switchover-test.sh --execute --confirm CLIENT_SWITCHOVER"
  exit 0
fi
[ "$CONFIRM" = CLIENT_SWITCHOVER ] || {
  echo "error: --execute requires --confirm CLIENT_SWITCHOVER" >&2
  exit 2
}

echo "[client-ha] Creating disposable continuity test account"
remote_oracle "$client_env; ${client_home}/bin/sqlplus -S 'sys/${SYS_PASSWORD}@super_primary as sysdba' <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
BEGIN
  EXECUTE IMMEDIATE 'DROP USER ${CLIENT_USER} CASCADE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -1918 THEN RAISE; END IF;
END;
/
CREATE USER ${CLIENT_USER} IDENTIFIED BY \"${CLIENT_PASSWORD}\";
GRANT CREATE SESSION TO ${CLIENT_USER};
EXIT;
SQL"

output="$(mktemp /tmp/oracle-client-ha.XXXXXX)"
finished=0
finish() {
  local current
  [ "$finished" -eq 0 ] || return 0
  finished=1
  set +e
  remote_oracle "$client_env; ${client_home}/bin/sqlplus -S 'sys/${SYS_PASSWORD}@super_primary as sysdba' <<SQL
BEGIN
  EXECUTE IMMEDIATE 'DROP USER ${CLIENT_USER} CASCADE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -1918 THEN RAISE; END IF;
END;
/
EXIT;
SQL" >/dev/null 2>&1
  if [ "$RESTORE" -eq 1 ]; then
    current="$(remote_oracle "$client_env; ${client_home}/bin/dgmgrl -silent dgmonitor/DgPassword1_@super_dgb <<'DGMGRL'
show configuration;
exit;
DGMGRL" 2>/dev/null | sed -n "s/^[[:space:]]*\([^[:space:]]*\)[[:space:]]*- Primary database/\1/p" | head -1)"
    if [ -n "$current" ] && [ "$current" != "$primary" ]; then
      echo "[client-ha] Restoring original primary ${primary}"
      for _ in $(seq 1 18); do
        restore_output="$(remote_oracle "$client_env; ${client_home}/bin/dgmgrl -silent dgmonitor/DgPassword1_@super_dgb <<DGMGRL
switchover to ${primary};
exit;
DGMGRL" 2>&1)"
        printf '%s\n' "$restore_output"
        printf '%s\n' "$restore_output" | grep -Fq 'Switchover succeeded' && break
        sleep 10
      done
    fi
  fi
  rm -f "$output"
}
trap finish EXIT INT TERM

echo "[client-ha] Starting ${ROWS}-row TAF SELECT from the client VM"
remote_oracle "$client_env; set -o pipefail; ${client_home}/bin/sqlplus -S '${CLIENT_USER}/${CLIENT_PASSWORD}@super_primary' <<'SQL' | while IFS= read -r line; do printf '%s\n' \"\$line\"; sleep 0.01; done
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET PAGES 0 FEEDBACK OFF HEADING OFF VERIFY OFF ECHO OFF ARRAYSIZE 1
SELECT 'CLIENT_HA_ROW|' || LPAD(level, 5, '0') || '|' || level
FROM dual CONNECT BY level <= ${ROWS};
SELECT 'CLIENT_HA_POST|' || SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') FROM dual;
EXIT;
SQL" >"$output" 2>&1 &
select_pid=$!

for _ in $(seq 1 30); do
  [ "$(grep -c '^CLIENT_HA_ROW|' "$output" 2>/dev/null || true)" -ge 5 ] && break
  sleep 1
done
[ "$(grep -c '^CLIENT_HA_ROW|' "$output" 2>/dev/null || true)" -ge 5 ] || {
  cat "$output" >&2
  echo "error: SELECT workload did not start" >&2
  exit 1
}

echo "[client-ha] Switching broker primary to ${target} during the open fetch"
remote_oracle "$client_env; ${client_home}/bin/dgmgrl -silent dgmonitor/DgPassword1_@super_dgb <<'DGMGRL'
switchover to ${target};
exit;
DGMGRL"

select_rc=0
wait "$select_pid" || select_rc=$?
if [ "$select_rc" -ne 0 ]; then
  cat "$output" >&2
  echo "error: SQL*Plus continuity workload exited with ${select_rc}" >&2
  exit 1
fi
if grep -Eq 'ORA-|SP2-' "$output"; then
  cat "$output" >&2
  echo "error: Oracle client reported an error during TAF SELECT" >&2
  exit 1
fi

row_count="$(grep -c '^CLIENT_HA_ROW|' "$output")"
sequence_count="$(sed -n 's/^CLIENT_HA_ROW|\([0-9][0-9]*\)|.*/\1/p' "$output" | sort -u | wc -l)"
post_primary="$(sed -n 's/^CLIENT_HA_POST|//p' "$output" | tail -1)"
[ "$row_count" -eq "$ROWS" ] || { cat "$output" >&2; echo "error: expected ${ROWS} rows, got ${row_count}" >&2; exit 1; }
[ "$sequence_count" -eq "$ROWS" ] || { cat "$output" >&2; echo "error: duplicate or missing fetch sequence" >&2; exit 1; }
[ "${post_primary,,}" = "${target,,}" ] || { cat "$output" >&2; echo "error: post-fetch session is on ${post_primary:-unknown}, expected ${target}" >&2; exit 1; }

echo "[client-ha] PASS: ${row_count} unique rows fetched without an Oracle error; the same client session continued on ${post_primary}"

finish
trap - EXIT INT TERM
echo "[client-ha] Client switchover proof complete"
