"""Oracle DB home patch inventory and convergence assertions."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE_HOME = os.environ.get("ORACLE_TEST_ORACLE_HOME", "/super/app/oracle/db_home1")
GRID_HOME = os.environ.get("ORACLE_TEST_GRID_HOME", "/grid/19c/gi_home1")
DATAGUARD_SID = os.environ.get("ORACLE_TEST_DATAGUARD_SID", "super")
SWITCHBACK_DB = os.environ.get("ORACLE_TEST_SWITCHBACK_DB", "fluff")
SWITCHBACK_SID = os.environ.get("ORACLE_TEST_SWITCHBACK_SID", SWITCHBACK_DB)
SWITCHBACK_ORIGINAL_HOME = os.environ.get(
    "ORACLE_TEST_SWITCHBACK_ORIGINAL_HOME",
    f"/{SWITCHBACK_DB}/app/oracle/db_home1",
)
SWITCHBACK_TARGET_HOME = os.environ.get(
    "ORACLE_TEST_SWITCHBACK_TARGET_HOME",
    f"/{SWITCHBACK_DB}/app/oracle/db_home2",
)
SWITCHBACK_LISTENER = os.environ.get(
    "ORACLE_TEST_SWITCHBACK_LISTENER",
    f"LISTENER_{SWITCHBACK_DB.upper()}",
)
SWITCHBACK_SERVICE = os.environ.get(
    "ORACLE_TEST_SWITCHBACK_SERVICE",
    f"{SWITCHBACK_DB}_svc",
)
EXPECTED_DB_RU = os.environ.get("ORACLE_TEST_DB_RU_PATCH_ID", "39034528")
EXPECTED_GI_PATCH_IDS = [
    p
    for p in os.environ.get(
        "ORACLE_TEST_GI_PATCH_IDS",
        "39034528,39039430,39055473,39107825,39107855",
    ).split(",")
    if p
]

pytestmark = pytest.mark.slice


def _ansible_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    env.setdefault("ANSIBLE_SSH_CONTROL_PATH_DIR", "/tmp/ansible-cp")
    env.setdefault("XDG_CACHE_HOME", "/tmp/ansible-cache")
    return env


def test_patch_role_db_apply_contract():
    defaults = (REPO_ROOT / "roles/oracle_patch/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_patch/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    playbook = (REPO_ROOT / "playbooks/07-patch.yml").read_text(encoding="utf-8")
    grid_playbook = (REPO_ROOT / "playbooks/07-patch-grid.yml").read_text(
        encoding="utf-8"
    )
    dual_playbook = (REPO_ROOT / "playbooks/07-patch-dual-db.yml").read_text(
        encoding="utf-8"
    )
    dual_switchback_playbook = (
        REPO_ROOT / "playbooks/07-patch-dual-db-switchback.yml"
    ).read_text(encoding="utf-8")
    standbyfirst_playbook = (
        REPO_ROOT / "playbooks/07-patch-standbyfirst.yml"
    ).read_text(encoding="utf-8")
    standbyfirst_media_playbook = (
        REPO_ROOT / "playbooks/07-patch-standbyfirst-media.yml"
    ).read_text(encoding="utf-8")

    assert "oracle_patch_apply_enabled: false" in defaults
    assert "oracle_patch_expected_patch_ids: []" in defaults
    assert "oracle_patch_expected_grid_patch_ids: []" in defaults
    assert "oracle_patch_target: db" in defaults
    assert "oracle_patch_mode: inplace" in defaults
    assert "oracle_patch_apply_component_path: \"\"" in defaults
    assert "oracle_patch_discover_oratab: true" in defaults
    assert "oracle_patch_extra_homes: []" in defaults
    assert "oracle_patch_discover_olr: true" in defaults
    assert "oracle_patch_extra_grid_homes: []" in defaults
    assert "oracle_patch_dual_home_suffix: \"\"" in defaults
    assert "oracle_patch_dual_home_path: \"\"" in defaults
    assert "oracle_patch_allow_dataguard_dual_home_switch: false" in defaults
    assert "oracle_patch_run_datapatch: true" in defaults
    assert "oracle_patch_standbyfirst_require_eligible: true" in defaults
    assert "oracle_patch_dual_home_restart" not in defaults
    assert "Fail when patch target is invalid" in tasks
    assert "Fail when patch mode is invalid" in tasks
    assert "Fail when dual-home mode is requested for Grid homes" in tasks
    assert "Resolve expected DB patch IDs" in tasks
    assert "Resolve selected patch component" in tasks
    assert "Fail when selected patch component is not eligible" in tasks
    assert "oracle_patch_apply_component_path" in tasks
    assert "Configured patch component not found" in tasks
    assert "Resolve expected Grid patch IDs" in tasks
    assert "'Database Release Update' in description" in tasks
    assert "selectattr('standby_first'" not in tasks
    assert "patch_inventory" in tasks
    assert "Read /etc/oratab DB homes for brownfield patching" in tasks
    assert "Read /etc/oracle/olr.loc Grid home for brownfield patching" in tasks
    assert "Resolve extra brownfield DB patch targets" in tasks
    assert "Resolve extra brownfield Grid patch targets" in tasks
    assert "oracle_patch_extra_homes" in tasks
    assert "oracle_patch_extra_grid_homes" in tasks
    assert "Report resolved Oracle patch targets" in tasks
    assert "home_path" in tasks
    assert "home_suffix" in tasks
    assert "restart_db_name" in tasks
    assert "Check Oracle home patch inventory" in tasks
    assert "installed_patch_ids" in tasks
    assert "Fail when patches are missing but apply is disabled" in tasks
    assert "Fail when standby-first orchestration is requested in per-host role" in tasks
    assert "playbooks/07-patch-standbyfirst.yml" in tasks
    assert "Apply Oracle home patch with opatchauto" in tasks
    assert "Read Restart database home for dual-home DB targets" in tasks
    assert "Record dual-home DB switch targets" in tasks
    assert "Fail when dual-home switch would need Data Guard orchestration" in tasks
    assert "oracle_patch_allow_dataguard_dual_home_switch | default(false)" in tasks
    assert "Switch Restart database to dual-home target" in tasks
    assert "Start DBs after dual-home Restart switch" in tasks
    assert "Reopen Data Guard standby read-only with apply after dual-home switch" in tasks
    assert (
        "ALTER DATABASE RECOVER MANAGED STANDBY DATABASE DISCONNECT FROM SESSION"
        in tasks
    )
    assert tasks.index(
        "Reopen Data Guard standby read-only with apply after dual-home switch"
    ) < tasks.index("Run datapatch for patched DB homes")
    assert "Run datapatch for patched DB homes" in tasks
    assert "oracle_patch_run_datapatch | bool" in tasks
    assert "SQL Patching tool complete" in tasks
    assert "Converge Oracle DB home patch inventory" in playbook
    assert "Converge Oracle Grid home patch inventory" in grid_playbook
    assert "oracle_patch_target: grid" in grid_playbook
    assert "Converge Oracle DB dual-home patch switch" in dual_playbook
    assert "Install Oracle DB dual-home target" in dual_playbook
    assert "Fail before installing target homes for Data Guard dual-home switch" in dual_playbook
    assert "playbooks/07-patch-standbyfirst.yml" in dual_playbook
    assert "Resolve inventory DB home paths for dual-home target" in dual_playbook
    assert "Check existing brownfield explicit dual-home path" in dual_playbook
    assert "Fail when explicit dual-home path is neither inventory-declared nor existing" in dual_playbook
    assert dual_playbook.index("Install Oracle DB dual-home target") < dual_playbook.index(
        "Converge Oracle DB dual-home patch switch"
    )
    assert "oracle_db_install_home_selection: selected" in dual_playbook
    assert "oracle_db_install_home_suffixes" in dual_playbook
    assert "oracle_db_install_home_paths" in dual_playbook
    assert "oracle_patch_dual_home_path | default('') | length == 0" in dual_playbook
    assert "oracle_patch_mode: oop_dual" in dual_playbook
    assert "oracle_patch_discover_oratab: false" in dual_playbook
    assert "Rehearse standalone DB dual-home switch and switchback" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_execute: false" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_target_path: \"\"" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_discover_restart: false" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_discovered_restart_names: []" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_listener_names: {}" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_sid_names: {}" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_install_discovered_targets: true" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_restart_discovery_fixture: []" in dual_switchback_playbook
    assert "SWITCH_DUAL_HOME_AND_BACK" in dual_switchback_playbook
    assert "Read Restart database names for switchback discovery" in dual_switchback_playbook
    assert "Read Restart database homes for switchback discovery" in dual_switchback_playbook
    assert "Resolve fixture Restart database homes for switchback discovery" in dual_switchback_playbook
    assert "Resolve Restart-discovered switchback targets" in dual_switchback_playbook
    assert "Merge inventory and Restart-discovered switchback targets" in dual_switchback_playbook
    assert "Resolve standalone switchback execution targets" in dual_switchback_playbook
    assert "_dual_switchback_standalone_targets" in dual_switchback_playbook
    assert "Report resolved dual-home switchback targets" in dual_switchback_playbook
    assert "original_home_path" in dual_switchback_playbook
    assert "target_home_path" in dual_switchback_playbook
    assert "'dataguard': item.dataguard | default(false) | bool" in dual_switchback_playbook
    assert "'dataguard': result.dataguard | default(false) | bool" in dual_switchback_playbook
    assert "Report Restart-discovered install plan" in dual_switchback_playbook
    assert "readiness/test-only" in dual_switchback_playbook
    assert "Fail when fixture Restart discovery is used for execution" in dual_switchback_playbook
    assert "Report readiness-only mode" in dual_switchback_playbook
    assert "standalone DB candidate(s)" in dual_switchback_playbook
    assert "Data Guard target(s)" in dual_switchback_playbook
    assert "Fail when switchback is requested for Data Guard hosts" not in dual_switchback_playbook
    assert (
        "Fail when Restart-discovered switchback targets are not explicitly named"
        in dual_switchback_playbook
    )
    assert (
        "Fail when requested Restart-discovered switchback targets are missing"
        in dual_switchback_playbook
    )
    assert (
        "Fail when Restart-discovered listener names are not explicitly mapped"
        in dual_switchback_playbook
    )
    assert (
        "Fail when Restart-discovered SID names are not explicitly mapped"
        in dual_switchback_playbook
    )
    assert "Check existing brownfield switchback target path" in dual_switchback_playbook
    assert "Check existing Restart-discovered switchback target paths" in dual_switchback_playbook
    assert (
        "Fail when Restart-discovered switchback target path does not exist"
        in dual_switchback_playbook
    )
    assert "Read actual Restart homes before dual-home switchback" in dual_switchback_playbook
    assert "Record actual original Restart homes for switchback" in dual_switchback_playbook
    assert "Read Restart-discovered database role before standalone switch" in dual_switchback_playbook
    assert "Fail when Restart-discovered database is not standalone primary" in dual_switchback_playbook
    assert "PRIMARY|MAXIMUM PERFORMANCE|0|0" in dual_switchback_playbook
    assert "v$archive_dest" in dual_switchback_playbook
    assert "v$dataguard_config" in dual_switchback_playbook
    assert dual_switchback_playbook.index(
        "Fail when Restart-discovered database is not standalone primary"
    ) < dual_switchback_playbook.index("Patch Restart-discovered dual-home target homes")
    assert "Resolve Restart-discovered target homes for patching" in dual_switchback_playbook
    assert "Resolve Restart-discovered target homes for installation" in dual_switchback_playbook
    assert "Gather facts required for target-home installation" in dual_switchback_playbook
    assert "gather_subset:" in dual_switchback_playbook
    assert "Install dual-home switchback target" in dual_switchback_playbook
    assert "Install Restart-discovered dual-home target homes" in dual_switchback_playbook
    assert (
        'oracle_db_install_instances: "{{ _dual_switchback_restart_install_instances | default([]) }}"'
        in dual_switchback_playbook
    )
    assert "Switch Restart to dual-home target" in dual_switchback_playbook
    assert dual_switchback_playbook.index(
        "Install Restart-discovered dual-home target homes"
    ) < dual_switchback_playbook.index("Switch Restart to dual-home target")
    assert dual_switchback_playbook.index(
        "Install Restart-discovered dual-home target homes"
    ) < dual_switchback_playbook.index("Patch Restart-discovered dual-home target homes")
    assert "oracle_patch_discover_oratab: false" in dual_switchback_playbook
    assert "Patch Restart-discovered dual-home target homes" in dual_switchback_playbook
    assert "oracle_patch_extra_homes" in dual_switchback_playbook
    assert "oracle_patch_run_datapatch: false" in dual_switchback_playbook
    assert "Stop Restart-discovered DBs before dual-home target switch" in dual_switchback_playbook
    assert "Switch Restart-discovered database to dual-home target" in dual_switchback_playbook
    assert "Switch Restart-discovered listener to dual-home target" in dual_switchback_playbook
    assert "_dual_switchback_modify_discovered_target_listener.rc != 0" in dual_switchback_playbook
    assert "Start Restart-discovered DBs after dual-home target switch" in dual_switchback_playbook
    assert "Run datapatch for Restart-discovered switched DBs" in dual_switchback_playbook
    assert "SQL Patching tool complete" in dual_switchback_playbook
    assert "Validate Restart uses dual-home target" in dual_switchback_playbook
    assert "loop: \"{{ _dual_switchback_standalone_targets }}\"" in dual_switchback_playbook
    assert "Stop DBs before dual-home switchback" in dual_switchback_playbook
    assert "Switch Restart database back to actual original home" in dual_switchback_playbook
    assert "Switch Restart listener back to actual original home" in dual_switchback_playbook
    assert "item.source == 'restart'" in dual_switchback_playbook
    assert "Start DBs after dual-home switchback" in dual_switchback_playbook
    assert "Validate Restart uses original home again" in dual_switchback_playbook
    assert "item.actual_original_home_path" in dual_switchback_playbook
    assert "Validate standby-first patch eligibility" in standbyfirst_playbook
    assert "oracle_patch_apply_component_path: \"\"" in standbyfirst_playbook
    assert "Resolve selected standby-first patch component" in standbyfirst_playbook
    assert "Fail when selected patch component is not standby-first eligible" in standbyfirst_playbook
    assert "Fail when patch is not standby-first eligible" in standbyfirst_playbook
    assert "oracle_patch_standbyfirst_execute: false" in standbyfirst_playbook
    assert "oracle_patch_standbyfirst_restore_primary: false" in standbyfirst_playbook
    assert 'oracle_patch_standbyfirst_expected_primary: ""' in standbyfirst_playbook
    assert 'oracle_patch_standbyfirst_expected_standby: ""' in standbyfirst_playbook
    assert 'oracle_patch_standbyfirst_confirm: ""' in standbyfirst_playbook
    assert "PATCH_STANDBY_FIRST" in standbyfirst_playbook
    assert "Fail when standby-first execution is not explicitly confirmed" in standbyfirst_playbook
    assert "Report standby-first readiness-only mode" in standbyfirst_playbook
    assert "Discover current Data Guard roles for standby-first patching" in standbyfirst_playbook
    standbyfirst_gate = standbyfirst_playbook.index(
        "Fail when patch is not standby-first eligible"
    )
    standbyfirst_confirm_gate = standbyfirst_playbook.index(
        "Fail when standby-first execution is not explicitly confirmed"
    )
    assert standbyfirst_gate < standbyfirst_confirm_gate
    assert standbyfirst_confirm_gate < standbyfirst_playbook.index(
        "Discover current Data Guard roles for standby-first patching"
    )
    assert standbyfirst_playbook.index(
        "Fail when broker roles could not be resolved"
    ) < standbyfirst_playbook.index("Report standby-first execution plan")
    assert "Fail when current primary does not match expected standby-first primary" in standbyfirst_playbook
    assert "Fail when current standby does not match expected standby-first standby" in standbyfirst_playbook
    assert standbyfirst_playbook.index(
        "Fail when broker roles could not be resolved"
    ) < standbyfirst_playbook.index(
        "Fail when current primary does not match expected standby-first primary"
    )
    assert standbyfirst_playbook.index(
        "Fail when current standby does not match expected standby-first standby"
    ) < standbyfirst_playbook.index("Report standby-first execution plan")
    assert standbyfirst_playbook.index(
        "Report standby-first execution plan"
    ) < standbyfirst_playbook.index("Add host to current standby patch group")
    for destructive_task in [
        "Discover current Data Guard roles for standby-first patching",
        "Install current Data Guard standby DB target homes",
        "Patch current Data Guard standby DB homes",
        "Switchover Data Guard primary for standby-first patch",
        "Run datapatch on promoted Data Guard primary",
    ]:
        assert standbyfirst_gate < standbyfirst_playbook.index(destructive_task)
    guarded_destructive_actions = [
        "Install current Data Guard standby DB target homes",
        "Patch current Data Guard standby DB homes",
        "Switchover Data Guard primary for standby-first patch",
        "Run datapatch on promoted Data Guard primary",
        "Install new Data Guard standby DB target homes",
        "Patch new Data Guard standby DB homes",
        "Validate Data Guard broker after standby-first patching",
        "Restore original Data Guard primary after standby-first patching",
        "Validate original primary after standby-first restore",
    ]
    for destructive_action in guarded_destructive_actions:
        action_pos = standbyfirst_playbook.index(destructive_action)
        guard_pos = standbyfirst_playbook.index(
            "oracle_patch_standbyfirst_execute | default(false) | bool",
            action_pos,
        )
        assert action_pos < guard_pos
    assert "Read Data Guard broker roles and protection mode" in standbyfirst_playbook
    assert "Publish standby-first broker facts to static primary hosts" in standbyfirst_playbook
    assert "Fail when broker is not in Maximum Availability" in standbyfirst_playbook
    assert "Report standby-first execution plan" in standbyfirst_playbook
    assert "target_homes" in standbyfirst_playbook
    assert "restore_original_primary" in standbyfirst_playbook
    assert "patch_current_standby" in standbyfirst_playbook
    assert "patch_current_primary" in standbyfirst_playbook
    assert "Install current Data Guard standby DB target homes" in standbyfirst_playbook
    assert "Install new Data Guard standby DB target homes" in standbyfirst_playbook
    assert "oracle_db_install_home_selection: selected" in standbyfirst_playbook
    assert "oracle_db_install_home_suffixes" in standbyfirst_playbook
    assert "oracle_db_install_home_paths" in standbyfirst_playbook
    assert "Patch current Data Guard standby DB homes" in standbyfirst_playbook
    assert "hosts: patch_current_standby" in standbyfirst_playbook
    assert "Validate current Data Guard standby before standby-first switchover" in standbyfirst_playbook
    assert "Validate current standby is read-only with apply before switchover" in standbyfirst_playbook
    assert "Switchover Data Guard primary for standby-first patch" in standbyfirst_playbook
    assert "oracle_dataguard_run_switchover: true" in standbyfirst_playbook
    assert 'oracle_dataguard_switchover_target: "{{ _patch_sf_current_standby }}"' in standbyfirst_playbook
    assert "_patch_sf_patch_home_path" in standbyfirst_playbook
    assert "oracle_patch_run_datapatch: false" in standbyfirst_playbook
    assert "Run datapatch on promoted Data Guard primary" in standbyfirst_playbook
    assert "Run datapatch after standby-first switchover" in standbyfirst_playbook
    assert "SQL Patching tool complete" in standbyfirst_playbook
    assert standbyfirst_playbook.index(
        "Switchover Data Guard primary for standby-first patch"
    ) < standbyfirst_playbook.index("Run datapatch on promoted Data Guard primary")
    assert standbyfirst_playbook.index(
        "Run datapatch on promoted Data Guard primary"
    ) < standbyfirst_playbook.index("Install new Data Guard standby DB target homes")
    assert "Patch new Data Guard standby DB homes" in standbyfirst_playbook
    assert "hosts: patch_current_primary" in standbyfirst_playbook
    assert "oracle_patch_mode: >-" in standbyfirst_playbook
    assert "oracle_patch_apply_enabled: true" in standbyfirst_playbook
    assert "oracle_patch_dg_standbyfirst: false" in standbyfirst_playbook
    assert "oracle_patch_allow_dataguard_dual_home_switch: true" in standbyfirst_playbook
    assert "READ ONLY WITH APPLY" in standbyfirst_playbook
    assert (
        "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
        in standbyfirst_playbook
    )
    assert (
        "PRIMARY|READ WRITE|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
        in standbyfirst_playbook
    )
    assert "Validate Data Guard broker after standby-first patching" in standbyfirst_playbook
    assert "Validate Maximum Availability after standby-first patching" in standbyfirst_playbook
    assert "Restore original Data Guard primary after standby-first patching" in standbyfirst_playbook
    assert 'oracle_dataguard_switchover_target: "{{ _patch_sf_current_primary }}"' in standbyfirst_playbook
    assert "oracle_patch_standbyfirst_restore_primary | default(false) | bool" in standbyfirst_playbook
    assert "Validate original primary after standby-first restore" in standbyfirst_playbook
    assert "Validate original primary and standby after standby-first restore" in standbyfirst_playbook
    assert "Report Data Guard standby-first patch media" in standbyfirst_media_playbook
    assert "Scan staged patch zips for standby-first eligibility" in standbyfirst_media_playbook
    assert "directory: \"{{ oracle_stage_dir }}\"" in standbyfirst_media_playbook
    assert "oracle_patch_standbyfirst_media_require_eligible: false" in standbyfirst_media_playbook
    assert "Report standby-first media scan" in standbyfirst_media_playbook
    assert "Report eligible standby-first command handoff" in standbyfirst_media_playbook
    assert "Report eligible standby-first DB RU component handoff" in standbyfirst_media_playbook
    assert "oracle_patch_zip={{ oracle_stage_dir }}/{{ item.basename }}" in standbyfirst_media_playbook
    assert "oracle_patch_apply_component_path={{ item.component_path }}" in standbyfirst_media_playbook
    assert "No staged patch zip or DB RU component is Data Guard Standby-First" in standbyfirst_media_playbook


def test_patch_applied_to_db_home(lab_exec):
    cmd = (
        f"export ORACLE_HOME={ORACLE_HOME} && "
        f"{ORACLE_HOME}/OPatch/opatch lspatches"
    )
    r = lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert EXPECTED_DB_RU in r.stdout
    assert "Database Release Update" in r.stdout
    assert "OPatch succeeded" in r.stdout


def test_patch_applied_to_grid_home(lab_exec):
    cmd = (
        f"export ORACLE_HOME={GRID_HOME} && "
        f"{GRID_HOME}/OPatch/opatch lspatches"
    )
    r = lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    for patch_id in EXPECTED_GI_PATCH_IDS:
        assert f"{patch_id};" in r.stdout
    assert "OPatch succeeded" in r.stdout


def test_dual_home_switchback_target_installed_and_original_restored(lab_exec):
    marker = lab_exec(f"test -f {SWITCHBACK_TARGET_HOME}/.install_complete")
    assert marker.returncode == 0, (
        f"{SWITCHBACK_TARGET_HOME} is not installed; run confirmed switchback proof"
    )

    target_patch = (
        f"export ORACLE_HOME={SWITCHBACK_TARGET_HOME} && "
        f"{SWITCHBACK_TARGET_HOME}/OPatch/opatch lspatches"
    )
    patch_result = lab_exec(f"su - oracle -c {shlex.quote(target_patch)}", timeout=180)
    assert patch_result.returncode == 0, patch_result.stdout + patch_result.stderr
    assert EXPECTED_DB_RU in patch_result.stdout
    assert "OPatch succeeded" in patch_result.stdout

    db_home = lab_exec(
        "su - oracle -c "
        + shlex.quote(
            f"/grid/19c/gi_home1/bin/srvctl config database -db {SWITCHBACK_DB} | "
            "sed -n 's/^Oracle home: //p'"
        )
    )
    assert db_home.returncode == 0, db_home.stdout + db_home.stderr
    assert db_home.stdout.strip() == SWITCHBACK_ORIGINAL_HOME

    listener_home = lab_exec(
        "su - oracle -c "
        + shlex.quote(
            "/grid/19c/gi_home1/bin/srvctl config listener "
            f"-listener {SWITCHBACK_LISTENER} -a | sed -n 's/^Home: //p'"
        )
    )
    assert listener_home.returncode == 0, listener_home.stdout + listener_home.stderr
    assert listener_home.stdout.strip() == SWITCHBACK_ORIGINAL_HOME

    database_status = lab_exec(
        f"su - oracle -c '/grid/19c/gi_home1/bin/srvctl status database -d {SWITCHBACK_DB}'"
    )
    assert database_status.returncode == 0, database_status.stdout + database_status.stderr
    assert "Database is running." in database_status.stdout

    service_status = lab_exec(
        f"su - oracle -c '/grid/19c/gi_home1/bin/srvctl status service -d {SWITCHBACK_DB}'"
    )
    assert service_status.returncode == 0, service_status.stdout + service_status.stderr
    assert f"Service {SWITCHBACK_SERVICE} is running" in service_status.stdout

    switched_sql = (
        f"export ORACLE_HOME={SWITCHBACK_ORIGINAL_HOME} ORACLE_SID={SWITCHBACK_SID} && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT name || '|' || open_mode FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    switched_state = lab_exec(f"su - oracle -c {shlex.quote(switched_sql)}")
    assert switched_state.returncode == 0, switched_state.stdout + switched_state.stderr
    assert f"{SWITCHBACK_DB.upper()}|READ WRITE" in switched_state.stdout

    dataguard_sql = (
        f"export ORACLE_HOME={ORACLE_HOME} ORACLE_SID={DATAGUARD_SID} && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT name || '|' || database_role || '|' || open_mode || '|' || "
        "protection_mode || '|' || protection_level FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    dataguard_state = lab_exec(f"su - oracle -c {shlex.quote(dataguard_sql)}")
    assert dataguard_state.returncode == 0, dataguard_state.stdout + dataguard_state.stderr
    assert (
        "SUPER|PRIMARY|READ WRITE|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
        in dataguard_state.stdout
    )


def test_patch_playbook_converges_when_ru_already_present():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch.yml",
        "-e",
        "oracle_patch_apply_enabled=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    assert '"name": "super"' in r.stdout
    assert '"name": "duper"' in r.stdout
    assert '"name": "fluff"' in r.stdout
    assert '"source": "inventory"' in r.stdout
    assert '"source": "oratab"' in r.stdout
    assert '"home_path": "/super/app/oracle/db_home1"' in r.stdout
    assert '"home_path": "/duper/app/oracle/db_home1"' in r.stdout
    assert '"home_path": "/fluff/app/oracle/db_home1"' in r.stdout


def test_grid_patch_playbook_converges_when_ru_already_present():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-grid.yml",
        "-e",
        "oracle_patch_apply_enabled=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    assert '"name": "super_grid"' in r.stdout
    assert '"source": "inventory"' in r.stdout
    assert '"home_path": "/grid/19c/gi_home1"' in r.stdout


def test_dual_home_switch_playbook_converges_when_target_is_current_home():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-dual-db.yml",
        "-e",
        "oracle_patch_apply_enabled=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout


def test_dual_home_switchback_playbook_resolves_readiness_without_switching():
    inventory_data = yaml.safe_load((REPO_ROOT / "inventory/hosts.yml").read_text())
    groups = inventory_data["all"]["children"]

    def group_hosts(group_name: str) -> set[str]:
        group = groups[group_name]
        hosts = set((group.get("hosts") or {}).keys())
        for child in (group.get("children") or {}).keys():
            hosts.update(group_hosts(child))
        return hosts

    expected_db_hosts = len(group_hosts("oracle_db_hosts"))
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-dual-db-switchback.yml",
        "-e",
        "oracle_patch_dual_home_switchback_discover_restart=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    readiness_reports = re.findall(
        r"Dual-home switchback readiness resolved for (\d+) standalone DB "
        r"candidate\(s\) and (\d+) Data Guard target\(s\)",
        r.stdout,
    )
    assert len(readiness_reports) == expected_db_hosts
    assert {int(dataguard_count) for _, dataguard_count in readiness_reports} == {1}
    assert sum(int(standalone_count) for standalone_count, _ in readiness_reports) <= 2
    assert '"restart_db_name": "super"' in r.stdout
    assert '"restart_db_name": "super_sby"' in r.stdout
    assert '"restart_db_name": "duper"' in r.stdout
    assert '"restart_db_name": "fluff"' in r.stdout
    assert '"source": "inventory"' in r.stdout
    assert '"source": "restart"' in r.stdout
    assert '"original_home_path": "/super/app/oracle/db_home1"' in r.stdout
    assert '"original_home_path": "/duper/app/oracle/db_home1"' in r.stdout
    assert '"original_home_path": "/fluff/app/oracle/db_home1"' in r.stdout
    assert '"target_home_path": "/super/app/oracle/db_home2"' in r.stdout
    assert '"target_home_path": "/duper/app/oracle/db_home2"' in r.stdout
    assert '"target_home_path": "/fluff/app/oracle/db_home2"' in r.stdout
    assert "Restart-discovered target-home install plan" not in r.stdout
    assert "Data Guard targets must use playbooks/07-patch-standbyfirst.yml" in r.stdout
    assert "TASK [Install dual-home switchback target]" in r.stdout
    assert "skipping:" in r.stdout


def test_dual_home_switchback_fixture_reports_discovered_install_plan(tmp_path):
    inventory = tmp_path / "hosts.yml"
    inventory.write_text(
        """
