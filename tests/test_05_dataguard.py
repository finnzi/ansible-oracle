"""Data Guard live assertions for standby, broker, and switchovers."""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.slice


def _oracle_home(exec_fn, db_unique_name: str) -> str:
    candidates = [db_unique_name]
    peer_name = "super_sby" if db_unique_name == "super" else "super"
    if peer_name not in candidates:
        candidates.append(peer_name)
    for candidate in candidates:
        r = exec_fn(
            "su - oracle -c "
            + shlex.quote(
                f"/grid/19c/gi_home1/bin/srvctl config database -db {candidate} | "
                "sed -n 's/^Oracle home: //p'"
            )
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[-1]
    return "/super/app/oracle/db_home1"


def test_dataguard_defaults_use_maximum_availability():
    defaults_text = (
        REPO_ROOT / "roles/oracle_dataguard/defaults/main.yml"
    ).read_text(encoding="utf-8")

    assert "protection mode: always MAXIMUM AVAILABILITY" in defaults_text
    assert "dg_protection_mode:" not in defaults_text
    assert "MAXIMUM PERFORMANCE" not in defaults_text
    assert "MAXIMUM PROTECTION" not in defaults_text
    assert "oracle_dataguard_prepare_primary: false" in defaults_text
    assert "oracle_dataguard_duplicate_standby: false" in defaults_text
    assert "oracle_dataguard_configure_broker: false" in defaults_text
    assert "oracle_dataguard_auto_switchover_target: auto" in defaults_text
    assert "oracle_dataguard_switchover_instance: \"\"" in defaults_text


def test_dataguard_inventory_and_network_prerequisites_are_wired():
    all_vars = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(
        encoding="utf-8"
    )
    primary_vars = (REPO_ROOT / "inventory/group_vars/primary.yml").read_text(
        encoding="utf-8"
    )
    standby_vars = (REPO_ROOT / "inventory/group_vars/standby.yml").read_text(
        encoding="utf-8"
    )
    network_tasks = (
        REPO_ROOT / "roles/oracle_network/tasks/main.yml"
    ).read_text(encoding="utf-8")
    network_defaults = (
        REPO_ROOT / "roles/oracle_network/defaults/main.yml"
    ).read_text(encoding="utf-8")
    listener_template = (
        REPO_ROOT / "roles/oracle_network/templates/listener.ora.j2"
    ).read_text(encoding="utf-8")
    tns_template = (
        REPO_ROOT / "roles/oracle_network/templates/tnsnames.ora.j2"
    ).read_text(encoding="utf-8")
    dataguard_tasks = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/main.yml"
    ).read_text(encoding="utf-8")
    dataguard_prepare = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/prepare-primary.yml"
    ).read_text(encoding="utf-8")
    dataguard_prepare_standby = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/prepare-standby.yml"
    ).read_text(encoding="utf-8")
    dataguard_duplicate_standby = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/duplicate-standby.yml"
    ).read_text(encoding="utf-8")
    restart_tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")
    restart_defaults = (
        REPO_ROOT / "roles/oracle_restart_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    dataguard_flashback = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/ensure-flashback.yml"
    ).read_text(encoding="utf-8")
    dataguard_configure_broker = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/configure-broker.yml"
    ).read_text(encoding="utf-8")
    dataguard_defaults = (
        REPO_ROOT / "roles/oracle_dataguard/defaults/main.yml"
    ).read_text(encoding="utf-8")
    dataguard_switchover = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/switchover.yml"
    ).read_text(encoding="utf-8")
    dataguard_playbook = (
        REPO_ROOT / "playbooks/05-dataguard.yml"
    ).read_text(encoding="utf-8")
    dataguard_meta = (
        REPO_ROOT / "roles/oracle_dataguard/meta/main.yml"
    ).read_text(encoding="utf-8")
    service_tasks = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")

    assert "192.168.87.31" in all_vars
    assert "superdc1.domain.is superdc1" in all_vars
    assert "192.168.87.32" in all_vars
    assert "superdc2.domain.is superdc2" in all_vars
    assert "dataguard: true" in primary_vars
    assert "flashback: true" in primary_vars
    assert "listener_vip: \"superdc1.domain.is\"" in primary_vars
    assert "db_unique_name: super" in primary_vars
    assert "dataguard: true" in standby_vars
    assert "flashback: true" in standby_vars
    assert "listener_vip: \"superdc2.domain.is\"" in standby_vars
    assert "db_unique_name: super_sby" in standby_vars
    assert "oracle_apply_instance_overrides" in network_tasks
    assert "oracle_network_dataguard_enabled: false" in network_defaults
    assert "oracle_network_dataguard_enabled | default(false)" in network_tasks
    assert (
        "| oracle_apply_instance_overrides(oracle_instance_overrides | default({}), require_dg)"
        in network_tasks
    )
    assert "set inst = raw_inst" in network_tasks
    assert (
        "set include_inst = ('standby' not in group_names or "
        "(inst.dataguard | default(false) | bool))"
        in network_tasks
    )
    assert "if dg_mode else ('standby' not in group_names" not in network_tasks
    assert "oracle_lab_guest_hosts | map(attribute='names')" in network_tasks
    assert "Remove stale lab host aliases from guest /etc/hosts" in network_tasks
    assert "'dc2' if 'standby' in group_names else 'dc1'" in network_tasks
    assert "lab_domain | default('domain.is')" in network_tasks
    assert (
        "oracle_apply_instance_overrides(oracle_instance_overrides | default({}), false)"
        in dataguard_tasks
    )
    assert "Prepare primary database for Data Guard" in dataguard_tasks
    assert "oracle_dataguard_prepare_primary | bool" in dataguard_tasks
    assert "Prepare standby auxiliary for Data Guard" in dataguard_tasks
    assert "oracle_dataguard_prepare_standby | bool" in dataguard_tasks
    assert "Duplicate physical standby for Data Guard" in dataguard_tasks
    assert "Ensure Data Guard flashback prerequisite" in dataguard_tasks
    assert "oracle_dataguard_duplicate_standby | bool" in dataguard_tasks
    assert "Configure Data Guard broker" in dataguard_tasks
    assert "oracle_dataguard_configure_broker | bool" in dataguard_tasks
    assert "Switchover Data Guard broker primary" in dataguard_tasks
    assert "Fail when switchover is requested without a target" in dataguard_tasks
    assert "Fail when switchover target does not match a Data Guard instance" in dataguard_tasks
    assert "Fail when automatic switchover is ambiguous across instances" in dataguard_tasks
    assert "oracle_dataguard_run_switchover | bool" in dataguard_tasks
    assert "oracle_dataguard_auto_switchover_target" in dataguard_tasks
    assert "oracle_dataguard_switchover_instance" in dataguard_tasks
    assert "'primary' in group_names" in dataguard_tasks
    assert "oracle_dataguard_switchover_target in [" in dataguard_tasks
    assert "Register instance, listener, and start them under Restart" in restart_tasks
    assert "oracle_restart_apply_instance_overrides_require_dataguard: true" in restart_defaults
    assert "oracle_restart_apply_instance_overrides_require_dataguard | default(true)" in restart_tasks
    assert "'standby' in group_names" in restart_tasks
    assert "inst.dg_role | default('') == 'standby'" in restart_tasks
    assert "hosts: oracle_db_hosts" in dataguard_playbook
    assert "oracle_network_dataguard_enabled: true" in dataguard_playbook
    assert "oracle_lab_host_map_mode: dataguard" in dataguard_playbook
    assert "oracle_dataguard_prepare_primary: true" in dataguard_playbook
    assert "oracle_dataguard_prepare_standby: true" in dataguard_playbook
    assert "oracle_dataguard_duplicate_standby: true" in dataguard_playbook
    assert "oracle_dataguard_configure_broker: true" in dataguard_playbook
    assert "dependencies: []" in dataguard_meta
    assert "standby_file_management" in dataguard_prepare
    assert "dg_broker_start" in dataguard_prepare
    assert "log_archive_config" in dataguard_prepare
    assert "log_archive_dest_2" in dataguard_prepare
    assert "SYNC AFFIRM" in dataguard_prepare
    assert "oracle_dataguard_configure_broker | default(false) | bool" in dataguard_prepare
    assert "fal_server" in dataguard_prepare
    assert "local_listener" in dataguard_prepare
    assert "ALTER SYSTEM REGISTER" in dataguard_prepare
    assert "ALTER DATABASE ADD STANDBY LOGFILE" in dataguard_prepare
    assert "STARTUP NOMOUNT" in dataguard_prepare_standby
    assert "Check registered physical standby before auxiliary startup" in dataguard_prepare_standby
    assert "Start registered physical standby instead of auxiliary NOMOUNT" in dataguard_prepare_standby
    assert "'ORA-19838' not in (_dg_registered_standby_start.stdout | default(''))" in dataguard_prepare_standby
    assert "'ORA-19838' in (_dg_registered_standby_start.stdout | default(''))" in dataguard_prepare_standby
    assert "'NOT_REGISTERED' in (_dg_registered_standby_status.stdout | default(''))" in dataguard_prepare_standby
    assert "Restart standby auxiliary when pfile changes" in dataguard_prepare_standby
    assert "orapwd" in dataguard_prepare_standby
    assert "{{ _dg_standby_unique_name }}_dgb as sysdba" in dataguard_prepare_standby
    assert "DUPLICATE TARGET DATABASE" in dataguard_duplicate_standby
    assert "FROM ACTIVE DATABASE" in dataguard_duplicate_standby
    assert "PHYSICAL STANDBY" in dataguard_duplicate_standby
    assert "Read standby spfile in use" in dataguard_duplicate_standby
    assert "Configure standby Data Guard initialization parameters" in dataguard_duplicate_standby
    assert "ALTER SYSTEM SET fal_server='{{ _dg_primary_unique_name }}_dgb' SCOPE=BOTH" in dataguard_duplicate_standby
    assert "Remove conflicting standalone Restart registration on standby" in dataguard_duplicate_standby
    assert "Start registered physical standby before role probe" in dataguard_duplicate_standby
    assert "DATABASE_ALREADY_RUNNING_OUTSIDE_RESTART" in dataguard_duplicate_standby
    assert "Restart standby from spfile for broker management" in dataguard_duplicate_standby
    assert "'NOT_REGISTERED' in (_dg_standby_registered_status_before.stdout | default(''))" in dataguard_duplicate_standby
    assert "oracle_dataguard_configure_broker | default(false) | bool" in dataguard_duplicate_standby
    assert "STARTUP MOUNT" in dataguard_duplicate_standby
    assert "-role PHYSICAL_STANDBY" in dataguard_duplicate_standby
    assert "srvctl\" add database" in dataguard_duplicate_standby
    assert "Validate standby Restart registration" in dataguard_duplicate_standby
    assert "ALTER DATABASE FLASHBACK ON" in dataguard_flashback
    assert "SHUTDOWN ABORT" in dataguard_flashback
    assert "replace('ORA-01109', '')" in dataguard_flashback
    assert "replace('ORA-16136', '')" in dataguard_flashback
    assert "ALTER DATABASE OPEN READ ONLY" in dataguard_flashback
    assert "PHYSICAL STANDBY|" in dataguard_flashback
    assert "oracle_dataguard_observer_user:" in dataguard_defaults
    assert "oracle_dataguard_observer_password:" in dataguard_defaults
    assert "Ensure observer SYSDG account exists on the primary" in dataguard_configure_broker
    assert "GRANT SYSDG TO" in dataguard_configure_broker
    assert "Validate observer SYSDG account can inspect broker" in dataguard_configure_broker
    assert "CREATE CONFIGURATION" in dataguard_configure_broker
    assert "Wait for standby broker member to be available" in dataguard_configure_broker
    assert "SHOW DATABASE '{{ _dg_standby_unique_name }}'" in dataguard_configure_broker
    assert "EDIT CONFIGURATION SET PROTECTION MODE AS MAXAVAILABILITY" in dataguard_configure_broker
    assert "Stop standby apply through broker before opening read-only" in dataguard_configure_broker
    assert "READ ONLY WITH APPLY" in dataguard_configure_broker
    assert "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY" in dataguard_configure_broker
    assert "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY" in dataguard_configure_broker
    assert "LogXptMode='SYNC'" in dataguard_configure_broker
    assert "export ORACLE_SID={{ inst.name }}" in dataguard_configure_broker
    assert "SWITCHOVER TO '{{ _dg_switchover_target }}'" in dataguard_switchover
    assert "_dg_switchover_requested_target" in dataguard_switchover
    assert "_dg_standby_unique_name if _dg_switchover_requested_target == oracle_dataguard_auto_switchover_target" in dataguard_switchover
    assert "ALREADY_PRIMARY" in dataguard_switchover
    assert "_dg_switchover_target_is_physical_standby" in dataguard_switchover
    assert "READ ONLY WITH APPLY" in dataguard_switchover
    assert "_DGMGRL" in listener_template
    assert "dg_primary_unique = inst.dg_primary_db_unique_name" in tns_template
    assert "dg_standby_unique = inst.dg_standby_db_unique_name" in tns_template
    assert "inst.name ~ 'dc1.'" in tns_template
    assert "inst.name ~ 'dc2.'" in tns_template
    assert "(FAILOVER = ON)" in tns_template
    assert "(LOAD_BALANCE = OFF)" in tns_template
    assert "SERVICE_NAME = {{ inst.service_name" in tns_template
    assert "dg_primary_unique = inst.dg_primary_db_unique_name | default(inst.name)" in tns_template
    assert "dg_primary_unique ~ '_dgb'" in tns_template
    assert "dg_standby_unique ~ '_dgb'" in tns_template
    assert "DGMGRL can create, inspect, and switchover" in tns_template
    assert "Data Guard current-primary service requires Restart ownership" in service_tasks
    assert "would not follow the current primary after" in service_tasks
    assert "oracle_restart_available | default(false)" in service_tasks


