#!/usr/bin/env bash
# PROTOTYPE: prove TAC replay and FAN/FCF through a Data Guard switchover.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INVENTORY="${ORACLE_INVENTORY:-${REPO_DIR}/inventory/hosts.yml}"
SSH_KEY="${ORACLE_TEST_SSH_KEY:-${HOME}/.ssh/lab_oracle}"
CLIENT_HOST="${ORACLE_TEST_OBSERVER_SSH_HOST:-192.168.87.13}"
APP_USER="${ORACLE_TAC_TEST_USER:-tac_fcf_test}"
APP_PASSWORD="${ORACLE_TAC_TEST_PASSWORD:-TacFcfTest1_}"
SYS_PASSWORD="${ORACLE_TEST_PASSWORD:-SysPassword1_}"
DG_PASSWORD="${ORACLE_DG_PASSWORD:-DgPassword1_}"
ONS_NODES="${ORACLE_ONS_NODES:-superdb1.domain.is:6200,superdb2.domain.is:6200}"
EXECUTE=0
CONFIRM=""
RESTORE=1

usage() {
  cat <<'EOF'
Usage: scripts/run-tac-fcf-poc.sh [options]

Safe by default: reconciles the PoC and validates connectivity without switching roles.

Options:
  --execute                         Run the TAC/FAN/FCF switchover proof
  --confirm TAC_FCF_SWITCHOVER      Required with --execute
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
SSH=(ssh -F /dev/null -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes "root@${CLIENT_HOST}")
remote_oracle() { "${SSH[@]}" "su - oracle -c $(printf '%q' "$1")"; }

echo "[tac-fcf] Reconciling TAC service, ONS, client aliases, and PoC client"
ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-local}" \
ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-/tmp/ansible-cp}" \
XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-cache}" \
  "${REPO_DIR}/.venv/bin/ansible-playbook" -i "$INVENTORY" \
  "${REPO_DIR}/playbooks/08-client-availability.yml"

client_home=/observer/app/oracle/client_home1
client_env="export ORACLE_HOME=${client_home} TNS_ADMIN=${client_home}/network/admin"
broker() { remote_oracle "$client_env; ${client_home}/bin/dgmgrl -silent dgmonitor/${DG_PASSWORD}@super_dgb <<'DGMGRL'
$1
exit;
DGMGRL"; }
current_primary() {
  broker 'show configuration;' | sed -n "s/^[[:space:]]*\([^[:space:]]*\)[[:space:]]*- Primary database/\1/p" | head -1
}

primary="$(current_primary)"
case "$primary" in
  super) target=super_sby ;;
  super_sby) target=super ;;
  *) echo "error: could not determine current broker primary" >&2; exit 1 ;;
esac
remote_oracle "$client_env; ${client_home}/bin/tnsping super_tac >/dev/null"
echo "[tac-fcf] Preflight passed; primary=${primary}, target=${target}"
if [ "$EXECUTE" -ne 1 ]; then
  echo "[tac-fcf] Destructive proof requires:"
  echo "  scripts/run-tac-fcf-poc.sh --execute --confirm TAC_FCF_SWITCHOVER"
  exit 0
fi
[ "$CONFIRM" = TAC_FCF_SWITCHOVER ] || {
  echo "error: --execute requires --confirm TAC_FCF_SWITCHOVER" >&2
  exit 2
}

token="tac-$(date +%s)-$$"
output="$(mktemp /tmp/oracle-tac-fcf.XXXXXX)"
finished=0
finish() {
  local current restore_output
  [ "$finished" -eq 0 ] || return 0
  finished=1
  set +e
  if [ "$RESTORE" -eq 1 ]; then
    current="$(current_primary 2>/dev/null)"
    if [ -n "$current" ] && [ "$current" != "$primary" ]; then
      echo "[tac-fcf] Restoring original primary ${primary}"
      for _ in $(seq 1 18); do
        restore_output="$(broker "switchover to ${primary};" 2>&1)"
        printf '%s\n' "$restore_output"
        printf '%s\n' "$restore_output" | grep -Fq 'Switchover succeeded' && break
        sleep 10
      done
    fi
  fi
  remote_oracle "$client_env; ${client_home}/bin/sqlplus -S 'sys/${SYS_PASSWORD}@super_tac as sysdba' <<SQL
WHENEVER SQLERROR CONTINUE
DROP USER ${APP_USER} CASCADE;
EXIT;
SQL" >/dev/null 2>&1
  rm -f "$output"
}
trap finish EXIT INT TERM

