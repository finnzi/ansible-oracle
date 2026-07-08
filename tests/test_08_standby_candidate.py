"""
test_08_standby_candidate.py - standby VM readiness for the Data Guard slice.

These checks do not assert Data Guard itself yet. They prove the second DB VM
has the software substrate required before RMAN duplicate and broker setup:
Oracle Restart, the DB home, the dedicated Grid disk, and no accidental
standalone database.
"""
from __future__ import annotations

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
    assert pmon.returncode != 0, "super PMON should not be running on standby candidate"

    oratab = standby_exec("grep -E '^super:' /etc/oratab 2>/dev/null || true")
    assert oratab.stdout.strip() == ""