def test_primary_dataguard_prerequisites(lab_exec):
    oracle_home = _oracle_home(lab_exec, "super")
    sql = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 TRIMSPOOL ON FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'standby_file_management';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'dg_broker_start';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'log_archive_config';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'log_archive_dest_2';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'log_archive_dest_state_2';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'fal_server';\n"
        "SELECT NVL(value, '<unset>') FROM v$parameter WHERE name = 'local_listener';\n"
        "SELECT count(*) FROM v$standby_log;\n"
        "SELECT count(*) + 1 FROM v$log WHERE thread# = 1;\n"
        "SELECT count(*) FROM v$logfile WHERE type = 'STANDBY' AND member LIKE '/super/r01/%';\n"
        "EXIT;\n"
        "SQL"
    )
    last = None
    for _ in range(18):
        last = lab_exec(f"su - oracle -c {shlex.quote(sql)}")
        assert last.returncode == 0, last.stderr
        assert "ORA-" not in last.stdout
        lines = [line.strip() for line in last.stdout.splitlines() if line.strip()]
        if len(lines) >= 10:
            break
        time.sleep(10)
    assert last is not None
    lines = [line.strip() for line in last.stdout.splitlines() if line.strip()]
    assert len(lines) >= 10, last.stdout
    standby_file_management = lines[0]
    dg_broker_start = lines[1]
    log_archive_config = lines[2]
    log_archive_dest_2 = lines[3]
    log_archive_dest_state_2 = lines[4]
    fal_server = lines[5]
    local_listener = lines[6]
    standby_log_count = int(lines[7])
    needed_standby_logs = int(lines[8])
    standby_logs_on_dedicated_path = int(lines[9])

    assert standby_file_management == "AUTO"
    assert dg_broker_start == "TRUE"
    assert "DG_CONFIG=(" in log_archive_config
    assert "super_sby" in log_archive_config
    log_archive_dest_2_lower = log_archive_dest_2.lower()
    assert (
        'service="super_sby_dgb"' in log_archive_dest_2_lower
        or "service_name=super_sby_dgmgrl" in log_archive_dest_2_lower
    )
    assert "sync" in log_archive_dest_2_lower
    assert "affirm" in log_archive_dest_2_lower
    assert 'db_unique_name="super_sby"' in log_archive_dest_2_lower
    assert log_archive_dest_state_2.upper() == "ENABLE"
    assert fal_server in {"super_sby_dgb", "<unset>"}
    assert "HOST=superdc1.domain.is" in local_listener
    assert standby_log_count >= needed_standby_logs
    assert standby_logs_on_dedicated_path == standby_log_count