all:
  children:
    oracle_db_hosts:
      hosts:
        localhost:
          ansible_connection: local
          ansible_become: false
""".lstrip(),
        encoding="utf-8",
    )
    extra_vars = {
        "oracle_user": os.environ.get("USER", "oracle"),
        "oracle_instances": [],
        "oracle_patch_dual_home_switchback_restart_discovery_fixture": [
            {
                "restart_db_name": "brown",
                "home_path": "/brown/app/oracle/db_home1",
            }
        ],
    }
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        str(inventory),
        "playbooks/07-patch-dual-db-switchback.yml",
        "-e",
        json.dumps(extra_vars),
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    assert "Restart-discovered target-home install plan" in r.stdout
    assert "'name': 'brown'" in r.stdout
    assert "'oracle_base': '/brown/app/oracle'" in r.stdout
    assert "'suffix': 'db_home2'" in r.stdout
    assert "TASK [Install Restart-discovered dual-home target homes]" in r.stdout
    assert "skipping:" in r.stdout


def test_dual_home_switchback_fixture_cannot_execute(tmp_path):
    inventory = tmp_path / "hosts.yml"
    inventory.write_text(
        """
all:
  children:
    oracle_db_hosts:
      hosts:
        localhost:
          ansible_connection: local
          ansible_become: false
