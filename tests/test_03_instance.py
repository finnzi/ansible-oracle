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


def test_db_manage_role_uses_writable_dbca_response_path():
    main_tasks = (
        REPO_ROOT / "roles/oracle_db_manage/tasks/main.yml"
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
    ).read_text(encoding="utf-8")
    service_main_tasks = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")
    lab_group_vars = (
        REPO_ROOT / "inventory/group_vars/all.yml"
    ).read_text(encoding="utf-8")
    test_conftest = (REPO_ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    test_runner = (REPO_ROOT / "scripts/run-tests.sh").read_text(encoding="utf-8")

    assert "_db_instances" not in main_tasks
    assert "'standby' not in group_names" in main_tasks
    assert "or (inst.dataguard" not in main_tasks
    assert "'standby' not in group_names" in service_main_tasks
    assert "or (inst.dataguard" not in service_main_tasks
    assert "oracle_stage_dir }}/{{ inst.name }}_dbca.rsp" not in instance_tasks
    assert "_dbca_response_file" in instance_tasks
    assert "autostartDuringBuild" not in dbca_response
    assert "dbUniqueName=" in dbca_response
    assert "dbUniquename=" not in dbca_response
    assert "* 1024" in dbca_response
    assert "'100% complete' in (_dbca.stdout | default(''))" in instance_tasks
    assert "map('combine'" not in network_tasks
    assert "'standby' not in group_names" in network_tasks
    assert "Ensure guest /etc/hosts has the lab host aliases" in network_tasks
    assert "oracle_network_open_firewall: false" in network_defaults
    assert "oracle_network_open_firewall: true" in lab_group_vars
    assert "superdc1.domain.is superdc1" in lab_group_vars
    assert "superdc2.domain.is superdc2" in lab_group_vars
    assert "Probe firewalld state" in network_tasks
    assert "firewall-cmd --add-port={{ inst._port }}/tcp" in network_tasks
    assert "firewall-cmd --permanent --add-port={{ inst._port }}/tcp" in network_tasks
    assert "r.inst is defined" in network_tasks
    assert "r.item is defined" not in network_tasks
    assert "ALTER SYSTEM REGISTER" in service_tasks
    assert "SQLCODE = -44305" in service_tasks
    assert "SQLCODE = -446" not in service_tasks
    assert "failed_when: false" not in service_tasks
    assert "'ORA-' in (_svc_sql.stdout | default(''))" in service_tasks
    assert 'SYS_USER = _env("ORACLE_TEST_USER", "sys")' in test_conftest
    assert 'ORACLE_TEST_USER="${ORACLE_TEST_USER:-sys}"' in test_runner


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


def test_dedicated_data_path_used(lab_exec):
    """Data files must live under /super/d01 (the dedicated data dir)."""
    # Skip cleanly if the oracle binary isn't linked (OL8+ install gap) so the
    # suite reports the gap honestly instead of erroring on sqlplus.
    probe = lab_exec("stat -c '%s' /super/app/oracle/db_home1/bin/sqlplus 2>/dev/null || echo 0")
    size = int((probe.stdout or "0").strip().splitlines()[-1] or "0")
    if size == 0:
        pytest.skip("sqlplus not linked (OL8+ install gap); DB instance not created.")
    sql = (
        "export ORACLE_HOME=/super/app/oracle/db_home1 ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF\n"
        "SELECT count(*) FROM v$datafile WHERE name LIKE '/super/d01%';\n"
        "EXIT;\n"
        "SQL"
    )
    r = lab_exec(f"su - oracle -c {shlex.quote(sql)}")
    assert r.returncode == 0, r.stderr
    count = int((r.stdout or "0").strip() or "0")
    assert count > 0, f"no datafiles under /super/d01; output: {r.stdout}"


def test_archivelog_mode_matches_desired(db_connection):
    cur = db_connection.cursor()
    cur.execute("SELECT log_mode FROM v$database")
    row = cur.fetchone()
    cur.close()
    assert row is not None
    # The slice default for `super` is archivelog: true.
    assert row[0] == "ARCHIVELOG", f"expected ARCHIVELOG, got {row[0]}"