def test_dataguard_listener_identities(lab_exec, standby_exec):
    primary_hosts = lab_exec("getent hosts superdc1.domain.is superdc2.domain.is")
    standby_hosts = standby_exec("getent hosts superdc1.domain.is superdc2.domain.is")
    assert primary_hosts.returncode == 0, primary_hosts.stderr
    assert standby_hosts.returncode == 0, standby_hosts.stderr
    assert "192.168.87.31" in primary_hosts.stdout
    assert "192.168.87.32" in primary_hosts.stdout
    assert "192.168.87.31" in standby_hosts.stdout
    assert "192.168.87.32" in standby_hosts.stdout

    stale_host_check = (
        "awk '$0 !~ /^#/ { for (i = 2; i <= NF; i++) "
        "if ($i == \"superdb.domain.is\" || $i == \"superdb\") print }' /etc/hosts"
    )
    stale_primary = lab_exec(stale_host_check)
    stale_standby = standby_exec(stale_host_check)
    assert stale_primary.stdout.strip() == ""
    assert stale_standby.stdout.strip() == ""

    primary_home = _oracle_home(lab_exec, "super")
    standby_home = _oracle_home(standby_exec, "super_sby")
    primary_listener = lab_exec(
        f"su - oracle -c 'export ORACLE_HOME={primary_home}; "
        f"{primary_home}/bin/lsnrctl status LISTENER_SUPER'"
    )
    standby_listener = standby_exec(
        f"su - oracle -c 'export ORACLE_HOME={standby_home}; "
        f"{standby_home}/bin/lsnrctl status LISTENER_SUPER'"
    )
    assert primary_listener.returncode == 0, primary_listener.stderr
    assert standby_listener.returncode == 0, standby_listener.stderr
    assert "HOST=192.168.87.31" in primary_listener.stdout
    assert "super_DGMGRL" in primary_listener.stdout
    assert "HOST=192.168.87.32" in standby_listener.stdout
    assert "super_sby_DGMGRL" in standby_listener.stdout


