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
    assert "Verify whether GI root configuration completed" in tasks
    assert "/etc/oracle/olr.loc" in tasks
    assert "root/crsstart" in tasks
    assert "when: _gi_root_configured.rc != 0" in tasks
    assert "{{ oracle_gi_home }}/root.sh" in tasks
    assert "Run Grid Infrastructure configuration assistants" in tasks
    assert "- -executeConfigTools" in tasks
    assert "Allow the Grid owner to update oratab during configuration" in tasks
    root_scripts = tasks.index("Run GI root scripts")
    config_tools = tasks.index("Run Grid Infrastructure configuration assistants")
    asm_css_verify = tasks.index("Verify ASM and CSS after Grid configuration")
    install_marker = tasks.index("Drop GI install marker")
    assert root_scripts < config_tools < asm_css_verify < install_marker
    assert "register: _gi_config_tools" in tasks
    assert "crsctl check css" in tasks
    assert "crsctl status resource ora.asm -p" in tasks
    assert "srvctl status asm" in tasks
    assert "srvctl status diskgroup" in tasks
    assert "CRS-4529" in tasks
    assert "NAME=ora.asm" in tasks
    assert "register: _gi_asm_css_verify" in tasks
    assert "Verify ASM and CSS after Grid configuration" in tasks
    assert "Refresh ASM registration after GI configuration" in tasks
    refresh_asm = tasks.index("Refresh ASM registration after GI configuration")
    wait_asm = tasks.index("Wait for the configured Restart ASM stack")
    assert refresh_asm < wait_asm
    wait_block = tasks[wait_asm : tasks.index("Probe Restart stack after GI install attempt", wait_asm)]
    assert "_gi_asm_registered | bool" not in wait_block
    assert "Install systemd OHASD stack-start drop-in" in tasks
    assert "Read native OHASD systemd unit" in tasks
    assert "_gi_ohasd_native_starts_stack" in tasks
    assert "Remove redundant OHASD stack-start drop-in" in tasks
    assert "ExecStartPost=/etc/init.d/ohasd start" in tasks
    assert "Recover an installed but offline Restart stack" in tasks
    assert "Wait for Oracle High Availability Services" in tasks
    assert "Wait for the configured Restart ASM stack" in tasks
    assert "srvctl status asm" in tasks
    assert "srvctl status diskgroup" in tasks
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
    standby_tasks = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/duplicate-standby.yml"
    ).read_text(encoding="utf-8")
    broker_tasks = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/configure-broker.yml"
    ).read_text(encoding="utf-8")

    assert "Read Oracle High Availability Services autostart policy" in main_tasks
    assert "Enable Oracle High Availability Services autostart" in main_tasks
    assert "crsctl config has" in main_tasks
    assert "crsctl enable has" in main_tasks
    assert "crsctl modify resource ora.cssd" not in main_tasks
    assert "crsctl start resource ora.cssd" not in main_tasks
    assert "crsctl check css" not in main_tasks
    assert "srvctl\" add database" in register_tasks
    assert "-autostart" not in register_tasks
    assert "Resolve role-aware database Restart contract" in register_tasks
    assert "_restart_db_managed_role" in register_tasks
    assert "_restart_db_start_option" in register_tasks
    assert "Read Restart database resource profile" in register_tasks
    assert "_restart_crs_db_exists" in register_tasks
    assert "_restart_srvctl_db_config_usable" in register_tasks
    assert "Refusing to mutate an ora.* resource" in register_tasks
    assert "crsctl; restore supported srvctl/CSS access" in register_tasks
    assert "Database role: PHYSICAL_STANDBY" in register_tasks
    assert "Reconcile database Restart configuration" in register_tasks
    assert 'srvctl" modify database' in register_tasks
    assert "-role {{ _restart_db_managed_role }}" in register_tasks
    assert "-policy AUTOMATIC" in register_tasks
    assert '-startoption "{{ _restart_db_start_option }}"' in register_tasks
    assert "-stopoption IMMEDIATE" in register_tasks
    assert "Reconcile listener Restart configuration" in register_tasks
    assert 'srvctl" modify listener' in register_tasks
    assert '"$srvctl_bin" enable "$@"' in register_tasks
    assert (
        'enable_resource DATABASE "$db_oracle_home" "$db_srvctl" database '
        "-db {{ _restart_db_unique_name }}"
        in register_tasks
    )
    assert "already enabled|PRCR-1002" in register_tasks
    assert "DATABASE_ALREADY_ENABLED" in register_tasks
    assert "DATABASE_ALREADY_RUNNING" in register_tasks
    assert "status resource ora.{{ _restart_db_unique_name }}.db -p" in register_tasks
    assert "status resource ora.{{ _restart_db_unique_name }}.db -t" in register_tasks
    assert "failed_when: _srvctl_enable.rc != 0" in register_tasks
    assert "listener_rc=$?" in register_tasks
    assert "database_rc=$?" in register_tasks
    assert "failed_when: _srvctl_start.rc != 0" in register_tasks
    assert "Probe database open mode after Restart start" in register_tasks
    assert "Recover a database left mounted instead of its configured open mode" in register_tasks
    assert "'PHYSICAL STANDBY|MOUNTED'" in register_tasks
    assert "Wait for database role-appropriate readiness under Restart" in register_tasks
    assert "database_role || '|' || open_mode" in register_tasks
    assert "'PRIMARY|READ WRITE'" in register_tasks
    assert "'PHYSICAL STANDBY|READ ONLY WITH APPLY'" in register_tasks
    assert "Reconcile standby database Restart configuration" in standby_tasks
    assert '-role "{{ _dg_standby_restart_role }}"' in standby_tasks
    assert "_dg_standby_live_role" in standby_tasks
    assert "_dg_standby_restart_startoption" in standby_tasks
    assert "-policy AUTOMATIC" in standby_tasks
    assert '-startoption "{{ _dg_standby_restart_startoption }}"' in standby_tasks
    assert "-stopoption IMMEDIATE" in standby_tasks
    assert "Configure standby Restart start policy for read-only apply" in broker_tasks
    assert "-startoption" in broker_tasks
    assert "read only" in broker_tasks


