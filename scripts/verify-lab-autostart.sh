#!/usr/bin/env bash
# Read-only proof that the completed lab converges from a guest boot without
# Ansible or manual Oracle start commands.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../lab/scripts/lib/common.sh
source "${REPO_DIR}/lab/scripts/lib/common.sh"

VERIFY_TIMEOUT_SECONDS="${VERIFY_TIMEOUT_SECONDS:-600}"
VERIFY_POLL_SECONDS="${VERIFY_POLL_SECONDS:-10}"
VERIFY_COMMAND_TIMEOUT_SECONDS="${VERIFY_COMMAND_TIMEOUT_SECONDS:-30}"
GI_HOME="${GI_HOME:-/grid/19c/gi_home1}"

lab_is_positive_integer "${VERIFY_TIMEOUT_SECONDS}" ||
  die "VERIFY_TIMEOUT_SECONDS must be a positive integer"
lab_is_positive_integer "${VERIFY_POLL_SECONDS}" ||
  die "VERIFY_POLL_SECONDS must be a positive integer"
lab_is_positive_integer "${VERIFY_COMMAND_TIMEOUT_SECONDS}" ||
  die "VERIFY_COMMAND_TIMEOUT_SECONDS must be a positive integer"
[[ "${GI_HOME}" =~ ^/[A-Za-z0-9._+/-]+$ ]] ||
  die "GI_HOME must be an absolute path containing only safe path characters"

# Discover the registered Oracle home through the GI srvctl view, then use
# that home for SQL and DB srvctl checks. The verifier never assumes a fixed home.
sql_state() {
  local host_ip="$1" oracle_home="$2" oracle_sid="$3"
  local home_q sid_q sqlplus_q
  printf -v home_q '%q' "${oracle_home}"
  printf -v sid_q '%q' "${oracle_sid}"
  sqlplus_q="${home_q}/bin/sqlplus"
  printf '%s\n' \
    'SET PAGES 0 FEEDBACK OFF VERIFY OFF HEADING OFF' \
    "SELECT database_role || '|' || open_mode FROM v\$database;" \
    'EXIT;' |
    ssh_lab "${host_ip}" \
      "timeout ${VERIFY_COMMAND_TIMEOUT_SECONDS} runuser -u oracle -- env ORACLE_HOME=${home_q} ORACLE_SID=${sid_q} ${sqlplus_q} -S / as sysdba" \
      2>&1
}

remote_state() {
  local host_ip="$1" command="$2"
  ssh_lab "${host_ip}" \
    "timeout ${VERIFY_COMMAND_TIMEOUT_SECONDS} bash -lc $(printf '%q' "${command}")" \
    2>&1
}

append_check() {
  local label="$1" output="$2" expected="$3"
  LAST_REPORT+=$'\n'
  LAST_REPORT+="--- ${label} (expected: ${expected}) ---"
  LAST_REPORT+=$'\n'
  LAST_REPORT+="${output}"
}

output_has() {
  local output="$1" expected="$2"
  grep -Fq -- "${expected}" <<<"${output}"
}

output_has_ci() {
  local output="$1" expected="$2"
  grep -Fiq -- "${expected}" <<<"${output}"
}

output_has_count_ci() {
  local output="$1" expected="$2" minimum="$3" count
  count="$(grep -Fic -- "${expected}" <<<"${output}" || true)"
  [ "${count}" -ge "${minimum}" ]
}

config_field() {
  local config="$1" field="$2"
  # srvctl emits fields such as `Oracle home:` and `Instance name:`.
  awk -F':[[:space:]]*' -v wanted="${field}" \
    'tolower($1) == tolower(wanted) { print $2; exit }' <<<"${config}"
}

resource_field() {
  local profile="$1" field="$2"
  awk -F= -v wanted="${field}" '
    $1 == wanted || $1 == "GEN_" wanted ||
    (wanted == "ORACLE_HOME" && $1 == "USR_ORA_ORACLE_HOME") ||
    (wanted == "USR_ORA_INST_NAME" && $1 == "GEN_USR_ORA_INST_NAME") {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      print $2
      exit
    }
  ' <<<"${profile}"
}

valid_oracle_home() {
  [[ "$1" =~ ^/[A-Za-z0-9._+/-]+$ ]]
}