def test_standby_auxiliary_prerequisites(standby_exec):
    oracle_home = _oracle_home(standby_exec, "super_sby")
    pfile = standby_exec("test -f /super/app/oracle/db_home1/dbs/initsuper.ora")
    pwfile = standby_exec("test -f /super/app/oracle/db_home1/dbs/orapwsuper")
    oratab = standby_exec(
        "awk -F'#' '/^super:/ {gsub(/[[:space:]]+$/, \"\", $1); print $1}' /etc/oratab | "
        "grep -E '^super:/super/app/oracle/db_home[12]:N$'"
    )
    assert pfile.returncode == 0
    assert pwfile.returncode == 0
    assert oratab.returncode == 0, oratab.stdout + oratab.stderr

    pfile_text = standby_exec("cat /super/app/oracle/db_home1/dbs/initsuper.ora")
    assert "db_unique_name='super_sby'" in pfile_text.stdout
    assert "fal_server='super_dgb'" in pfile_text.stdout
    assert (
        "local_listener='(ADDRESS=(PROTOCOL=TCP)(HOST=superdc2.domain.is)(PORT=1521))'"
        in pfile_text.stdout
    )

    sql = (
        f"export ORACLE_HOME={oracle_home} TNS_ADMIN={oracle_home}/network/admin && "
        "$ORACLE_HOME/bin/sqlplus -L -S 'sys/SysPassword1_@super_sby_dgb as sysdba' <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT status FROM v$instance;\n"
        "SELECT database_role || '|' || open_mode FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    r = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
    assert r.returncode == 0, r.stderr
    if "ORA-01507" in r.stdout:
        assert "STARTED" in r.stdout
    else:
        assert "ORA-" not in r.stdout
        assert (
            "STARTED" in r.stdout
            or "MOUNTED" in r.stdout
            or "OPEN" in r.stdout
        )
        assert "PHYSICAL STANDBY" in r.stdout

    live_fal = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT value FROM v$parameter WHERE name = 'fal_server';\n"
        "EXIT;\n"
        "SQL"
    )
    fal = standby_exec(f"su - oracle -c {shlex.quote(live_fal)}")
    assert fal.returncode == 0, fal.stderr
    assert "ORA-" not in fal.stdout
    assert "super_dgb" in fal.stdout or "super_DGMGRL" in fal.stdout