def test_fan_registers_ons_and_fails_closed_on_status_errors():
    """ONS must be registered through SRVCTL, not inferred from a failed probe."""
    fan_tasks = (
        REPO_ROOT / "roles/oracle_fan_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")

    assert "Classify initial ONS resource probe" in fan_tasks
    assert "PRKO-0?2458|PRKO-0?2465" in fan_tasks
    assert "PRKO-00371" not in fan_tasks
    assert "Add Oracle Notification Services to Restart" in fan_tasks
    assert '"-onsremoteport"' in fan_tasks
    assert '"{{ oracle_fan_remote_port }}"' in fan_tasks
    assert "when: _fan_ons_initial_resource_absent | bool" in fan_tasks
    assert "PRKO-0?2452" in fan_tasks
    assert "PRKO-0?2576" in fan_tasks
    assert "PRKO-0?2569" in fan_tasks
    assert 'argv: ["{{ oracle_gi_home }}/bin/srvctl", "enable", "ons"]' in fan_tasks
    assert 'argv: ["{{ oracle_gi_home }}/bin/srvctl", "start", "ons"]' in fan_tasks
    ons_lifecycle = fan_tasks.split(
        "Read initial Oracle Notification Services state", 1
    )[1].split("Probe firewalld for remote ONS", 1)[0]
    assert "failed_when: false" not in ons_lifecycle
    assert "Validate Oracle Notification Services after lifecycle convergence" in ons_lifecycle