valid_instance_name() {
  [[ "$1" =~ ^[A-Za-z0-9_$#]+$ ]]
}

database_resource_profile() {
  local host_ip="$1" db_unique="$2"
  remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/crsctl status resource ora.${db_unique}.db -p" \
    || true
}

database_config() {
  local host_ip="$1" db_unique="$2" oracle_home="$3"
  remote_state "${host_ip}" \
    "runuser -u oracle -- env ORACLE_HOME=${oracle_home} ${oracle_home}/bin/srvctl config database -db ${db_unique} -all" \
    || true
}

extract_database_state() {
  local output="$1"
  awk '
    /^[[:space:]]*PRIMARY\|READ WRITE[[:space:]]*$/ {
      print "PRIMARY|READ WRITE"; exit
    }
    /^[[:space:]]*PHYSICAL STANDBY\|READ ONLY WITH APPLY[[:space:]]*$/ {
      print "PHYSICAL STANDBY|READ ONLY WITH APPLY"; exit
    }
    /^[[:space:]]*PHYSICAL STANDBY\|READ ONLY[[:space:]]*$/ {
      print "PHYSICAL STANDBY|READ ONLY"; exit
    }
    /^[[:space:]]*PHYSICAL STANDBY\|MOUNTED[[:space:]]*$/ {
      print "PHYSICAL STANDBY|MOUNTED"; exit
    }
  ' <<<"${output}"
}

# Indexed arrays describe only registered DG database resources discovered on
# the two database hosts. They are reset on every poll.
DG_HOST_LABELS=()
DG_HOST_IPS=()
DG_UNIQUES=()
DG_HOMES=()
DG_SIDS=()
DG_STATES=()

discover_dg_members() {
  local host_label host_ip db_unique profile home sid state
  for host_label in superdb1 superdb2; do
    host_ip="$(vm_ip "${host_label}")"
    for db_unique in super super_sby; do
      profile="$(database_resource_profile "${host_ip}" "${db_unique}")"
      home="$(resource_field "${profile}" ORACLE_HOME | tr -d '\r')"
      sid="$(resource_field "${profile}" USR_ORA_INST_NAME | tr -d '\r')"
      if ! valid_oracle_home "${home}" || ! valid_instance_name "${sid}"; then
        continue
      fi

      state="$(extract_database_state "$(sql_state "${host_ip}" "${home}" "${sid}" || true)")"
      DG_HOST_LABELS+=("${host_label}")
      DG_HOST_IPS+=("${host_ip}")
      DG_UNIQUES+=("${db_unique}")
      DG_HOMES+=("${home}")
      DG_SIDS+=("${sid}")
      DG_STATES+=("${state:-UNKNOWN}")
    done
  done
}

check_database_resource() {
  local host_ip="$1" db_unique="$2" role="$3" start_option="$4"
  local profile status
  profile="$(remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/crsctl status resource ora.${db_unique}.db -p" || true)"
  append_check "${db_unique} Restart resource profile" "${profile}" \
    "enabled, AUTOMATIC, ROLE=${role}, open=${start_option}"
  output_has "${profile}" "ENABLED=1" || ready=1
  output_has "${profile}" "MANAGEMENT_POLICY=AUTOMATIC" || ready=1
  output_has "${profile}" "ROLE=${role}" || ready=1
  output_has_ci "${profile}" "USR_ORA_OPEN_MODE=${start_option}" || ready=1

  status="$(remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/crsctl status resource ora.${db_unique}.db -t" || true)"
  append_check "${db_unique} Restart resource status" "${status}" "ONLINE  ONLINE"
  if ! output_has_count_ci "${status}" "ONLINE  ONLINE" 1 &&
     ! output_has_count_ci "${status}" "ONLINE ONLINE" 1; then
    ready=1
  fi
}

check_database_config() {
  local host_ip="$1" oracle_home="$2" db_unique_name="$3" role="$4" start_option="$5" config
  config="$(remote_state "${host_ip}" \
    "runuser -u oracle -- env ORACLE_HOME=${oracle_home} ${oracle_home}/bin/srvctl config database -db ${db_unique_name} -all" || true)"
  append_check "${db_unique_name} Restart configuration" "${config}" \
    "enabled, AUTOMATIC, role=${role}, start=${start_option}, home=${oracle_home}"
  output_has_ci "${config}" "Database is enabled" || ready=1
  output_has_ci "${config}" "Management policy: AUTOMATIC" || ready=1
  output_has_ci "${config}" "Database role: ${role}" || ready=1
  output_has_ci "${config}" "Start options: ${start_option}" || ready=1
  output_has_ci "${config}" "Stop options: immediate" || ready=1
  check_database_resource "${host_ip}" "${db_unique_name}" "${role}" "${start_option}"
}

check_listener_config() {
  local host_ip="$1" listener="$2" oracle_home="$3" port="$4" listener_ip="$5" config sockets
  config="$(remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/srvctl config listener -listener ${listener}" || true)"
  append_check "${listener} Restart configuration" "${config}" \
    "enabled, home=${oracle_home}, IPC-only Restart endpoint; TCP:${listener_ip}:${port} in listener.ora"
  output_has_ci "${config}" "Listener is enabled" || ready=1
  output_has_ci "${config}" "Home: ${oracle_home}" || ready=1
  output_has_ci "${config}" "End points: /IPC:${listener}" || ready=1
  sockets="$(remote_state "${host_ip}" "ss -H -ltn sport = :${port} | awk '{print \$4}'" || true)"
  append_check "${listener} TCP sockets" "${sockets}" "exactly ${listener_ip}:${port}"
  [ "$(grep -Fc -- "${listener_ip}:${port}" <<<"${sockets}" || true)" -eq 1 ] || ready=1
  if grep -Evx -- "${listener_ip}:${port}" <<<"${sockets}" | grep -q '[^[:space:]]'; then
    ready=1
  fi
}