def test_physical_standby_duplicate(standby_exec):
    oracle_home = _oracle_home(standby_exec, "super_sby")
    sql = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT database_role || '|' || open_mode FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    r = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
    assert r.returncode == 0, r.stderr
    assert "ORA-" not in r.stdout
    assert "PHYSICAL STANDBY" in r.stdout


def test_physical_standby_restart_registration(standby_exec):
    config = standby_exec(
        "/grid/19c/gi_home1/bin/srvctl config database -db super_sby"
    )
    listener = standby_exec(
        "/grid/19c/gi_home1/bin/srvctl config listener -listener LISTENER_SUPER"
    )
    assert config.returncode == 0, config.stdout + config.stderr
    assert listener.returncode == 0, listener.stdout + listener.stderr
    assert "Database unique name: super_sby" in config.stdout
    assert "Database name: super" in config.stdout
    assert "Database role: PHYSICAL_STANDBY" in config.stdout
    assert "Oracle home: /super/app/oracle/db_home2" in config.stdout
    assert "/super/app/oracle/db_home1/dbs/spfilesuper.ora" in config.stdout
    assert "LISTENER_SUPER" in listener.stdout


def test_physical_standby_uses_spfile(standby_exec):
    oracle_home = _oracle_home(standby_exec, "super_sby")
    sql = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT value FROM v$parameter WHERE name = 'spfile';\n"
        "EXIT;\n"
        "SQL"
    )
    r = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
    assert r.returncode == 0, r.stderr
    assert "ORA-" not in r.stdout
    assert "/super/app/oracle/db_home1/dbs/spfilesuper.ora" in r.stdout


