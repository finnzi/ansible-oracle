"""Oracle DB home patch inventory and convergence assertions."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE_HOME = os.environ.get("ORACLE_TEST_ORACLE_HOME", "/super/app/oracle/db_home1")
GRID_HOME = os.environ.get("ORACLE_TEST_GRID_HOME", "/grid/19c/gi_home1")
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

    assert "oracle_patch_apply_enabled: false" in defaults
    assert "oracle_patch_expected_patch_ids: []" in defaults
    assert "oracle_patch_expected_grid_patch_ids: []" in defaults
    assert "oracle_patch_target: db" in defaults
    assert "oracle_patch_mode: inplace" in defaults
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
    assert "Rehearse standalone DB dual-home switch and switchback" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_execute: false" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_target_path: \"\"" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_discover_restart: false" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_discovered_restart_names: []" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_listener_names: {}" in dual_switchback_playbook
    assert "oracle_patch_dual_home_switchback_sid_names: {}" in dual_switchback_playbook
    assert "SWITCH_DUAL_HOME_AND_BACK" in dual_switchback_playbook
    assert "Read Restart database names for switchback discovery" in dual_switchback_playbook
    assert "Read Restart database homes for switchback discovery" in dual_switchback_playbook
    assert "Resolve Restart-discovered switchback targets" in dual_switchback_playbook
    assert "Merge inventory and Restart-discovered switchback targets" in dual_switchback_playbook
    assert "Report readiness-only mode" in dual_switchback_playbook
    assert "Fail when switchback is requested for Data Guard hosts" in dual_switchback_playbook
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
    assert "Install dual-home switchback target" in dual_switchback_playbook
    assert "Switch Restart to dual-home target" in dual_switchback_playbook
    assert "oracle_patch_discover_oratab: false" in dual_switchback_playbook
    assert "Patch Restart-discovered dual-home target homes" in dual_switchback_playbook
    assert "oracle_patch_extra_homes" in dual_switchback_playbook
    assert "oracle_patch_run_datapatch: false" in dual_switchback_playbook
    assert "Stop Restart-discovered DBs before dual-home target switch" in dual_switchback_playbook
    assert "Switch Restart-discovered database to dual-home target" in dual_switchback_playbook
    assert "Switch Restart-discovered listener to dual-home target" in dual_switchback_playbook
    assert "Start Restart-discovered DBs after dual-home target switch" in dual_switchback_playbook
    assert "Run datapatch for Restart-discovered switched DBs" in dual_switchback_playbook
    assert "Validate Restart uses dual-home target" in dual_switchback_playbook
    assert "Stop DBs before dual-home switchback" in dual_switchback_playbook
    assert "Switch Restart database back to actual original home" in dual_switchback_playbook
    assert "Switch Restart listener back to actual original home" in dual_switchback_playbook
    assert "Start DBs after dual-home switchback" in dual_switchback_playbook
    assert "Validate Restart uses original home again" in dual_switchback_playbook
    assert "item.actual_original_home_path" in dual_switchback_playbook
    assert "Validate standby-first patch eligibility" in standbyfirst_playbook
    assert "Fail when patch is not standby-first eligible" in standbyfirst_playbook
    assert "Discover current Data Guard roles for standby-first patching" in standbyfirst_playbook
    assert "Read Data Guard broker roles and protection mode" in standbyfirst_playbook
    assert "Publish standby-first broker facts to static primary hosts" in standbyfirst_playbook
    assert "Fail when broker is not in Maximum Availability" in standbyfirst_playbook
    assert "patch_current_standby" in standbyfirst_playbook
    assert "patch_current_primary" in standbyfirst_playbook
    assert "Install current Data Guard standby DB target homes" in standbyfirst_playbook
    assert "Install new Data Guard standby DB target homes" in standbyfirst_playbook
    assert "oracle_db_install_home_selection: selected" in standbyfirst_playbook
    assert "oracle_db_install_home_suffixes" in standbyfirst_playbook
    assert "oracle_db_install_home_paths" in standbyfirst_playbook
    assert "Patch current Data Guard standby DB homes" in standbyfirst_playbook
    assert "hosts: patch_current_standby" in standbyfirst_playbook
    assert "Validate current Data Guard standby after target-home patch" in standbyfirst_playbook
    assert "Validate current standby is read-only with apply before switchover" in standbyfirst_playbook
    assert "Switchover Data Guard primary for standby-first patch" in standbyfirst_playbook
    assert "oracle_dataguard_run_switchover: true" in standbyfirst_playbook
    assert 'oracle_dataguard_switchover_target: "{{ _patch_sf_current_standby }}"' in standbyfirst_playbook
    assert "_patch_sf_patch_home_path" in standbyfirst_playbook
    assert "oracle_patch_run_datapatch: false" in standbyfirst_playbook
    assert "Run datapatch on promoted Data Guard primary" in standbyfirst_playbook
    assert "Run datapatch after standby-first switchover" in standbyfirst_playbook
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
    assert "Dual-home switchback readiness resolved" in r.stdout
    assert "TASK [Install dual-home switchback target]" in r.stdout
    assert "skipping:" in r.stdout


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
    assert r.returncode != 0, r.stdout + r.stderr
    assert "not Data Guard standby-first installable" in r.stdout
    assert "Patch current Data Guard standby DB homes" not in r.stdout