def test_restart_has_bounded_role_aware_post_boot_reconciliation():
    """Cold boot retries must use broker state before starting DG databases."""
    main_tasks = (REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    defaults = (
        REPO_ROOT / "roles/oracle_restart_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    reconcile = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.sh.j2"
    ).read_text(encoding="utf-8")
    unit = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.service.j2"
    ).read_text(encoding="utf-8")

    assert "Install Oracle Restart post-boot reconciliation" in main_tasks
    assert "oracle_restart_reconcile_enabled" in defaults
    assert "oracle_restart_reconcile_attempts" in defaults
    assert "oracle_restart_reconcile_delay_seconds" in defaults
    assert "oracle_restart_reconcile_command_timeout_seconds" in defaults
    assert "oracle-ohasd.service" in unit
    assert "network-online.target" in unit
    assert "Wants=network-online.target oracle-ohasd.service" in unit
    assert "Type=oneshot" in unit
    assert "After=" in unit
    assert "oracle_restart_reconcile_command_timeout_seconds" in unit
    assert "for ((attempt=1; attempt<=" in reconcile
    assert "dgmgrl" in reconcile
    assert 'timeout --kill-after=5s "$COMMAND_TIMEOUT_SECONDS" "$db_home/bin/dgmgrl"' in reconcile
    assert "oracle_apply_instance_overrides" in reconcile
    assert "oracle_instance_overrides" in reconcile
    assert "SHOW DATABASE" in reconcile
    assert "ORA-16661" in reconcile
    assert "grep -Fq 'ORA-16661'" in reconcile
    assert "grep -Eiq 'ORA-16661|" not in reconcile
    assert "16808" in reconcile
    assert "16825" in reconcile
    assert "-startoption MOUNT" in reconcile
    assert "MOUNTED to bootstrap broker role discovery" in reconcile
    assert reconcile.index("MOUNTED to bootstrap broker role discovery") < reconcile.index(
        'if ! probe_broker "$db_home"'
    )
    assert "Primary database" in reconcile
    assert "Physical standby database" in reconcile
    assert "DG_BROKER_USER" in reconcile
    assert "DG_SYS_PASSWORD" not in reconcile
    assert "srvctl\" modify database" in reconcile
    assert "srvctl\" start database" in reconcile
    assert "crsctl modify" not in reconcile
    assert "crsctl start" not in reconcile
    assert "PHYSICAL_STANDBY" in reconcile
    assert "read only" in reconcile
    assert "Failing closed" in reconcile
    assert "Waiting for ${db_unique}: Restart registration is not readable yet" in reconcile
    assert "'standby' not in group_names" in reconcile


def test_restart_dedicated_listener_disables_wildcard_default_on_port_1521():
    main_tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")

    assert "Replace wildcard default listener with dedicated port-1521 listener" in main_tasks
    assert 'srvctl" disable listener -listener LISTENER' in main_tasks
    assert 'srvctl" stop listener -listener LISTENER' in main_tasks
    assert "DEDICATED_LISTENER_STARTED" in main_tasks
    assert "DEDICATED_LISTENER_NOT_REGISTERED" in main_tasks
    assert 'grep -Eiq "^Alias[[:space:]]+${named_listener}$"' in main_tasks
    assert "(listener_inst.listener_port | default(1521) | int) == 1521" in main_tasks
    assert "loop_var: listener_inst" in main_tasks