def test_primary_reports_dataguard_role_and_protection(db_connection):
    last = None
    for _ in range(18):
        cur = db_connection.cursor()
        cur.execute(
            "SELECT database_role, protection_mode, protection_level FROM v$database"
        )
        last = cur.fetchone()
        cur.close()
        role, protection_mode, protection_level = last
        assert role == "PRIMARY"
        assert protection_mode == "MAXIMUM AVAILABILITY"
        if protection_level == "MAXIMUM AVAILABILITY":
            return
        time.sleep(10)
    assert last is not None
    assert last[2] == "MAXIMUM AVAILABILITY"


def test_standby_is_read_only_with_apply(standby_exec):
    oracle_home = _oracle_home(standby_exec, "super_sby")
    sql = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT database_role || '|' || open_mode || '|' || protection_mode || '|' || protection_level FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    expected = (
        "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
    )
    last = None
    for _ in range(12):
        last = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
        assert last.returncode == 0, last.stderr
        assert "ORA-" not in last.stdout
        if expected in last.stdout:
            return
        time.sleep(10)
    assert last is not None
    assert expected in last.stdout


def test_dgmgrrl_configuration_healthy(lab_exec):
    last = None
    oracle_home = _oracle_home(lab_exec, "super")
    command = (
        "su - oracle -c "
        + shlex.quote(
            f"export ORACLE_HOME={oracle_home} TNS_ADMIN={oracle_home}/network/admin; "
            "$ORACLE_HOME/bin/dgmgrl -silent sys/SysPassword1_@super_dgb "
            "'SHOW CONFIGURATION'"
        )
    )
    for _ in range(18):
        last = lab_exec(command)
        assert last.returncode == 0, last.stderr
        if (
            "SUCCESS" in last.stdout
            and "ORA-" not in last.stdout
            and "Error:" not in last.stdout
        ):
            break
        time.sleep(10)
    assert last is not None
    assert "SUCCESS" in last.stdout
    assert "ORA-" not in last.stdout
    assert "Error:" not in last.stdout
    assert "Protection Mode: MaxAvailability" in last.stdout
    assert "super_sby" in last.stdout


def test_super_service_runs_only_on_current_dataguard_primary(lab_exec, standby_exec):
    _assert_super_service_role(lab_exec, standby_exec, "super")


