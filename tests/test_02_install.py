"""
test_02_install.py — Oracle software install assertions for the slice.

Verifies the central inventory exists, the db_home1 has a working sqlplus,
and OPatch lsinventory reports 19.3. Runs against the superdb1 container.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slice

ORACLE_HOME = "/super/app/oracle/db_home1"


def test_central_inventory_exists(docker_exec):
    r = docker_exec("test -f /etc/oraInst.loc && cat /etc/oraInst.loc")
    assert r.returncode == 0, f"oraInst.loc missing: {r.stderr}"
    assert "inventory_loc=/opt/oracle/oraInventory" in r.stdout
    assert "inst_group=oinstall" in r.stdout


def test_oracle_home_marker_present(docker_exec):
    """The idempotency marker dropped by oracle_db_install."""
    r = docker_exec(f"test -f {ORACLE_HOME}/.install_complete && echo OK")
    assert r.returncode == 0, f"install marker missing: {r.stderr}"
    assert "OK" in r.stdout


def test_sqlplus_executable_present(docker_exec):
    r = docker_exec(f"test -x {ORACLE_HOME}/bin/sqlplus && echo OK")
    assert r.returncode == 0, f"sqlplus missing: {r.stderr}"
    assert "OK" in r.stdout


def test_oracle_binary_present(docker_exec):
    r = docker_exec(f"test -x {ORACLE_HOME}/bin/oracle && echo OK")
    assert r.returncode == 0, f"oracle binary missing: {r.stderr}"
    assert "OK" in r.stdout


def test_opatch_version(docker_exec):
    r = docker_exec(
        f"export ORACLE_HOME={ORACLE_HOME} && {ORACLE_HOME}/OPatch/opatch version"
    )
    assert r.returncode == 0, f"opatch version failed: {r.stderr}"
    # OPatch 12.2.x ships with 19c; just assert it printed a version line.
    assert "OPatch Version" in (r.stdout + r.stderr)


@pytest.mark.slow
def test_opatch_lsinventory_reports_193(docker_exec):
    """opatch lsinventory can take a while; hence slow marker."""
    r = docker_exec(
        f"export ORACLE_HOME={ORACLE_HOME} && {ORACLE_HOME}/OPatch/opatch lsinventory",
        timeout=180,
    )
    assert r.returncode == 0, f"opatch lsinventory failed: {r.stderr}"
    combined = r.stdout + r.stderr
    assert "19.3" in combined, f"expected 19.3 in lsinventory: {combined}"