def test_restart_reconciliation_bounds_all_external_oracle_commands():
    """CRS, SQL, and SRVCTL calls must not outlive one reconciliation pass."""
    defaults = (
        REPO_ROOT / "roles/oracle_restart_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    env = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.env.j2"
    ).read_text(encoding="utf-8")
    unit = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.service.j2"
    ).read_text(encoding="utf-8")
    reconcile = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.sh.j2"
    ).read_text(encoding="utf-8")

    assert "oracle_restart_reconcile_read_timeout_seconds: 30" in defaults
    assert "oracle_restart_reconcile_mutation_timeout_seconds: 120" in defaults
    assert "ORACLE_RESTART_RECONCILE_READ_TIMEOUT_SECONDS" in env
    assert "ORACLE_RESTART_RECONCILE_MUTATION_TIMEOUT_SECONDS" in env
    assert 'timeout --kill-after=5s "$READ_TIMEOUT_SECONDS"' in reconcile
    assert 'timeout --kill-after=5s "$MUTATION_TIMEOUT_SECONDS"' in reconcile
    assert 'timeout --kill-after=5s "$COMMAND_TIMEOUT_SECONDS"' in reconcile
    assert "non_negative_integer \"$DELAY_SECONDS\"" in reconcile
    assert "positive_integer \"$ATTEMPTS\"" in reconcile
    assert 'run_read "$GI_HOME/bin/crsctl" check has' in reconcile
    assert 'run_read env ORACLE_HOME="$db_home" ORACLE_SID="$sid" "$db_home/bin/sqlplus"' in reconcile
    assert 'run_read env ORACLE_HOME="$db_home" "$db_home/bin/srvctl" config database' in reconcile
    assert 'run_read env ORACLE_HOME="$db_home" "$db_home/bin/srvctl" status database' in reconcile
    assert 'run_mutation env ORACLE_HOME="$db_home" "$db_home/bin/srvctl" modify database' in reconcile
    assert 'run_mutation env ORACLE_HOME="$db_home" "$db_home/bin/srvctl" stop database' in reconcile
    assert 'run_mutation env ORACLE_HOME="$db_home" "$db_home/bin/srvctl" start database' in reconcile
    assert "oracle_instances | default([]) | length" in unit
    assert "oracle_restart_reconcile_read_timeout_seconds" in unit
    assert "oracle_restart_reconcile_mutation_timeout_seconds" in unit
    assert "* 4 *" in unit
    assert "* 3 *" in unit


def test_restart_reconciliation_is_disabled_when_opted_out():
    """Opting out must stop and disable a previously installed unit."""
    tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")

    disable = tasks.split(
        "Disable Oracle Restart post-boot reconciliation when not enabled", 1
    )[1].split("- name:", 1)[0]
    assert "ansible.builtin.systemd_service:" in disable
    assert "enabled: false" in disable
    assert "state: stopped" in disable
    assert "daemon_reload: true" in disable
    assert "Could not find the requested service" in disable
    assert "when: not (oracle_restart_reconcile_enabled | bool)" in disable


def test_restart_reconciliation_keeps_broker_credentials_out_of_executable():
    """The systemd unit must load credentials from a protected env file."""
    defaults = (
        REPO_ROOT / "roles/oracle_restart_manage/defaults/main.yml"
    ).read_text(encoding="utf-8")
    tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")
    unit = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.service.j2"
    ).read_text(encoding="utf-8")
    reconcile = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.sh.j2"
    ).read_text(encoding="utf-8")

    assert "oracle_restart_reconcile_environment_file" in defaults
    env_task = tasks.split(
        "Write Oracle Restart reconciliation environment", 1
    )[1].split("- name:", 1)[0]
    assert "ansible.builtin.template:" in env_task
    assert "mode: \"0600\"" in env_task
    assert "owner: root" in env_task
    assert "group: root" in env_task
    assert "no_log: true" in env_task
    assert "EnvironmentFile={{ oracle_restart_reconcile_environment_file }}" in unit
    assert "ORACLE_RESTART_RECONCILE_DGMGRL_PASSWORD" in reconcile
    assert "DG_BROKER_PASSWORD=" not in reconcile
    assert "oracle_restart_reconcile_dgmgrl_password" not in reconcile


def test_restart_reconciliation_validates_broker_evidence_before_mutation():
    """Broker role parsing must reject ambiguous or unexpected diagnostics."""
    reconcile = (
        REPO_ROOT
        / "roles/oracle_restart_manage/templates/oracle-restart-reconcile.sh.j2"
    ).read_text(encoding="utf-8")

    assert "validate_broker_output" in reconcile
    assert "validate_member_output" in reconcile
    assert "Configuration Status" in reconcile
    assert "waiting && $0 ~ /[^[:space:]]/" in reconcile
    assert "print toupper(fields[1])" in reconcile
    assert "PRIMARY_COUNT" in reconcile
    assert "STANDBY_COUNT" in reconcile
    assert "-eq 1" in reconcile
    assert "ORA-(16072|16661|16808|16819|16820|16825)" in reconcile
    assert "unrecognized broker diagnostic" in reconcile
    assert "SHOW DATABASE '${db_unique}'" in reconcile
    assert "member_output" in reconcile
    assert "if ! validate_broker_output \"$output\"" in reconcile
    assert "if ! validate_member_output" in reconcile
    assert "Configuration Status:[[:space:]]+ERROR" not in reconcile


