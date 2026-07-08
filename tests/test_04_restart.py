"""
test_04_restart.py — Oracle Restart assertions for the slice.

This is the Restart ownership test: if Oracle Restart is installed and owns
the `super` database, we stop and start it through srvctl and assert SQL
readiness returns. If Restart is NOT installed, the test reports that
explicitly and skips the Restart assertions — it never fakes a pass.

Either way, we first assert that `super` is registered with Restart (or that
Restart is absent and the gap is honestly recorded).
"""
from __future__ import annotations

import shlex
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slice

RESTART_BRINGUP_WINDOW_S = 180
POLL_INTERVAL_S = 5
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gi_install_role_has_oracle_restart_install_path():
    defaults = (REPO_ROOT / "roles/oracle_gi_install/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_gi_install/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    response = (
        REPO_ROOT / "roles/oracle_gi_install/templates/gridsetup.rsp.j2"
    ).read_text(encoding="utf-8")

    assert "oracle_gi_install_enabled: false" in defaults
    assert "oracle_asm_group: asmadmin" in defaults
    assert "oracle_gi_asm_diskgroup_name: RESTART" in defaults
    assert "oracle_gi_asm_disk_discovery_string: /dev/vdb" in defaults
    assert "oracle_gi_install_recreate_incomplete_home: true" in defaults
    assert "oracle_gi_install_min_free_mb" in defaults
    assert "Probe existing Restart stack before install" in tasks
    assert "Verify Grid ASM disk exists for Oracle Restart" in tasks
    assert "Remove incomplete GI home left by a failed installer run" in tasks
    assert "Unzip Grid Infrastructure image into GI home" in tasks
    assert "Upgrade GI OPatch" in tasks
    assert "Resolve extracted GI RU directory for gridSetup -applyRU" in tasks
    assert "./gridSetup.sh -silent -force -waitforcompletion" in tasks
    assert "-applyRU {{ _gi_ru_apply_dir.stdout | trim | quote }}" in tasks
    assert "{{ oracle_gi_home }}/root.sh" in tasks
    assert "oracle.install.option=HA_CONFIG" in response
    assert "oracle.install.crs.config.storageOption=FLEX_ASM_STORAGE" in response
    assert "oracle.install.asm.diskGroup.disks={{ oracle_gi_asm_disks }}" in response
    assert "oracle.install.crs.rootconfig.executeRootScript=false" in response


def test_restart_registration_uses_supported_srvctl_syntax():
    main_tasks = (REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    register_tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/register-instance.yml"
    ).read_text(encoding="utf-8")

    assert "Start local CSS before srvctl database operations" in main_tasks
    assert "crsctl start resource ora.cssd -init" in main_tasks
    assert "srvctl\" add database" in register_tasks
    assert "-autostart" not in register_tasks
    assert 'srvctl" enable "$@"' in register_tasks
    assert "enable_resource DATABASE database -d {{ inst.name }}" in register_tasks
    assert "already enabled|PRCR-1002" in register_tasks
    assert "failed_when: _srvctl_enable.rc != 0" in register_tasks
    assert "listener_rc=$?" in register_tasks
    assert "database_rc=$?" in register_tasks
    assert "failed_when: _srvctl_start.rc != 0" in register_tasks


def _restart_installed(lab_exec) -> bool:
    """True if srvctl exists AND ohasd reports healthy."""
    r = lab_exec(
        "test -x /grid/19c/gi_home1/bin/srvctl && "
        "/grid/19c/gi_home1/bin/crsctl check has 2>&1 | grep -q 'CRS-4638' && echo YES || echo NO"
    )
    return "YES" in r.stdout


def _sqlplus_sysdba(lab_exec, sql: str):
    command = (
        "export ORACLE_HOME=/super/app/oracle/db_home1 ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF\n"
        f"{sql}\n"
        "EXIT;\n"
        "SQL"
    )
    return lab_exec(f"su - oracle -c {shlex.quote(command)}", timeout=30)


def _db_accepts_local_sql(lab_exec) -> bool:
    r = _sqlplus_sysdba(lab_exec, "SELECT status FROM v$instance;")
    output = r.stdout or ""
    return r.returncode == 0 and "ORA-" not in output and "OPEN" in output


def _ensure_restart_database_running(lab_exec):
    start = lab_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl start database -d super 2>&1"
    )
    ok_messages = (
        "already running",
        "CRS-5702",
        "Database is running",
        "PRCC-1014",
    )
    assert start.returncode == 0 or any(
        msg in start.stdout for msg in ok_messages
    ), start.stdout

    deadline = time.time() + RESTART_BRINGUP_WINDOW_S
    last_status = ""
    while time.time() < deadline:
        status = lab_exec(
            "export ORACLE_HOME=/grid/19c/gi_home1 && "
            "$ORACLE_HOME/bin/srvctl status database -d super"
        )
        last_status = status.stdout
        if "is running" in status.stdout and _db_accepts_local_sql(lab_exec):
            return
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(f"super did not become SQL-ready under Restart: {last_status}")


def _ensure_restart_service_running(lab_exec):
    start = lab_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl start service -db super -service super_svc 2>&1"
    )
    ok_messages = ("already running", "CRS-5702", "PRCC-1014")
    assert start.returncode == 0 or any(
        msg in start.stdout for msg in ok_messages
    ), start.stdout


def test_srvctl_status_or_honest_gap(lab_exec):
    """Either srvctl reports super ONLINE, or we honestly record Restart absent."""
    if not _restart_installed(lab_exec):
        pytest.skip(
            "Oracle Restart is not installed (Grid install is scaffolded in this "
            "slice). The DB still runs under sqlplus/lsnrctl; Restart registration "
            "will be asserted once oracle_gi_install is implemented."
        )

    _ensure_restart_database_running(lab_exec)


@pytest.mark.slow
def test_restart_can_stop_and_start_database(lab_exec):
    """Restart must own the database enough to stop, start, and restore SQL."""
    if not _restart_installed(lab_exec):
        pytest.skip("Oracle Restart not installed; skipping auto-restart test.")

    _ensure_restart_database_running(lab_exec)

    stop = lab_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl stop database -d super -stopoption abort 2>&1"
    )
    assert stop.returncode == 0, f"could not stop database through Restart: {stop.stdout}"

    _ensure_restart_database_running(lab_exec)
    _ensure_restart_service_running(lab_exec)
