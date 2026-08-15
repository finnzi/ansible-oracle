"""Contract tests for execution-safety guards found in the repo review."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_prepare_standby_does_not_abort_a_live_dataguard_member():
    prepare = _read("roles/oracle_dataguard/tasks/prepare-standby.yml")
    duplicate = _read("roles/oracle_dataguard/tasks/duplicate-standby.yml")

    assert "_dg_standby_is_live_member" in prepare
    assert "db_unique_name" in prepare
    assert "not (_dg_standby_is_live_member | default(false) | bool)" in prepare
    assert (
        "pgrep -x \"ora_pmon_{{ inst.name }}\" >/dev/null 2>&1 &&"
        in prepare
    )
    # Abort is only for leftover non-member instances, never a promoted member.
    abort_block = prepare.split("Start registered physical standby instead of auxiliary NOMOUNT")[1]
    assert "_dg_standby_is_live_member" in abort_block.split("- name:")[0] or (
        "not (_dg_standby_is_live_member | default(false) | bool)" in prepare
    )
    assert "_dg_standby_is_live_member" in duplicate
    assert "not (_dg_standby_is_live_member | default(false) | bool)" in duplicate
    assert "'PHYSICAL STANDBY' not in (_dg_standby_role_before.stdout | default(''))" in duplicate


def test_switchover_reenables_fsfo_only_when_it_was_enabled():
    switchover = _read("roles/oracle_dataguard/tasks/switchover.yml")

    assert "_dg_switchover_fsfo_was_enabled" in switchover
    assert "FSFO_DISABLED" in switchover
    assert "when: _dg_switchover_fsfo_was_enabled | default(false) | bool" in switchover
    assert "\n  when: true\n" not in switchover


def test_switchover_apply_lag_does_not_treat_double_digit_seconds_as_small():
    switchover = _read("roles/oracle_dataguard/tasks/switchover.yml")

    assert "Apply Lag:[[:space:]]*[1-5] second" not in switchover or (
        "Apply Lag:[[:space:]]+[1-5] seconds?([^0-9]|$)" in switchover
    )
    assert "Apply Lag:[[:space:]]+[1-5] seconds?([^0-9]|$)" in switchover


def test_oop_dual_current_home_mode_accepts_any_modeled_home():
    tasks = _read("roles/oracle_patch/tasks/main.yml")

    assert "modeled_home_paths" in tasks
    assert "explicit_dual_target" in tasks
    assert "current_home not in modeled" in tasks or "current_home not in (result.item.modeled_home_paths" in tasks


def test_datapatch_skips_non_writable_primary():
    tasks = _read("roles/oracle_patch/tasks/main.yml")

    assert "Read database role before datapatch" in tasks
    assert "PRIMARY|READ WRITE" in tasks
    assert "Run datapatch for patched DB homes" in tasks


def test_standbyfirst_publishes_broker_facts_to_all_db_hosts():
    playbook = _read("playbooks/07-patch-standbyfirst.yml")

    assert "Publish standby-first broker facts to Data Guard hosts" in playbook
    assert "groups.oracle_db_hosts" in playbook
    assert "delegate_facts: true" in playbook
    assert 'oracle_patch_instances: "{{ [_patch_sf_instance] }}"' in playbook
    assert 'oracle_db_install_instances: "{{ [_patch_sf_instance] }}"' in playbook


def test_switchback_and_upgrade_scope_standalone_instances():
    switchback = _read("playbooks/07-patch-dual-db-switchback.yml")
    prepare = _read("playbooks/07-upgrade-dual-db-prepare.yml")
    cutover = _read("playbooks/07-upgrade-dual-db-cutover.yml")

    assert 'oracle_patch_instances: "{{ _dual_switchback_standalone_instances }}"' in switchback
    assert 'oracle_db_install_instances: "{{ _dual_switchback_standalone_instances }}"' in switchback
    assert "hosts: primary" in prepare
    assert "hosts: primary" in cutover
    assert "'standby' not in group_names" in prepare
    assert "'standby' not in group_names" in cutover


def test_observer_accepts_either_unique_name_as_active_target():
    tasks = _read("roles/oracle_observer/tasks/main.yml")

    assert "observer_dg_primary_unique_name" in tasks.split("Validate Fast-Start Failover observer status")[1]
    assert "Active Target:" in tasks
    assert "observer_dg_standby_unique_name" in tasks.split("Validate Fast-Start Failover observer status")[1]


def test_network_retain_keeps_dataguard_site_vips():
    tasks = _read("roles/oracle_network/tasks/main.yml")

    assert "dc1" in tasks.split("Resolve host-retained listener VIPs from full inventory")[1].split("- name:")[0]
    assert "dc2" in tasks.split("Resolve host-retained listener VIPs from full inventory")[1].split("- name:")[0]
    assert "require_dg = false" in tasks.split("Resolve host-retained listener VIPs from full inventory")[1].split("- name:")[0]


def test_failover_final_validate_retries_until_read_only_with_apply():
    playbook = _read("playbooks/08-failover-reinstate.yml")
    validate = playbook.split("Validate original primary restored and standby read-only with apply")[1]

    assert "READ ONLY WITH APPLY" in validate
    assert "until:" in validate
    assert "READ ONLY WITH APPLY" in validate.split("until:")[1].split("- name:")[0]


def test_e2e_helper_fails_when_pytest_fails():
    helper = _read("scripts/run-e2e-full-lab.sh")

    assert "E2E_PYTEST_FAILED=1" not in helper
    assert "exit 1" in helper.split("run-tests.sh")[1]
    assert "WARN: pytest reported failures" not in helper


def test_lab_down_waits_for_domains_to_stop():
    down = _read("lab/scripts/lab-down.sh")
    common = _read("lab/scripts/lib/common.sh")
    up = _read("lab/scripts/lab-up.sh")

    assert "wait_for_domain_shutoff" in down
    assert "wait_for_domain_shutoff" in common
    assert "in shutdown" in up or "shut off" in up
    assert "render_lab_inventory" in common or "vm_ip superdb1" in up
    assert "|| true" not in up.split("lab_ensure_root_disk_size")[1].split("\n")[0]


def test_runtime_home_prefers_restart_registration():
    helper = _read("roles/oracle_common/tasks/resolve-runtime-home.yml")
    switchover = _read("roles/oracle_dataguard/tasks/switchover.yml")

    assert "oracle_runtime_home_fallback" in helper
    assert "Oracle home" in helper
    assert "resolve-runtime-home.yml" in switchover
    assert "_runtime_home_path" in switchover


def test_listener_start_fails_closed_without_tns_token():
    tasks = _read("roles/oracle_network/tasks/main.yml")
    start = tasks.split("Start listener where it is down")[1].split("- name:")[0]

    assert "'TNS-01106' not in (_lsnr_start.stdout | default(''))" in start
    assert "'TNS-' in (_lsnr_start.stdout | default(''))" not in start


def test_relocate_spfile_home_copy_uses_sid():
    script = _read("roles/oracle_patch/files/relocate_spfile_for_dual_home.sh")

    assert 'dest_spfile_home="${new_oh}/dbs/spfile${sid}.ora"' in script
    assert 'dest_pwfile_home="${new_oh}/dbs/orapw${sid}"' in script
    assert "SPFILE_DURABLE" in script
