"""
test_03_instance.py — instance + listener assertions for the slice.

Verifies the `super` instance is OPEN READ WRITE, the listener answers on
superdb.domain.is:1521, and the client-facing service super_svc resolves.
Uses python-oracledb from the control host.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest

pytestmark = pytest.mark.slice
REPO_ROOT = Path(__file__).resolve().parents[1]


def _current_super_home(lab_exec) -> str:
    r = lab_exec(
        "su - oracle -c "
        + shlex.quote(
            "/grid/19c/gi_home1/bin/srvctl config database -db super | "
            "sed -n 's/^Oracle home: //p'"
        )
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().splitlines()[-1]
    return "/super/app/oracle/db_home1"


def _run_super_sql(lab_exec, sql: str, timeout: int = 60):
    oracle_home = _current_super_home(lab_exec)
    probe = lab_exec(
        f"stat -c '%s' {oracle_home}/bin/sqlplus 2>/dev/null || echo 0"
    )
    size = int((probe.stdout or "0").strip().splitlines()[-1] or "0")
    if size == 0:
        pytest.skip("sqlplus not linked (OL8+ install gap); DB instance not created.")

    cmd = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        f"{sql}\n"
        "EXIT;\n"
        "SQL"
    )
    return lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=timeout)


def test_db_manage_role_uses_writable_dbca_response_path():
    main_tasks = (
        REPO_ROOT / "roles/oracle_db_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")
    manage_defaults = (
        REPO_ROOT / "roles/oracle_db_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    instance_tasks = (
        REPO_ROOT / "roles/oracle_db_manage/tasks/manage-instance.yml"
    ).read_text(encoding="utf-8")
    dbca_response = (
        REPO_ROOT / "roles/oracle_db_manage/templates/dbca.rsp.j2"
    ).read_text(encoding="utf-8")
    network_tasks = (
        REPO_ROOT / "roles/oracle_network/tasks/main.yml"
    ).read_text(encoding="utf-8")
    network_defaults = (
        REPO_ROOT / "roles/oracle_network/defaults/main.yml"
    ).read_text(encoding="utf-8")
    service_tasks = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/create-service.yml"
    ).read_text(encoding="utf-8") + (
        REPO_ROOT / "roles/oracle_service_manage/tasks/reconcile-service.yml"
    ).read_text(encoding="utf-8")
    service_main_tasks = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")
    service_defaults = (
        REPO_ROOT / "roles/oracle_service_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    lab_group_vars = (
        REPO_ROOT / "inventory/group_vars/all.yml"
    ).read_text(encoding="utf-8")
    test_conftest = (REPO_ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    test_runner = (REPO_ROOT / "scripts/run-tests.sh").read_text(encoding="utf-8")
    site = (REPO_ROOT / "playbooks/site.yml").read_text(encoding="utf-8")

    assert "_db_instances" not in main_tasks
    assert "oracle_db_manage_apply_instance_overrides_require_dataguard" in main_tasks
    assert "oracle_db_manage_apply_instance_overrides_require_dataguard: true" in manage_defaults
    assert "oracle_db_manage_apply_instance_overrides_require_dataguard: false" in site
    assert "'standby' not in group_names" in main_tasks
    assert "or (inst.dataguard" not in main_tasks
    assert "inst.dataguard | default(false) | bool or 'standby' not in group_names" in service_main_tasks
    assert "or (inst.dataguard" not in service_main_tasks
    assert "oracle_service_apply_instance_overrides_require_dataguard" in service_main_tasks
    assert "oracle_service_apply_instance_overrides_require_dataguard: true" in service_defaults
    assert "oracle_service_apply_instance_overrides_require_dataguard: false" in site
    assert "oracle_stage_dir }}/{{ inst.name }}_dbca.rsp" not in instance_tasks
    assert "_dbca_response_file" in instance_tasks
    assert "autostartDuringBuild" not in dbca_response
    assert "dbUniqueName=" in dbca_response
    assert "dbUniquename=" not in dbca_response
    assert "* 1024" in dbca_response
    assert "'100% complete' in (_dbca.stdout | default(''))" in instance_tasks
    assert "map('combine'" not in network_tasks
    assert "'standby' not in group_names" in network_tasks
    assert (
        "set include_inst = ('standby' not in group_names or "
        "(inst.dataguard | default(false) | bool))"
        in network_tasks
    )
    assert "if dg_mode else ('standby' not in group_names" not in network_tasks
    assert "Ensure guest /etc/hosts has the lab host aliases" in network_tasks
    assert "oracle_network_open_firewall: false" in network_defaults
    assert "oracle_lab_host_map_mode: standalone" in network_defaults
    assert "oracle_lab_listener_vips: []" in network_defaults
    assert "oracle_network_persist_listener_vips: true" in network_defaults
    assert "oracle_network_listener_vip_prefix: 24" in network_defaults
    assert "oracle_network_open_firewall: true" in lab_group_vars
    assert "oracle_lab_host_map_mode: standalone" in lab_group_vars
    assert "192.168.87.21" in lab_group_vars
    assert "names: superdb.domain.is superdb" in lab_group_vars
    assert "modes: [standalone]" in lab_group_vars
    assert "_listener_host" in instance_tasks
    assert "ALTER SYSTEM SET sga_target" in instance_tasks
    assert "ALTER SYSTEM SET pga_aggregate_target" in instance_tasks
    assert "Validate custom database parameters" in instance_tasks
    assert "param.name is match" in instance_tasks
    assert "Apply custom database parameters" in instance_tasks
    assert "ALTER SYSTEM SET {{ param.name }}" in instance_tasks
    assert "param.quote | default(false)" in instance_tasks
    assert "ALTER SYSTEM SET local_listener" in instance_tasks
    assert "_db_reachable: false" in instance_tasks
    assert "_dbfacts_fields: []" in instance_tasks
    assert "_db_reconcile_writable: false" in instance_tasks
    assert "Fail when the database is not ready for reconciliation" in instance_tasks
    assert "_dbfacts_fields[3] == 'PRIMARY'" in instance_tasks
    assert "PHYSICAL STANDBY" in instance_tasks
    assert "READ ONLY WITH APPLY" in instance_tasks
    assert "Fail when Data Guard inventory disables flashback" in instance_tasks
    assert "when: _db_reconcile_writable | default(false)" in instance_tasks
    assert "192.168.87.31" in lab_group_vars
    assert "names: superdc1.domain.is superdc1" in lab_group_vars
    assert "192.168.87.32" in lab_group_vars
    assert "names: superdc2.domain.is superdc2" in lab_group_vars
    assert "Assign dedicated listener VIPs to the guest interface" in network_tasks
    assert "Remove unmanaged lab listener VIPs from the guest interface" in network_tasks
    assert "nmcli is required to remove stale listener VIPs" in network_tasks
    assert "ip addr del \"$ip/$prefix\" dev \"$iface\"" in network_tasks
    assert " -ipv4.addresses \"$ip/$prefix\"" in network_tasks
    assert "nmcli is required to persist listener VIP" in network_tasks
    assert "nmcli connection modify" in network_tasks
    assert "ip addr add" in network_tasks
    assert "register: _guest_hosts" in network_tasks
    assert "Restart listener where bind inputs changed" in network_tasks
    assert "_listener_vip_assign.changed" in network_tasks
    assert "'TNS-01106' not in (_lsnr_start.stdout | default(''))" in network_tasks
    assert "Probe firewalld state" in network_tasks
    assert "firewall-cmd --add-port={{ inst._port }}/tcp" in network_tasks
    assert "firewall-cmd --permanent --add-port={{ inst._port }}/tcp" in network_tasks
    assert "r.inst is defined" in network_tasks
    assert "r.item is defined" not in network_tasks
    assert "ALTER SYSTEM REGISTER" in service_tasks
    assert "Read local database role before service reconciliation" in service_tasks
    assert "PRIMARY|READ WRITE" in service_tasks
    assert "_svc_manage_current_role" in service_tasks
    assert "_svc_restart_db" in service_tasks
    assert "Add role-based service to Oracle Restart" in service_tasks
    assert "SERVICE_REGISTERED_FOR_{{ _svc_role }}_ROLE" in service_tasks
    assert "Enable and start matching role-based service" in service_tasks
    assert "srvctl\" enable service" in service_tasks
    assert "srvctl\" start service" in service_tasks
    assert "already enabled|PRCR-1002" in service_tasks
    assert "SQLCODE = -44305" in service_tasks
    assert "SQLCODE = -446" not in service_tasks
    assert "'ORA-' in (_svc_sql.stdout | default(''))" in service_tasks
    assert 'SYS_USER = _env("ORACLE_TEST_USER", "sys")' in test_conftest
    assert 'ORACLE_TEST_USER="${ORACLE_TEST_USER:-sys}"' in test_runner
    assert (
        "Ensure online redo groups have members in the dedicated redo directory"
        in instance_tasks
    )
    assert "ALTER DATABASE ADD LOGFILE MEMBER" in instance_tasks
    assert "{{ inst.dirs.redo }}/online_redo_g" in instance_tasks
    assert (
        "Remove online redo members outside the dedicated redo directory"
        in instance_tasks
    )
    assert "ALTER DATABASE DROP LOGFILE MEMBER" in instance_tasks
    assert "member NOT LIKE '{{ inst.dirs.redo }}/%'" in instance_tasks
    assert "ALTER DATABASE FLASHBACK ON" in instance_tasks
    assert "ALTER DATABASE FLASHBACK OFF" in instance_tasks
    assert "and (inst.flashback | default(false))" not in instance_tasks
    assert "ALTER DATABASE FORCE LOGGING" in instance_tasks
    assert "ALTER DATABASE NO FORCE LOGGING" in instance_tasks


def test_instance_is_open_read_write(db_connection):
    cur = db_connection.cursor()
    cur.execute("SELECT open_mode, database_role FROM v$database")
    row = cur.fetchone()
    cur.close()
    assert row is not None, "v$database returned no row"
    open_mode, role = row
    assert open_mode == "READ WRITE", f"expected READ WRITE, got {open_mode}"
    assert role == "PRIMARY", f"expected PRIMARY, got {role}"


def test_listener_answers_on_vip(db_conn_kwargs):
    """TCP connect to the dedicated listener VIP."""
    import socket
    try:
        s = socket.create_connection(
            (db_conn_kwargs["host"], db_conn_kwargs["port"]), timeout=5
        )
    except (socket.gaierror, OSError) as exc:
        pytest.skip(
            f"could not resolve/reach {db_conn_kwargs['host']}:{db_conn_kwargs['port']} "
            f"— bring the lab up (lab/scripts/lab-up.sh) first: {exc}"
        )
    s.close()


def test_standalone_listener_uses_dedicated_vip(lab_exec):
    host_lookup = lab_exec("getent hosts superdb.domain.is | awk '{print $1}'")
    dg_lookup = lab_exec("getent hosts superdc1.domain.is")
    vip_addr = lab_exec("ip -4 addr show | grep -w '192.168.87.21/24'")
    if dg_lookup.returncode == 0 and dg_lookup.stdout.strip():
        if vip_addr.returncode != 0:
            pytest.skip("Lab is in Data Guard listener mode; standalone VIP is not mapped.")
    assert host_lookup.returncode == 0, host_lookup.stderr
    assert host_lookup.stdout.strip().splitlines()[-1] == "192.168.87.21"

    assert vip_addr.returncode == 0, vip_addr.stderr


def test_service_super_svc_resolves(db_connection):
    cur = db_connection.cursor()
    # The service we connected through IS super_svc (per conftest). Confirm it
    # is listed in v$active_services / v$services.
    cur.execute(
        "SELECT name FROM v$active_services WHERE name = 'super_svc'"
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None, "super_svc service not active"


def test_db_unique_name(db_connection):
    cur = db_connection.cursor()
    cur.execute("SELECT db_unique_name FROM v$database")
    row = cur.fetchone()
    cur.close()
    assert row is not None
    # Standalone: db_unique_name == db_name == super.
    assert row[0].lower() == "super", f"unexpected db_unique_name: {row[0]}"


def test_configured_memory_parameters_match_inventory(db_connection):
    cur = db_connection.cursor()
    cur.execute(
        """
        SELECT name, value
          FROM v$parameter
         WHERE name IN ('sga_target', 'pga_aggregate_target')
        """
    )
    rows = dict(cur.fetchall())
    cur.close()

    assert rows == {
        "sga_target": str(2 * 1024 * 1024 * 1024),
        "pga_aggregate_target": str(1 * 1024 * 1024 * 1024),
    }


def test_dedicated_data_path_used(lab_exec):
    """Data files must live under /super/d01 (the dedicated data dir)."""
    sql = (
        "SELECT count(*) FROM v$datafile WHERE name LIKE '/super/d01%';\n"
    )
    r = _run_super_sql(lab_exec, sql)
    assert r.returncode == 0, r.stderr
    count = int((r.stdout or "0").strip() or "0")
    assert count > 0, f"no datafiles under /super/d01; output: {r.stdout}"


def test_database_files_are_filesystem_backed_and_use_dedicated_paths(lab_exec):
    sql = """
