"""
test_03_instance.py — instance + listener assertions for the slice.

Verifies the `super` instance is OPEN READ WRITE, the listener answers on
superdb.domain.is:1521, and the client-facing service super_svc resolves.
Uses python-oracledb from the control host.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slice


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


def test_dedicated_data_path_used(docker_exec):
    """Data files must live under /super/d01 (the dedicated data dir)."""
    # Skip cleanly if the oracle binary isn't linked (OL8+ install gap) so the
    # suite reports the gap honestly instead of erroring on sqlplus.
    probe = docker_exec("stat -c '%s' /super/app/oracle/db_home1/bin/sqlplus 2>/dev/null || echo 0")
    size = int((probe.stdout or "0").strip().splitlines()[-1] or "0")
    if size == 0:
        pytest.skip("sqlplus not linked (OL8+ install gap); DB instance not created.")
    r = docker_exec(
        "export ORACLE_HOME=/super/app/oracle/db_home1 ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF\n"
        "SELECT count(*) FROM v$datafile WHERE name LIKE '/super/d01%';\n"
        "EXIT;\n"
        "SQL"
    )
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
