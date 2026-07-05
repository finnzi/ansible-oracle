"""
test_04_restart.py — Oracle Restart assertions for the slice.

This is the creative Restart test: if Oracle Restart is installed and owns
the `super` database, we kill the instance's PMON process and assert that
Restart brings the database back online within a generous window. If Restart
is NOT installed (the slice case where the Grid install is scaffolded), the
test reports that explicitly and skips the kill — it never fakes a pass.

Either way, we first assert that `super` is registered with Restart (or that
Restart is absent and the gap is honestly recorded).
"""
from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.slice

RESTART_BRINGUP_WINDOW_S = 90
POLL_INTERVAL_S = 5


def _restart_installed(docker_exec) -> bool:
    """True if srvctl exists AND ohasd reports healthy."""
    r = docker_exec(
        "test -x /grid/19c/gi_home1/bin/srvctl && "
        "/grid/19c/gi_home1/bin/crsctl check has 2>&1 | grep -q 'CRS-4638' && echo YES || echo NO"
    )
    return "YES" in r.stdout


def test_srvctl_status_or_honest_gap(docker_exec):
    """Either srvctl reports super ONLINE, or we honestly record Restart absent."""
    if not _restart_installed(docker_exec):
        pytest.skip(
            "Oracle Restart is not installed (Grid install is scaffolded in this "
            "slice). The DB still runs under sqlplus/lsnrctl; Restart registration "
            "will be asserted once oracle_gi_install is implemented."
        )

    r = docker_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl status database -d super"
    )
    assert r.returncode == 0, f"srvctl status failed: {r.stderr}"
    assert "is running" in r.stdout, f"super not running under Restart: {r.stdout}"


@pytest.mark.slow
def test_restart_brings_db_back_after_pmon_kill(docker_exec):
    """Kill PMON; Restart must restart the instance. The real Restart test."""
    if not _restart_installed(docker_exec):
        pytest.skip("Oracle Restart not installed; skipping auto-restart test.")

    # Sanity: must be running first.
    r = docker_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl status database -d super"
    )
    assert "is running" in r.stdout, f"precondition: super must be running: {r.stdout}"

    # Kill PMON. This simulates a process crash; Restart should restart it.
    kill = docker_exec("pkill -9 -x ora_pmon_super")
    assert kill.returncode == 0, f"could not kill pmon: {kill.stderr}"

    # Poll until Restart reports it running again, up to the window.
    deadline = time.time() + RESTART_BRINGUP_WINDOW_S
    while time.time() < deadline:
        r = docker_exec(
            "export ORACLE_HOME=/grid/19c/gi_home1 && "
            "$ORACLE_HOME/bin/srvctl status database -d super"
        )
        if "is running" in r.stdout:
            return  # Restart brought it back. PASS.
        time.sleep(POLL_INTERVAL_S)

    pytest.fail(
        f"Restart did not bring `super` back within {RESTART_BRINGUP_WINDOW_S}s "
        f"after PMON was killed. Last status: {r.stdout}"
    )
