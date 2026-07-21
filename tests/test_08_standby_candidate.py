"""
test_08_standby_candidate.py - standby VM readiness for the Data Guard slice.

These checks prove the second DB VM has the substrate and role required for the
Data Guard slice: Oracle Restart, the DB home, the dedicated Grid disk, and no
accidental standalone/open primary database.
"""
from __future__ import annotations

import shlex

import pytest

pytestmark = pytest.mark.slice


def _standby_home(standby_exec) -> str:
    r = standby_exec(
        "su - oracle -c "
        + shlex.quote(
            "/grid/19c/gi_home1/bin/srvctl config database -db super_sby | "
            "sed -n 's/^Oracle home: //p'"
        )
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().splitlines()[-1]
    return "/super/app/oracle/db_home1"


def test_standby_candidate_has_restart_online(standby_exec):
    r = standby_exec(
        "test -x /grid/19c/gi_home1/bin/crsctl && "
        "/grid/19c/gi_home1/bin/crsctl check has"
    )
    assert r.returncode == 0, r.stderr
    assert "CRS-4638" in r.stdout


def test_standby_candidate_has_database_home(standby_exec):
    oracle_home = _standby_home(standby_exec)
    runinstaller = standby_exec(f"test -x {oracle_home}/runInstaller")
    assert runinstaller.returncode == 0, runinstaller.stderr

    opatch = standby_exec(f"{oracle_home}/OPatch/opatch version")
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
        oracle_home = _standby_home(standby_exec)
        sql = (
            f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
            "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
            "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
            "SELECT status FROM v$instance;\n"
            "SELECT database_role || '|' || open_mode FROM v$database;\n"
            "EXIT;\n"
            "SQL"
        )
        state = standby_exec(f"su - oracle -c {shlex.quote(sql)}")
        assert state.returncode == 0, state.stderr
        if "ORA-01507" in state.stdout:
            assert "STARTED" in state.stdout
        else:
            assert "PHYSICAL STANDBY" in state.stdout

    oratab = standby_exec(
        "awk -F'#' '/^super:/ {gsub(/[[:space:]]+$/, \"\", $1); print $1}' "
        "/etc/oratab 2>/dev/null || true"
    )
    assert oratab.stdout.strip() in (
        "",
        "super:/super/app/oracle/db_home1:N",
        "super:/super/app/oracle/db_home2:N",
    )
