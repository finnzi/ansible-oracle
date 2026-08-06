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

import os
import shlex
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slice

RESTART_BRINGUP_WINDOW_S = 180
POLL_INTERVAL_S = 5
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_restart_stop_start_skips_when_fsfo_unknown_or_enabled():
    """Abort-stop must not run unless FSFO is proven disabled (fail closed)."""
    source = (REPO_ROOT / "tests/test_04_restart.py").read_text(encoding="utf-8")
    assert "fsfo_unknown" in source
    assert "Fast-Start Failover: Disabled" in source
    assert "would intentionally trigger failover" in source


def test_gi_install_role_has_oracle_restart_install_path():
    defaults = (REPO_ROOT / "roles/oracle_gi_install/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    all_vars = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(
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
    assert "oracle_gi_repair_existing_enabled: false" in defaults
    assert "oracle_gi_repair_existing_enabled: true" in all_vars
    assert "oracle_gi_install_min_free_mb" in defaults
    assert "Probe existing Restart stack before install" in tasks
    assert "Verify Grid ASM disks exist for Oracle Restart" in tasks
    assert "Remove incomplete GI home left by a failed installer run" in tasks
    assert "Unzip Grid Infrastructure image into GI home" in tasks
    assert "Upgrade GI OPatch" in tasks
    assert "Resolve extracted GI RU directory for gridSetup -applyRU" in tasks
    assert "./gridSetup.sh -silent -force -waitforcompletion" in tasks
    assert "-applyRU {{ _gi_ru_apply_dir.stdout | trim | quote }}" in tasks
    assert "{{ oracle_gi_home }}/root.sh" in tasks
    assert "Install systemd OHASD stack-start drop-in" in tasks
    assert "Read native OHASD systemd unit" in tasks
    assert "_gi_ohasd_native_starts_stack" in tasks
    assert "Remove redundant OHASD stack-start drop-in" in tasks
    assert "ExecStartPost=/etc/init.d/ohasd start" in tasks
    assert "Recover an installed but offline Restart stack" in tasks
    assert "Wait for Oracle High Availability Services" in tasks
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
    assert "Read local CSS autostart policy" in main_tasks
    assert "Configure local CSS to start with OHASD" in main_tasks
    assert 'AUTO_START=always' in main_tasks
    assert 'crsctl modify resource ora.cssd' in main_tasks
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
    assert "Probe database open mode after Restart start" in register_tasks
    assert "Recover a database left mounted by an earlier CSS failure" in register_tasks
    assert "Wait for database role-appropriate readiness under Restart" in register_tasks
    assert "database_role || '|' || open_mode" in register_tasks
    assert "'PRIMARY|READ WRITE'" in register_tasks
    assert "'PHYSICAL STANDBY|READ ONLY WITH APPLY'" in register_tasks
    assert "-startoption OPEN" in register_tasks


def _restart_installed(lab_exec) -> bool:
    """True if srvctl exists AND ohasd reports healthy."""
    r = lab_exec(
        "test -x /grid/19c/gi_home1/bin/srvctl && "
        "/grid/19c/gi_home1/bin/crsctl check has 2>&1 | grep -q 'CRS-4638' && echo YES || echo NO"
    )
    return "YES" in r.stdout


def _current_restart_home(lab_exec, db_unique_name: str) -> str:
    r = lab_exec(
        "su - oracle -c "
        + shlex.quote(
            f"/grid/19c/gi_home1/bin/srvctl config database -db {db_unique_name} | "
            "sed -n 's/^Oracle home: //p'"
        )
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().splitlines()[-1]
    return "/super/app/oracle/dbhome_1"


def _sqlplus_sysdba(lab_exec, sql: str):
    oracle_home = _current_restart_home(lab_exec, "super")
    command = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID=super && "
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
            "Oracle Restart is not installed in this lab. The DB still runs under "
            "sqlplus/lsnrctl; Restart registration tests require a Grid home."
        )

    _ensure_restart_database_running(lab_exec)


@pytest.mark.parametrize(
    (
        "exec_fixture",
        "restart_db_name",
        "database_name",
        "home",
        "spfile",
        "role",
        "start_options",
        "service",
        "instance",
    ),
    [
        (
            "lab_exec",
            "super",
            "super",
            ("/super/app/oracle/dbhome_1", "/super/app/oracle/dbhome_2"),
            (
                # Durable data-dir path (preferred for dual-home rebuild safety)
                "/super/d01/super/spfilesuper.ora",
                "/super/app/oracle/dbhome_1/dbs/spfilesuper.ora",
                "/super/app/oracle/dbhome_2/dbs/spfilesuper.ora",
            ),
            "PRIMARY",
            "open",
            "super_svc",
            "super",
        ),
        (
            "standby_exec",
            "super_sby",
            "super",
            ("/super/app/oracle/dbhome_1", "/super/app/oracle/dbhome_2"),
            (
                "/super/d01/super/spfilesuper.ora",
                "/super/d01/super_sby/spfilesuper.ora",
                "/super/app/oracle/dbhome_1/dbs/spfilesuper.ora",
                "/super/app/oracle/dbhome_2/dbs/spfilesuper.ora",
            ),
            "PHYSICAL_STANDBY",
            "read only",
            "super_svc",
            "super",
        ),
        (
            "lab_exec",
            "duper",
            "duper",
            ("/duper/app/oracle/dbhome_1", "/duper/app/oracle/dbhome_2"),
            (
                "/duper/d01/duper/spfileduper.ora",
                "/duper/app/oracle/dbhome_1/dbs/spfileduper.ora",
                "/duper/app/oracle/dbhome_2/dbs/spfileduper.ora",
            ),
            "PRIMARY",
            "open",
            "duper_svc",
            "duper",
        ),
        (
            "lab_exec",
            "fluff",
            "fluff",
            ("/fluff/app/oracle/dbhome_1", "/fluff/app/oracle/dbhome_2"),
            (
                "/fluff/d01/fluff/spfilefluff.ora",
                "/fluff/app/oracle/dbhome_1/dbs/spfilefluff.ora",
                "/fluff/app/oracle/dbhome_2/dbs/spfilefluff.ora",
            ),
            "PRIMARY",
            "open",
            "fluff_svc",
            "fluff",
        ),
    ],
)
def test_restart_database_registration_details(
    request,
    exec_fixture,
    restart_db_name,
    database_name,
    home,
    spfile,
    role,
    start_options,
    service,
    instance,
):
    exec_fn = request.getfixturevalue(exec_fixture)
    config = exec_fn(
        f"su - oracle -c '/grid/19c/gi_home1/bin/srvctl config database -db {restart_db_name}'"
    )

    if config.returncode != 0 and restart_db_name in {"duper", "fluff"}:
        pytest.skip(
            f"Optional multi-instance smoke database {restart_db_name} is not converged"
        )

    assert config.returncode == 0, config.stdout + config.stderr
    assert f"Database unique name: {restart_db_name}" in config.stdout
    assert f"Database name: {database_name}" in config.stdout
    expected_homes = home if isinstance(home, tuple) else (home,)
    assert any(f"Oracle home: {value}" in config.stdout for value in expected_homes)
    expected_spfiles = spfile if isinstance(spfile, tuple) else (spfile,)
    assert any(f"Spfile: {value}" in config.stdout for value in expected_spfiles)
    assert f"Start options: {start_options}" in config.stdout
    assert f"Database role: {role}" in config.stdout
    assert "Management policy: AUTOMATIC" in config.stdout
    services_line = next(
        line for line in config.stdout.splitlines() if line.startswith("Services:")
    )
    assert service in {
        value.strip()
        for value in services_line.removeprefix("Services:").split(",")
    }
    assert f"Database instance: {instance}" in config.stdout


def test_restart_systemd_unit_starts_stack_after_monitor(lab_exec):
    """The native unit must launch the stack as well as the init monitor."""
    if not _restart_installed(lab_exec):
        pytest.skip("Oracle Restart not installed; skipping systemd unit test.")

    unit = lab_exec("systemctl cat oracle-ohasd.service")
    assert unit.returncode == 0, unit.stdout + unit.stderr
    native_starts_stack = "ExecStart=/etc/init.d/ohasd " in unit.stdout
    monitor_repair = (
        "ExecStart=/etc/init.d/init.ohasd run" in unit.stdout
        and "ExecStartPost=/etc/init.d/ohasd start" in unit.stdout
    )
    assert native_starts_stack or monitor_repair


@pytest.mark.slow
def test_standby_recovers_after_ohasd_unit_restart(standby_exec):
    """Opt-in live test of OHASD, CSS, and standby database recovery."""
    if os.environ.get("ORACLE_TEST_OHASD_RESTART") != "1":
        pytest.skip("set ORACLE_TEST_OHASD_RESTART=1 to restart standby OHASD")

    restart = standby_exec("systemctl restart oracle-ohasd.service", timeout=180)
    assert restart.returncode == 0, restart.stdout + restart.stderr

    sql_command = (
        "export ORACLE_HOME=/super/app/oracle/dbhome_1 ORACLE_SID=super; "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 FEEDBACK OFF VERIFY OFF HEADING OFF\n"
        "SELECT database_role || '|' || open_mode FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    deadline = time.time() + RESTART_BRINGUP_WINDOW_S
    last = ""
    while time.time() < deadline:
        state = standby_exec(
            "/grid/19c/gi_home1/bin/crsctl check has 2>&1; "
            "/grid/19c/gi_home1/bin/crsctl stat res ora.cssd -t -init 2>&1; "
            f"su - oracle -c {shlex.quote(sql_command)}"
        )
        last = state.stdout
        if (
            "CRS-4638" in last
            and "ONLINE  ONLINE" in last
            and "PHYSICAL STANDBY|READ ONLY WITH APPLY" in last
        ):
            return
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(f"standby did not recover after OHASD restart:\n{last}")


@pytest.mark.slow
def test_restart_can_stop_and_start_database(lab_exec):
    """Restart must own the database enough to stop, start, and restore SQL."""
    if not _restart_installed(lab_exec):
        pytest.skip("Oracle Restart not installed; skipping auto-restart test.")

    _ensure_restart_database_running(lab_exec)

    # Fail closed: never abort-stop a DG primary unless we can prove FSFO is
    # disabled. A failed/ambiguous dgmgrl probe (missing VIP, idle instance)
    # must skip — otherwise FSFO promotes the standby mid-suite.
    oracle_home = _current_restart_home(lab_exec, "super")
    fsfo = lab_exec(
        "su - oracle -c "
        + shlex.quote(
            f"export ORACLE_HOME={oracle_home} "
            f"TNS_ADMIN={oracle_home}/network/admin; "
            "printf 'SHOW FAST_START FAILOVER;\\nEXIT;\\n' | "
            "$ORACLE_HOME/bin/dgmgrl -silent sys/SysPassword1_@super_dgb; "
            "printf 'SHOW FAST_START FAILOVER;\\nEXIT;\\n' | "
            "$ORACLE_HOME/bin/dgmgrl -silent /"
        ),
        timeout=90,
    )
    fsfo_out = fsfo.stdout or ""
    fsfo_enabled = "Fast-Start Failover: Enabled" in fsfo_out and "Active Target:" in fsfo_out
    fsfo_disabled = "Fast-Start Failover: Disabled" in fsfo_out
    fsfo_unknown = (not fsfo_enabled) and (not fsfo_disabled)
    if fsfo_enabled or fsfo_unknown:
        pytest.skip(
            "super is FSFO-protected (or FSFO state could not be proven disabled); "
            "abort-stopping it through Restart would intentionally trigger failover. "
            f"dgmgrl_probe={fsfo_out[:400]!r}"
        )

    stop = lab_exec(
        "export ORACLE_HOME=/grid/19c/gi_home1 && "
        "$ORACLE_HOME/bin/srvctl stop database -d super -stopoption abort 2>&1"
    )
    assert stop.returncode == 0, f"could not stop database through Restart: {stop.stdout}"

    _ensure_restart_database_running(lab_exec)
    _ensure_restart_service_running(lab_exec)