""".lstrip(),
        encoding="utf-8",
    )
    extra_vars = {
        "oracle_user": os.environ.get("USER", "oracle"),
        "oracle_instances": [],
        "oracle_patch_dual_home_switchback_execute": True,
        "oracle_patch_dual_home_switchback_confirm": "SWITCH_DUAL_HOME_AND_BACK",
        "oracle_patch_dual_home_switchback_restart_discovery_fixture": [
            {
                "restart_db_name": "brown",
                "home_path": "/brown/app/oracle/db_home1",
            }
        ],
    }
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        str(inventory),
        "playbooks/07-patch-dual-db-switchback.yml",
        "-e",
        json.dumps(extra_vars),
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode != 0, r.stdout + r.stderr
    assert "readiness/test-only" in r.stdout
    assert "Install Restart-discovered dual-home target homes" not in r.stdout


def test_dual_home_switchback_fixture_dataguard_suppresses_install_plan(tmp_path):
    inventory = tmp_path / "hosts.yml"
    inventory.write_text(
        """
all:
  children:
    oracle_db_hosts:
      hosts:
        localhost:
          ansible_connection: local
          ansible_become: false
""".lstrip(),
        encoding="utf-8",
    )
    extra_vars = {
        "oracle_user": os.environ.get("USER", "oracle"),
        "oracle_instances": [],
        "oracle_patch_dual_home_switchback_restart_discovery_fixture": [
            {
                "restart_db_name": "brown_sby",
                "home_path": "/brown/app/oracle/db_home1",
                "dataguard": True,
            }
        ],
    }
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        str(inventory),
        "playbooks/07-patch-dual-db-switchback.yml",
        "-e",
        json.dumps(extra_vars),
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    assert "Restart-discovered target-home install plan" not in r.stdout
    assert (
        "Dual-home switchback readiness resolved for 0 standalone DB candidate(s) "
        "and 1 Data Guard target(s)"
    ) in r.stdout


def test_restart_database_uses_current_oracle_home_after_dual_home_noop(lab_exec):
    cmd = (
        "/grid/19c/gi_home1/bin/srvctl config database -db super | "
        "awk -F': ' '$1 == \"Oracle home\" {print $2}'"
    )
    r = lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ORACLE_HOME


def test_standbyfirst_playbook_rejects_current_ojvm_combo_before_patching():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-standbyfirst.yml",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = r.stdout + r.stderr
    if (
        r.returncode != 0
        and "not Data Guard standby-first installable" not in r.stdout
        and ("unreachable=1" in output or "UNREACHABLE!" in output)
    ):
        pytest.skip("KVM lab host unreachable; standby-first live precheck not run")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "not Data Guard standby-first installable" in r.stdout
    for skipped_task in [
        "Discover current Data Guard roles for standby-first patching",
        "Read Data Guard broker roles and protection mode",
        "Install current Data Guard standby DB target homes",
        "Patch current Data Guard standby DB homes",
        "Switchover Data Guard primary for standby-first patch",
        "Run datapatch on promoted Data Guard primary",
        "Install new Data Guard standby DB target homes",
        "Patch new Data Guard standby DB homes",
    ]:
        assert skipped_task not in r.stdout


def test_standbyfirst_final_command_without_confirmation_refuses_before_patching():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-standbyfirst.yml",
        "-e",
        "oracle_patch_zip=/u01/stage/p39062931_190000_Linux-x86-64.zip",
        "-e",
        "oracle_patch_apply_component_path=39062931/39034528",
        "-e",
        "oracle_patch_dual_home_suffix=db_home2",
        "-e",
        "oracle_patch_standbyfirst_execute=true",
        "-e",
        "oracle_patch_standbyfirst_restore_primary=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = r.stdout + r.stderr
    if (
        r.returncode != 0
        and "Standby-first patch execution installs/patches" not in output
        and ("unreachable=1" in output or "UNREACHABLE!" in output)
    ):
        pytest.skip("KVM lab host unreachable; standby-first confirmation gate not run")

    assert r.returncode != 0, output
    assert "Standby-first patch execution installs/patches" in output
    assert "PATCH_STANDBY_FIRST" in output
    for skipped_task in [
        "Discover current Data Guard roles for standby-first patching",
        "Report standby-first execution plan",
        "Install current Data Guard standby DB target homes",
        "Patch current Data Guard standby DB homes",
        "Switchover Data Guard primary for standby-first patch",
        "Run datapatch on promoted Data Guard primary",
        "Install new Data Guard standby DB target homes",
        "Patch new Data Guard standby DB homes",
        "Restore original Data Guard primary after standby-first patching",
    ]:
        assert skipped_task not in r.stdout


def test_standbyfirst_readiness_only_validates_dataguard_without_execution():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-standbyfirst.yml",
        "-e",
        "oracle_patch_standbyfirst_require_eligible=false",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = r.stdout + r.stderr
    if (
        r.returncode != 0
        and ("unreachable=1" in output or "UNREACHABLE!" in output)
    ):
        pytest.skip("KVM lab host unreachable; standby-first readiness not run")

    assert r.returncode == 0, output
    assert (
        "Standby-first readiness passed for primary=super, standby=super_sby"
        in r.stdout
    )
    assert "Report standby-first execution plan" in r.stdout
    assert "restore_original_primary" in r.stdout
    assert "target_homes" in r.stdout
    assert "protection=MaxAvailability" in r.stdout
    assert "No DB homes were installed or patched" in r.stdout
    assert "no broker switchover was run" in r.stdout
    assert "datapatch was not executed" in r.stdout
    assert "changed=0" in r.stdout
    assert "failed=0" in r.stdout
    assert "unreachable=0" in r.stdout


def test_standbyfirst_media_scan_reports_current_staged_zips():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-standbyfirst-media.yml",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = r.stdout + r.stderr
    if (
        r.returncode != 0
        and ("unreachable=1" in output or "UNREACHABLE!" in output)
    ):
        pytest.skip("KVM lab host unreachable; standby-first media scan not run")

    assert r.returncode == 0, output
    assert "Standby-first media scan examined" in r.stdout
    assert "eligible=0" in r.stdout
    assert "eligible_db_components=" in r.stdout
    assert "Eligible zip(s): none" in r.stdout
    assert "Eligible standby-first DB RU component 39034528" in r.stdout
    assert "oracle_patch_apply_component_path=39062931/39034528" in r.stdout
    assert "p39062931_190000_Linux-x86-64.zip" in r.stdout
    assert "p39062956_190000_Linux-x86-64.zip" in r.stdout
    assert "changed=0" in r.stdout
    assert "failed=0" in r.stdout


def test_standbyfirst_media_scan_can_require_eligible_zip():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch-standbyfirst-media.yml",
        "-e",
        "oracle_patch_standbyfirst_media_require_eligible=true",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = r.stdout + r.stderr
    if r.returncode != 0 and ("unreachable=1" in output or "UNREACHABLE!" in output):
        pytest.skip("KVM lab host unreachable; standby-first media gate not run")

    assert r.returncode == 0, output
    assert "eligible=0" in r.stdout
    assert "eligible_db_components=" in r.stdout
    assert "Eligible standby-first DB RU component 39034528" in r.stdout