SELECT 'DATAFILES_IN_D01|' || COUNT(*) FROM v$datafile WHERE name LIKE '/super/d01/%';
SELECT 'TEMPFILES_IN_D01|' || COUNT(*) FROM v$tempfile WHERE name LIKE '/super/d01/%';
SELECT 'CONTROLFILES_IN_FS|' || COUNT(*)
  FROM v$controlfile
 WHERE name LIKE '/super/d01/%' OR name LIKE '/super/f01/%';
SELECT 'ONLINE_REDO_GROUPS|' || COUNT(DISTINCT group#) FROM v$log;
SELECT 'ONLINE_REDO_GROUPS_WITH_R01|' || COUNT(DISTINCT group#)
  FROM v$logfile
 WHERE type = 'ONLINE' AND member LIKE '/super/r01/%';
SELECT 'ONLINE_REDO_MEMBERS|' || COUNT(*)
  FROM v$logfile
 WHERE type = 'ONLINE';
SELECT 'ONLINE_REDO_MEMBERS_IN_R01|' || COUNT(*)
  FROM v$logfile
 WHERE type = 'ONLINE' AND member LIKE '/super/r01/%';
SELECT 'ASM_FILE_COUNT|' || COUNT(*) FROM (
  SELECT name path FROM v$datafile
  UNION ALL SELECT name FROM v$tempfile
  UNION ALL SELECT member FROM v$logfile
  UNION ALL SELECT name FROM v$controlfile
) WHERE path LIKE '+%';
SELECT 'DB_CREATE_FILE_DEST|' || value
  FROM v$parameter
 WHERE name = 'db_create_file_dest';
SELECT 'DB_RECOVERY_FILE_DEST|' || value
  FROM v$parameter
 WHERE name = 'db_recovery_file_dest';
SELECT 'LOG_ARCHIVE_DEST_1|' || value
  FROM v$parameter
 WHERE name = 'log_archive_dest_1';
"""
    r = _run_super_sql(lab_exec, sql)

    assert r.returncode == 0, r.stdout + r.stderr
    facts = dict(
        line.strip().split("|", 1)
        for line in r.stdout.splitlines()
        if "|" in line
    )
    assert int(facts["DATAFILES_IN_D01"]) > 0
    assert int(facts["TEMPFILES_IN_D01"]) > 0
    assert int(facts["CONTROLFILES_IN_FS"]) > 0
    assert facts["ASM_FILE_COUNT"] == "0"
    assert facts["DB_CREATE_FILE_DEST"] == "/super/d01"
    assert facts["DB_RECOVERY_FILE_DEST"] == "/super/f01"
    assert facts["LOG_ARCHIVE_DEST_1"] == "LOCATION=/super/a01"
    assert int(facts["ONLINE_REDO_GROUPS"]) > 0
    assert facts["ONLINE_REDO_GROUPS_WITH_R01"] == facts["ONLINE_REDO_GROUPS"]
    assert facts["ONLINE_REDO_MEMBERS_IN_R01"] == facts["ONLINE_REDO_MEMBERS"]


def test_archivelog_mode_matches_desired(db_connection):
    cur = db_connection.cursor()
    cur.execute("SELECT log_mode FROM v$database")
    row = cur.fetchone()
    cur.close()
    assert row is not None
    # The slice default for `super` is archivelog: true.
    assert row[0] == "ARCHIVELOG", f"expected ARCHIVELOG, got {row[0]}"