check_service_configs() {
  local host_ip="$1" oracle_home="$2" db_unique_name="$3" minimum="$4" config
  config="$(remote_state "${host_ip}" \
    "runuser -u oracle -- env ORACLE_HOME=${oracle_home} ${oracle_home}/bin/srvctl config service -db ${db_unique_name}" || true)"
  append_check "${db_unique_name} service configuration" "${config}" \
    "${minimum} enabled AUTOMATIC service(s)"
  output_has_count_ci "${config}" "Management policy: AUTOMATIC" "${minimum}" || ready=1
  output_has_count_ci "${config}" "Service is enabled" "${minimum}" || ready=1
}

check_service_resource() {
  local host_ip="$1" db_unique="$2" service="$3" role="$4"
  local profile status resource="ora.${db_unique}.${service}.svc"
  # Oracle 19c srvctl may report a NullPointerException for SIHA services;
  # CRSCTL is used here only for read-only status/profile inspection.
  profile="$(remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/crsctl status resource ${resource} -p" || true)"
  append_check "${resource} profile" "${profile}" \
    "enabled, AUTOMATIC, ROLE=${role}"
  output_has "${profile}" "NAME=${resource}" || ready=1
  output_has "${profile}" "ENABLED=1" || ready=1
  output_has "${profile}" "MANAGEMENT_POLICY=AUTOMATIC" || ready=1
  output_has "${profile}" "ROLE=${role}" || ready=1

  status="$(remote_state "${host_ip}" \
    "runuser -u oracle -- ${GI_HOME}/bin/crsctl status resource ${resource} -t" || true)"
  append_check "${resource} status" "${status}" "ONLINE  ONLINE"
  if ! output_has_count_ci "${status}" "ONLINE  ONLINE" 1 &&
     ! output_has_count_ci "${status}" "ONLINE ONLINE" 1; then
    ready=1
  fi
}