echo "[tac-fcf] Creating disposable replay workload"
remote_oracle "$client_env; ${client_home}/bin/sqlplus -S 'sys/${SYS_PASSWORD}@super_tac as sysdba' <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
BEGIN
  EXECUTE IMMEDIATE 'DROP USER ${APP_USER} CASCADE';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1918 THEN RAISE; END IF;
END;
/
CREATE USER ${APP_USER} IDENTIFIED BY \"${APP_PASSWORD}\";
GRANT CREATE SESSION, CREATE TABLE, CREATE PROCEDURE TO ${APP_USER};
ALTER USER ${APP_USER} QUOTA UNLIMITED ON USERS;
CREATE TABLE ${APP_USER}.results (
  token VARCHAR2(128) PRIMARY KEY,
  database_name VARCHAR2(128) NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE OR REPLACE PROCEDURE ${APP_USER}.do_work(p_token VARCHAR2) AS
BEGIN
  DBMS_SESSION.SLEEP(90);
  INSERT INTO results VALUES (
    p_token, SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME'), SYSTIMESTAMP
  );
  COMMIT;
END;
/
ALTER SYSTEM ARCHIVE LOG CURRENT;
EXIT;
SQL"

cp="$client_home/jdbc/lib/ojdbc8.jar:$client_home/ucp/lib/ucp.jar:$client_home/jdbc/lib/simplefan.jar:$client_home/opmn/lib/ons.jar:/observer/app/oracle/tac-fcf-poc"
java_cmd="$client_env; ${client_home}/jdk/bin/java -Doracle.net.tns_admin=${client_home}/network/admin -cp ${cp} TacFcfPoc jdbc:oracle:thin:@super_tac ${APP_USER} ${APP_PASSWORD} super_tac ${ONS_NODES} ${token}"
echo "[tac-fcf] Starting replayable call on ${primary}"
remote_oracle "$java_cmd" >"$output" 2>&1 &
java_pid=$!
for _ in $(seq 1 45); do
  grep -Fq 'TAC_CALL_BEGIN|' "$output" 2>/dev/null && break
  kill -0 "$java_pid" 2>/dev/null || break
  sleep 1
done
grep -Fq 'TAC_CALL_BEGIN|' "$output" || { cat "$output" >&2; echo "error: PoC client did not start" >&2; exit 1; }

echo "[tac-fcf] Switching broker primary to ${target} during the call"
switch_output="$(broker "switchover to ${target};")"
printf '%s\n' "$switch_output"
printf '%s\n' "$switch_output" | grep -Fq 'Switchover succeeded' || { cat "$output" >&2; exit 1; }

java_rc=0
wait "$java_pid" || java_rc=$?
cat "$output"
[ "$java_rc" -eq 0 ] || { echo "error: PoC client exited with ${java_rc}" >&2; exit 1; }
grep -Fq "FAN_DOWN|super_tac|${primary}|" "$output" || { echo "error: no matching FAN service-down event" >&2; exit 1; }
grep -Fq "TAC_CALL_OK|db=${target}|count=1|" "$output" || { echo "error: TAC call was not replayed exactly once on ${target}" >&2; exit 1; }
grep -Fq "FCF_BORROW_OK|db=${target}|" "$output" || { echo "error: UCP did not borrow from ${target}" >&2; exit 1; }
grep -Fq 'POC_RESULT|fan_down=true|fcf=true' "$output" || { echo "error: FAN/FCF result incomplete" >&2; exit 1; }

echo "[tac-fcf] PASS: FAN arrived, TAC replayed the in-flight call once, and UCP borrowed on ${target}"
finish
trap - EXIT INT TERM