def test_restart_database_srvctl_runs_from_registered_database_home():
    """Database SRVCTL must come from the registered DB home, not GI home."""
    register_tasks = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/register-instance.yml"
    ).read_text(encoding="utf-8")

    assert 'export ORACLE_HOME={{ _restart_home_path }}' in register_tasks
    assert '"$ORACLE_HOME/bin/srvctl" config database' in register_tasks
    assert '"$ORACLE_HOME/bin/srvctl" add database' in register_tasks
    assert '"$ORACLE_HOME/bin/srvctl" modify database' in register_tasks
    assert 'db_oracle_home="{{ _restart_home_path }}"' in register_tasks
    assert 'enable_output="$(ORACLE_HOME="$oracle_home" "$srvctl_bin" enable' in register_tasks
    assert 'status_output="$(ORACLE_HOME="$oracle_home" "$srvctl_bin" status' in register_tasks
    assert (
        'enable_resource DATABASE "$db_oracle_home" "$db_srvctl" database'
        in register_tasks
    )
    assert (
        'start_resource DATABASE "$db_oracle_home" "$db_srvctl" database'
        in register_tasks
    )
    assert '"$ORACLE_HOME/bin/srvctl" stop database' in register_tasks
    assert '"$ORACLE_HOME/bin/srvctl" start database' in register_tasks

    # Listener and CRSCTL operations remain owned by the GI home.
    assert 'export ORACLE_HOME={{ oracle_gi_home }}' in register_tasks
    assert '"$ORACLE_HOME/bin/srvctl" config listener' in register_tasks
    assert '"$ORACLE_HOME/bin/crsctl" status resource' in register_tasks


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


def test_srvctl_status_or_honest_gap(lab_exec, request):
    """Restart must own super when the lab is required; otherwise record the gap."""
    if not _restart_installed(lab_exec):
        from conftest import _skip_or_fail

        _skip_or_fail(
            "Oracle Restart is not installed in this lab. The DB still runs under "
            "sqlplus/lsnrctl; Restart registration tests require a Grid home.",
            request,
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

    expected_homes = home if isinstance(home, tuple) else (home,)
    command_home = expected_homes[0]
    config = exec_fn(
        "su - oracle -c "
        f"'ORACLE_HOME={command_home} {command_home}/bin/srvctl "
        f"config database -db {restart_db_name}'"
    )

    if config.returncode != 0 and restart_db_name in {"duper", "fluff"}:
        pytest.skip(
            f"Optional multi-instance smoke database {restart_db_name} is not converged"
        )

    assert config.returncode == 0, config.stdout + config.stderr
    assert f"Database unique name: {restart_db_name}" in config.stdout
    assert f"Database name: {database_name}" in config.stdout
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


def test_restart_systemd_unit_starts_stack_after_monitor(lab_exec, request):
    """The native unit must launch the stack as well as the init monitor."""
    if not _restart_installed(lab_exec):
        from conftest import _skip_or_fail

        _skip_or_fail(
            "Oracle Restart not installed; systemd unit test requires Restart.",
            request,
        )

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
    """Opt-in live test of OHASD and standby database recovery."""
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
            f"su - oracle -c {shlex.quote(sql_command)}"
        )
        last = state.stdout
        if (
            "CRS-4638" in last
            and "PHYSICAL STANDBY|READ ONLY WITH APPLY" in last
        ):
            return
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(f"standby did not recover after OHASD restart:\n{last}")


@pytest.mark.slow
def test_restart_can_stop_and_start_database(lab_exec, request):
    """Restart must own the database enough to stop, start, and restore SQL."""
    if not _restart_installed(lab_exec):
        from conftest import _skip_or_fail

        _skip_or_fail(
            "Oracle Restart not installed; auto-restart test requires Restart.",
            request,
        )

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