check_database_host_core() {
  local label="$1" host_ip="$2" require_standalone_aliases="$3" core
  core="$(remote_state "${host_ip}" "
    getent hosts superdc1.domain.is superdc2.domain.is duperdb.domain.is fluffdb.domain.is
    ${GI_HOME}/bin/crsctl check has
    ${GI_HOME}/bin/crsctl check css
    ${GI_HOME}/bin/crsctl config has
    runuser -u oracle -- ${GI_HOME}/bin/srvctl status asm
    runuser -u oracle -- ${GI_HOME}/bin/srvctl status diskgroup -diskgroup RESTART
    runuser -u oracle -- ${GI_HOME}/bin/srvctl status ons
    runuser -u oracle -- ${GI_HOME}/bin/srvctl status listener -listener LISTENER_SUPER
  " || true)"
  append_check "${label} core" "${core}" "VIPs, HAS/CSS, ASM/RESTART, ONS, and LISTENER_SUPER running"
  output_has "${core}" "192.168.87.31" || ready=1
  output_has "${core}" "192.168.87.32" || ready=1
  output_has "${core}" "CRS-4638" || ready=1
  output_has "${core}" "CRS-4529" || ready=1
  output_has_ci "${core}" "autostart is enabled" || ready=1
  output_has_ci "${core}" "ASM is running" || ready=1
  output_has_ci "${core}" "Disk Group RESTART is running" || ready=1
  output_has "${core}" "ONS daemon is running" || ready=1
  output_has "${core}" "Listener LISTENER_SUPER is running" || ready=1
  if [ "${require_standalone_aliases}" = true ]; then
    output_has "${core}" "192.168.87.22" || ready=1
    output_has "${core}" "192.168.87.23" || ready=1
  fi
}

check_standalone_database() {
  local db_unique="$1" listener="$2" port="$3" service="$4"
  local profile home sid state
  profile="$(database_resource_profile "${IP_SUPERDB1}" "${db_unique}")"
  home="$(resource_field "${profile}" ORACLE_HOME | tr -d '\r')"
  sid="$(resource_field "${profile}" USR_ORA_INST_NAME | tr -d '\r')"
  if ! valid_oracle_home "${home}" || ! valid_instance_name "${sid}"; then
    append_check "${db_unique} registration" "${profile}" "registered Oracle home and instance"
    ready=1
    return
  fi
  state="$(extract_database_state "$(sql_state "${IP_SUPERDB1}" "${home}" "${sid}" || true)")"
  append_check "${db_unique} database" "${state}" "PRIMARY|READ WRITE"
  output_has "${state}" "PRIMARY|READ WRITE" || ready=1
  check_database_config "${IP_SUPERDB1}" "${home}" "${db_unique}" PRIMARY open
  local listener_ip
  case "${db_unique}" in
    duper) listener_ip=192.168.87.22 ;;
    fluff) listener_ip=192.168.87.23 ;;
    *) listener_ip=192.168.87.21 ;;
  esac
  check_listener_config "${IP_SUPERDB1}" "${listener}" "${home}" "${port}" "${listener_ip}"
  check_service_configs "${IP_SUPERDB1}" "${home}" "${db_unique}" 1
  check_service_resource "${IP_SUPERDB1}" "${db_unique}" "${service}" PRIMARY
}

