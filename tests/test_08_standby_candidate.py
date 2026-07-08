"""
test_08_standby_candidate.py - standby VM readiness for the Data Guard slice.

These checks do not assert a completed Data Guard configuration yet. They prove
the second DB VM has the substrate required before RMAN duplicate and broker
setup: Oracle Restart, the DB home, the dedicated Grid disk, and no accidental
standalone/open database.
"""
from __future__ import annotations

import shlex

import pytest

pytestmark = pytest.mark.slice


def test_standby_candidate_has_restart_online(standby_exec):
    r = standby_exec(
        "test -x /grid/19c/gi_home1/bin/crsctl && "
        "/grid/19c/gi_home1/bin/crsctl check has"
    )
    assert r.returncode == 0, r.stderr
    assert "CRS-4638" in r.stdout


def test_standby_candidate_has_database_home(standby_exec):
    runinstaller = standby_exec("test -x /super/app/oracle/db_home1/runInstaller")
    assert runinstaller.returncode == 0, runinstaller.stderr

    opatch = standby_exec("/super/app/oracle/db_home1/OPatch/opatch version")
    assert opatch.returncode == 0, opatch.stderr
    assert "OPatch Version" in (opatch.stdout + opatch.stderr)


def test_standby_candidate_grid_disk_is_owned_for_asm(standby_exec):
    r = standby_exec("stat -c '%U:%G %a %n' /dev/vdb")
    assert r.returncode == 0, r.stderr
    assert "oracle:asmadmin" in r.stdout
    assert "660" in r.stdout


def test_standby_candidate_has_no_standalone_database(standby_exec):
    pmon = standby_exec("pgrep -x ora_pmon_super")
    if pmon.returncode == 0:
        sql = (
            "export ORACLE_HOME=/super/app/oracle/db_home1 ORACLE_SID=super && "
            "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
            "SET PAGES 0 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
            "SELECT status FROM v$instance;\n"
            "EXIT;\n"
            "SQL"
        )
        state = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
        assert state.returncode == 0, state.stderr
        assert "STARTED" in state.stdout
        assert "MOUNTED" not in state.stdout
        assert "OPEN" not in state.stdout

    oratab = standby_exec("grep -E '^super:' /etc/oratab 2>/dev/null || true")
    assert oratab.stdout.strip() in ("", "super:/super/app/oracle/db_home1:N")
