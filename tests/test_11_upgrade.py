"""Contract tests for dual-home upgrade prepare/cutover and version detection."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_inventory_upgrade_and_inventory_loc_defaults():
    defaults = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(encoding="utf-8")
    assert 'oracle_inventory_loc: /home/oracle/oraInventory' in defaults
    assert "oracle_inventory_enforce_single: true" in defaults
    assert 'oracle_release_update: "19.31.0.0.260421"' in defaults
    assert 'oracle_upgrade_release_update: "19.32.0.0.260721"' in defaults
    assert 'db_ru_upgrade_zip: "p39618649_190000_Linux-x86-64.zip"' in defaults
    assert 'gi_ru_upgrade_zip: "p39618711_190000_Linux-x86-64.zip"' in defaults
    assert 'oracle_upgrade_db_ru_component_path: "39618649/39472050"' in defaults
    assert 'oracle_upgrade_db_ru_patch_id: "39472050"' in defaults
    # Greenfield current home is dbhome_1; dbhome_2 is the upgrade target.
    assert "- suffix: dbhome_1\n        current: true" in defaults
    assert "- suffix: dbhome_2\n        current: false" in defaults


def test_role_defaults_use_single_home_inventory():
    for rel in (
        "roles/oracle_common/defaults/main.yml",
        "roles/oracle_db_install/defaults/main.yml",
        "roles/oracle_gi_install/defaults/main.yml",
        "roles/oracle_observer/defaults/main.yml",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "oracle_inventory_loc: /home/oracle/oraInventory" in text
        assert "oracle_inventory_enforce_single" in text
        assert "/opt/oracle/oraInventory" not in text


def test_oracle_common_creates_inventory_dir():
    tasks = (REPO_ROOT / "roles/oracle_common/tasks/main.yml").read_text(encoding="utf-8")
    assert "Ensure single central Oracle inventory directory exists" in tasks
    assert "oracle_inventory_loc" in tasks


def test_db_install_enforces_single_inventory_pointer():
    tasks = (REPO_ROOT / "roles/oracle_db_install/tasks/main.yml").read_text(encoding="utf-8")
    assert "Fail when inventory pointer conflicts with single-inventory policy" in tasks
    assert "inventory_loc=" in tasks


def test_patch_role_switch_enabled_gate():
    defaults = (REPO_ROOT / "roles/oracle_patch/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_patch/tasks/main.yml").read_text(encoding="utf-8")
    assert "oracle_patch_switch_enabled: true" in defaults
    assert "Report dual-home switch deferred (prepare-only)" in tasks
    assert "oracle_patch_switch_enabled | default(true) | bool" in tasks
    assert "datapatch waits for cutover" in tasks


def test_db_deinstall_role_safety_contract():
    defaults = (REPO_ROOT / "roles/oracle_db_deinstall/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_db_deinstall/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    assert "oracle_db_deinstall_execute: false" in defaults
    assert "oracle_db_deinstall_homes: []" in defaults
    assert "oracle_db_deinstall_rescue_parameter_files: true" in defaults
    assert "Fail when a deinstall target is still registered with Restart" in tasks
    assert "Fail when a deinstall target is not an allowlisted Oracle home leaf" in tasks
    assert "Fail when a deinstall target overlaps a live Oracle tree" in tasks
    assert "oracle_deinstall_conflicts" in tasks
    assert "oracle_deinstall_is_allowlisted_leaf" in tasks
    assert "realpath -m" in tasks
    assert "inst.oracle_base" in tasks.split("Collect approved Oracle bases")[1].split("- name:")[0]
    # Fail closed: discovery must succeed; empty/failed/multi-line srvctl must not skip the guard.
    assert "Fail when Restart discovery could not list databases" in tasks
    assert "Fail when Restart home discovery failed for a registered database" in tasks
    assert "Fail when Restart home is not exactly one absolute path line" in tasks
    assert "exactly one absolute" in tasks
    assert "_deinstall_restart_home_paths" in tasks
    assert "fails closed" in tasks
    assert "failed_when: false" not in tasks.split("Read Restart database names before deinstall")[1].split(
        "Fail when a deinstall target is still registered"
    )[0]
    assert "Detach Oracle home from central inventory" in tasks
    assert "-detachHome" in tasks
    assert "Rescue spfile/pfile/orapw before removing Oracle home" in tasks
    assert "Remove Oracle home directory tree" in tasks
    assert "Remove per-home install staging directory" in tasks
    assert "Report deinstall plan (readiness)" in tasks


def test_dual_home_switch_relocates_spfile_to_durable_data_path():
    tasks = (REPO_ROOT / "roles/oracle_patch/tasks/main.yml").read_text(encoding="utf-8")
    cutover = (REPO_ROOT / "roles/oracle_patch/tasks/dual-home-cutover.yml").read_text(
        encoding="utf-8"
    )
    script = (
        REPO_ROOT / "roles/oracle_patch/files/relocate_spfile_for_dual_home.sh"
    ).read_text(encoding="utf-8")
    assert "Relocate spfile and password file to durable path for dual-home switch" in cutover
    assert "relocate_spfile_for_dual_home.sh" in cutover
    assert "include_tasks: dual-home-cutover.yml" in tasks
    assert "parameter_file_dir" in tasks
    assert "SPFILE_DURABLE" in script
    assert "dirs.data" in tasks
    restart = (
        REPO_ROOT / "roles/oracle_restart_manage/tasks/register-instance.yml"
    ).read_text(encoding="utf-8")
    assert "Ensure durable spfile path for Restart" in restart
    assert "inst.dirs.data" in restart


def test_network_role_supports_selected_homes_for_upgrade_target():
    defaults = (REPO_ROOT / "roles/oracle_network/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_network/tasks/main.yml").read_text(encoding="utf-8")
    assert "oracle_network_home_selection: current" in defaults
    assert "oracle_network_home_suffixes: []" in defaults
    assert "oracle_network_manage_listener: true" in defaults
    assert "oracle_network_instances: []" in defaults
    assert "oracle_network_manage_listener: true" in defaults
    assert "oracle_network_instances" in tasks
    assert "Fail when network home selection is invalid" in tasks
    assert "selection == 'selected'" in tasks
    assert "selected_suffixes" in tasks


def test_patch_role_accepts_scoped_instances_list():
    defaults = (REPO_ROOT / "roles/oracle_patch/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_patch/tasks/main.yml").read_text(encoding="utf-8")
    assert "oracle_patch_instances: []" in defaults
    assert "oracle_patch_instances" in tasks
    # Prefer role-scoped list over inventory/extra-var oracle_instances.
    assert "if (oracle_patch_instances | default([]) | length > 0)" in tasks


def test_upgrade_prepare_playbook_contract():
    playbook = (REPO_ROOT / "playbooks/07-upgrade-dual-db-prepare.yml").read_text(
        encoding="utf-8"
    )
    assert "oracle_patch_switch_enabled: false" in playbook
    assert "oracle_patch_run_datapatch: false" in playbook
    assert "db_ru_upgrade_zip" in playbook
    assert "39618649/39472050" in playbook
    assert "oracle_home_facts" in playbook
    assert "rejectattr('dataguard', 'equalto', true)" in playbook
    assert "playbooks/07-patch-standbyfirst.yml" in playbook
    assert "playbooks/07-upgrade-dual-db-downtime.yml" in playbook
    assert "oracle_db_deinstall" in playbook
    assert "Detach and remove unused dual-home target for clean reinstall" in playbook
    assert "oracle_upgrade_prepare_force_rebuild" in playbook
    assert "Decide which target homes need a clean rebuild" in playbook
    assert "Fail when target path equals the current runtime home" in playbook
    assert "Fail when target path is not an allowlisted Oracle home leaf" in playbook
    assert "Fail when target path overlaps live Oracle trees" in playbook
    assert "oracle_network_manage_listener: false" in playbook
    assert "Install standalone dual-home upgrade target into cleaned path" in playbook
    assert "Patch standalone dual-home upgrade target without Restart switch" in playbook
    assert "Deploy network/admin into the unused upgrade target home" in playbook
    assert "oracle_network_manage_listener: false" in playbook
    assert "oracle_network_home_selection: selected" in playbook
    assert "Fail when target home is missing network/admin files after apply" in playbook
    assert "clean_reinstall_unused_path" in playbook
    assert "parameter_file_dir" in playbook
    assert "data_dir" in playbook
    # Play-level media defaults; -e wins because include_role never rebinds zip.
    assert "db_ru_upgrade_zip" in playbook
    assert "Extra vars (-e) win" in playbook
    assert "never rebind zip or component" in playbook
    assert "oracle_patch_db_zip: \"{{ _upgrade_prepare_zip }}\"" not in playbook
    assert "oracle_patch_zip: \"{{ _upgrade_prepare_zip }}\"" not in playbook
    # Role-scoped instance list survives -e oracle_instances (extra-var clash).
    assert 'oracle_patch_instances: "{{ _upgrade_prepare_standalone_instances }}"' in playbook
    assert 'oracle_network_instances: "{{ _upgrade_prepare_standalone_instances }}"' in playbook
    assert 'oracle_instances: "{{ _upgrade_prepare_standalone_instances }}"' not in playbook
    # Prepare must not invent a third home suffix by default.
    assert "dbhome_3" not in playbook


def test_upgrade_cutover_playbook_contract():
    playbook = (REPO_ROOT / "playbooks/07-upgrade-dual-db-cutover.yml").read_text(
        encoding="utf-8"
    )
    assert "oracle_upgrade_cutover_execute: false" in playbook
    assert "CUTOVER_TO_UPGRADE_HOME" in playbook
    assert "oracle_home_facts" in playbook
    assert "oracle_patch_switch_enabled: true" in playbook
    assert "Fail when destructive cutover confirmation is missing" in playbook
    assert "Fail when target home is not at expected upgrade version" in playbook
    assert "Fail when target home is missing network/admin files" in playbook
    assert "tnsnames.ora" in playbook
    assert "Validate Restart uses upgrade target after cutover" in playbook
    assert "Validate database is open after cutover" in playbook
    assert "Validate database is open after cutover" in playbook
    # Role-scoped list so -e oracle_instances cannot reintroduce Data Guard super.
    assert "_upgrade_cutover_standalone_instances" in playbook
    assert 'oracle_patch_instances: "{{ _upgrade_cutover_standalone_instances }}"' in playbook
    assert 'oracle_instances: "{{ _upgrade_cutover_standalone_instances }}"' not in playbook
    # Play-level media defaults; -e wins because include_role never rebinds zip.
    assert "Extra vars (-e) win" in playbook
    assert "never rebind zip or component" in playbook
    assert "oracle_patch_db_zip: \"{{ _upgrade_cutover_zip }}\"" not in playbook
    assert "oracle_patch_zip: \"{{ _upgrade_cutover_zip }}\"" not in playbook


def test_upgrade_downtime_playbook_contract():
    playbook = (REPO_ROOT / "playbooks/07-upgrade-dual-db-downtime.yml").read_text(
        encoding="utf-8"
    )
    assert "DOWN_TIME_DUAL_HOME_UPGRADE" in playbook
    assert "oracle_upgrade_downtime_execute: false" in playbook
    assert "patch_standbyfirst_info" in playbook
    assert "playbooks/07-patch-standbyfirst.yml" in playbook
    assert "Fail when downtime confirmation is missing" in playbook
    assert "readiness scaffold only" in playbook


def test_oracle_home_facts_module_present():
    module = (REPO_ROOT / "library/oracle_home_facts.py").read_text(encoding="utf-8")
    assert "def gather_home_facts" in module
    assert "def parse_lspatches" in module
    assert "release_update" in module
    assert "db_ru_patch_id" in module


def test_dual_db_upgrade_helper_script_contract():
    helper = (REPO_ROOT / "scripts/run-dual-db-upgrade.sh").read_text(encoding="utf-8")
    assert "07-upgrade-dual-db-prepare.yml" in helper
    assert "07-upgrade-dual-db-cutover.yml" in helper
    assert "CUTOVER_TO_UPGRADE_HOME" in helper
    assert "dbhome_2" in helper
    assert "39618649/39472050" in helper
    assert "oracle_patch_apply_enabled=true" in helper
    assert "oracle_upgrade_prepare_force_rebuild=true" in helper
    assert "--apply" in helper
    assert "--force-rebuild" in helper
    assert "--cutover" in helper
    assert "--limit" in helper
    assert "--extra-vars" in helper
    assert "multi-instance-smoke.yml" in helper
    assert "detach" in helper.lower() or "rebuild" in helper.lower()


def test_remaining_gates_documents_clean_reinstall_prepare():
    gates = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")
    assert "07-upgrade-dual-db-prepare.yml" in gates
    assert "dbhome_2" in gates
    assert "force" in gates.lower() or "rebuild" in gates.lower()
    assert "multi-instance-smoke.yml" in gates
    assert "--limit superdb1" in gates
    # Align with GOAL_AUDIT / STATUS live proof naming.
    assert "standalone `duper`" in gates