check_lab_autostart() {
  local observer_state
  local ready=0
  local PRIMARY_INDEX=-1 STANDBY_INDEX=-1
  local i db_unique host_ip home role start_option

  LAST_REPORT=""
  DG_HOST_LABELS=()
  DG_HOST_IPS=()
  DG_UNIQUES=()
  DG_HOMES=()
  DG_SIDS=()
  DG_STATES=()

  check_database_host_core superdb1 "${IP_SUPERDB1}" true
  check_database_host_core superdb2 "${IP_SUPERDB2}" false

  discover_dg_members
  append_check "Data Guard topology" \
    "$(for i in "${!DG_UNIQUES[@]}"; do
        printf '%s host=%s home=%s sid=%s state=%s\n' \
          "${DG_UNIQUES[${i}]}" "${DG_HOST_LABELS[${i}]}" \
          "${DG_HOMES[${i}]}" "${DG_SIDS[${i}]}" "${DG_STATES[${i}]}"
      done)" \
    "Exactly one PRIMARY|READ WRITE and one PHYSICAL STANDBY|READ ONLY WITH APPLY"

  if [ "${#DG_UNIQUES[@]}" -ne 2 ]; then
    ready=1
  fi
  for i in "${!DG_UNIQUES[@]}"; do
    case "${DG_STATES[${i}]}" in
      "PRIMARY|READ WRITE")
        if [ "${PRIMARY_INDEX}" -ge 0 ]; then ready=1; fi
        PRIMARY_INDEX="${i}"
        ;;
      "PHYSICAL STANDBY|READ ONLY WITH APPLY")
        if [ "${STANDBY_INDEX}" -ge 0 ]; then ready=1; fi
        STANDBY_INDEX="${i}"
        ;;
      *)
        ready=1
        ;;
    esac
  done
  if [ "${PRIMARY_INDEX}" -lt 0 ] || [ "${STANDBY_INDEX}" -lt 0 ]; then
    ready=1
  fi

  if [ "${PRIMARY_INDEX}" -ge 0 ]; then
    db_unique="${DG_UNIQUES[${PRIMARY_INDEX}]}"
    host_ip="${DG_HOST_IPS[${PRIMARY_INDEX}]}"
    home="${DG_HOMES[${PRIMARY_INDEX}]}"
    role=PRIMARY
    start_option=open
    check_database_config "${host_ip}" "${home}" "${db_unique}" "${role}" "${start_option}"
    check_listener_config "${host_ip}" LISTENER_SUPER "${home}" 1521 192.168.87.31
    check_service_configs "${host_ip}" "${home}" "${db_unique}" 4
    check_service_resource "${host_ip}" "${db_unique}" super_svc PRIMARY
    check_service_resource "${host_ip}" "${db_unique}" super_pri PRIMARY
    check_service_resource "${host_ip}" "${db_unique}" super_tac PRIMARY
  fi

  if [ "${STANDBY_INDEX}" -ge 0 ]; then
    db_unique="${DG_UNIQUES[${STANDBY_INDEX}]}"
    host_ip="${DG_HOST_IPS[${STANDBY_INDEX}]}"
    home="${DG_HOMES[${STANDBY_INDEX}]}"
    role=PHYSICAL_STANDBY
    start_option="read only"
    check_database_config "${host_ip}" "${home}" "${db_unique}" "${role}" "${start_option}"
    check_listener_config "${host_ip}" LISTENER_SUPER "${home}" 1521 192.168.87.32
    check_service_configs "${host_ip}" "${home}" "${db_unique}" 4
    check_service_resource "${host_ip}" "${db_unique}" super_stb PHYSICAL_STANDBY
  fi

  # Standalone duper/fluff remain on superdb1, regardless of DG role location.
  check_standalone_database duper LISTENER_DUPER 1522 duper_svc
  check_standalone_database fluff LISTENER_FLUFF 1523 fluff_svc

  observer_state="$(remote_state "${IP_OBSERVER}" '
    getent hosts superdc1.domain.is superdc2.domain.is
    systemctl is-enabled oracle-fsfo-observer.service
    systemctl is-active oracle-fsfo-observer.service
    set -a
    source /etc/sysconfig/oracle-fsfo-observer
    set +a
    runuser -u oracle -- env ORACLE_HOME="${OBSERVER_CLIENT_HOME}" TNS_ADMIN="${TNS_ADMIN}" \
      "${OBSERVER_CLIENT_HOME}/bin/dgmgrl" -silent "${DGMGRL_CONNECT}" \
      "SHOW FAST_START FAILOVER"
  ' || true)"
  append_check "observer" "${observer_state}" \
    "both VIP aliases, systemd enabled/active, FSFO enabled with a registered observer"
  output_has "${observer_state}" "192.168.87.31" || ready=1
  output_has "${observer_state}" "192.168.87.32" || ready=1
  output_has "${observer_state}" "enabled" || ready=1
  output_has "${observer_state}" "active" || ready=1
  output_has "${observer_state}" "Fast-Start Failover: Enabled" || ready=1
  output_has "${observer_state}" "Protection Mode:    MaxAvailability" || ready=1
  output_has "${observer_state}" "Observer:" || ready=1
  if grep -Eq 'Observer:[[:space:]]+\(none\)' <<<"${observer_state}"; then
    ready=1
  fi

  return "${ready}"
}

deadline="$(lab_shutdown_deadline_after "${VERIFY_TIMEOUT_SECONDS}")" ||
  die "Could not establish verification deadline"
attempt=0

while true; do
  attempt=$((attempt + 1))
  if check_lab_autostart; then
    log "Automatic startup verified after ${attempt} check(s)."
    printf '%s\n' "${LAST_REPORT}"
    exit 0
  fi

  if lab_shutdown_deadline_expired "${deadline}"; then
    warn "Automatic startup did not converge within ${VERIFY_TIMEOUT_SECONDS}s."
    printf '%s\n' "${LAST_REPORT}" >&2
    exit 1
  fi

  log "Oracle startup not ready (check ${attempt}); retrying in ${VERIFY_POLL_SECONDS}s"
  sleep "${VERIFY_POLL_SECONDS}"
done