@pytest.mark.slow
def test_manual_switchover(lab_exec, standby_exec):
    try:
        switched = _run_dataguard_switchover("super_sby")
        assert switched.returncode == 0, switched.stdout + switched.stderr
        assert "failed=0" in switched.stdout

        standby_state = _database_state(standby_exec)
        old_primary_state = _database_state(lab_exec)
        assert "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" in standby_state
        assert "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY" in old_primary_state
        _assert_super_service_role(lab_exec, standby_exec, "super_sby")
    finally:
        restored = _run_dataguard_switchover("super")
        assert restored.returncode == 0, restored.stdout + restored.stderr
        assert "failed=0" in restored.stdout

    primary_state = _database_state(lab_exec)
    standby_state = _database_state(standby_exec)
    assert "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" in primary_state
    assert "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY" in standby_state
    _assert_super_service_role(lab_exec, standby_exec, "super")


@pytest.mark.slow
def test_automatic_switchover(lab_exec, standby_exec):
    try:
        if "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" not in _database_state(lab_exec):
            restored = _run_dataguard_switchover("super")
            assert restored.returncode == 0, restored.stdout + restored.stderr
            assert "failed=0" in restored.stdout

        switched = _run_dataguard_switchover("auto")
        assert switched.returncode == 0, switched.stdout + switched.stderr
        assert "failed=0" in switched.stdout

        standby_state = _database_state(standby_exec)
        old_primary_state = _database_state(lab_exec)
        assert "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" in standby_state
        assert "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY" in old_primary_state
        _assert_super_service_role(lab_exec, standby_exec, "super_sby")

        repeated = _run_dataguard_switchover("auto")
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        assert "failed=0" in repeated.stdout
        assert "changed=0" in repeated.stdout
        _assert_super_service_role(lab_exec, standby_exec, "super_sby")
    finally:
        if "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" not in _database_state(lab_exec):
            restored = _run_dataguard_switchover("super")
            assert restored.returncode == 0, restored.stdout + restored.stderr
            assert "failed=0" in restored.stdout

    primary_state = _database_state(lab_exec)
    standby_state = _database_state(standby_exec)
    assert "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY" in primary_state
    assert "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY" in standby_state
    _assert_super_service_role(lab_exec, standby_exec, "super")


def _run_dataguard_switchover(target: str) -> subprocess.CompletedProcess:
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "playbooks/05-dataguard.yml",
        "-e", "oracle_dataguard_prepare_primary=false",
        "-e", "oracle_dataguard_prepare_standby=false",
        "-e", "oracle_dataguard_duplicate_standby=false",
        "-e", "oracle_dataguard_configure_broker=false",
        "-e", "oracle_dataguard_run_switchover=true",
        "-e", f"oracle_dataguard_switchover_target={target}",
    ]
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    env.setdefault("ANSIBLE_SSH_CONTROL_PATH_DIR", "/tmp/ansible-cp")
    env.setdefault("XDG_CACHE_HOME", "/tmp/ansible-cache")
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _database_state(exec_fn) -> str:
    oracle_home = _oracle_home(exec_fn, "super")
    sql = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT database_role || '|' || open_mode || '|' || protection_mode || '|' || protection_level FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    last = None
    for _ in range(18):
        last = exec_fn(f"su - oracle -c {shlex.quote(sql)}", timeout=90)
        assert last.returncode == 0, last.stderr
        assert "ORA-" not in last.stdout
        if "RESYNCHRONIZATION" not in last.stdout:
            return last.stdout
        time.sleep(10)
    assert last is not None
    return last.stdout


def _assert_super_service_role(lab_exec, standby_exec, expected_primary: str) -> None:
    expected = {
        "super": {
            "primary": "Service super_svc is running",
            "standby": "Service super_svc is not running",
        },
        "super_sby": {
            "primary": "Service super_svc is not running",
            "standby": "Service super_svc is running",
        },
    }[expected_primary]

    last_primary = ""
    last_standby = ""
    for _ in range(18):
        last_primary = _service_state(lab_exec, "super")
        last_standby = _service_state(standby_exec, "super_sby")
        if expected["primary"] in last_primary and expected["standby"] in last_standby:
            return
        time.sleep(10)

    assert expected["primary"] in last_primary
    assert expected["standby"] in last_standby


def _service_state(exec_fn, db_unique_name: str) -> str:
    command = (
        "/grid/19c/gi_home1/bin/srvctl status service "
        f"-db {db_unique_name} -service super_svc 2>&1"
    )
    result = exec_fn(f"su - oracle -c {shlex.quote(command)}", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout
