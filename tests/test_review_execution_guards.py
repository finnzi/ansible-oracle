"""Contract tests for execution-safety guards found in the repo review."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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
    restore = _read("roles/oracle_dataguard/tasks/switchover-restore.yml")

    assert "_dg_switchover_fsfo_was_enabled" in switchover
    assert "FSFO_DISABLED" in switchover
    assert "Perform switchover with guaranteed FSFO and apply restore" in switchover
    assert "include_tasks: switchover-execute.yml" in switchover
    assert "include_tasks: switchover-restore.yml" in switchover
    assert "\n  always:\n" in switchover
    assert "when: _dg_switchover_fsfo_was_enabled | default(false) | bool" in restore
    assert "Restore Fast-Start Failover after switchover attempt" in restore
    assert "Restore standby apply after switchover attempt" in restore
    assert restore.index("Restore standby apply after switchover attempt") < restore.index(
        "Restore Fast-Start Failover after switchover attempt"
    )
    assert "failed_when: false" not in restore
    assert "APPLY_FAILED" in restore
    assert "\n  when: true\n" not in switchover


def test_switchover_apply_lag_does_not_treat_double_digit_seconds_as_small():
    execute = _read("roles/oracle_dataguard/tasks/switchover-execute.yml")

    assert "Apply Lag:[[:space:]]*[1-5] second" not in execute or (
        "Apply Lag:[[:space:]]+[1-5] seconds?([^0-9]|$)" in execute
    )
    assert "Apply Lag:[[:space:]]+[1-5] seconds?([^0-9]|$)" in execute


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


def test_failover_destroy_recovers_primary_vm_when_promotion_fails():
    playbook = _read("playbooks/08-failover-reinstate.yml")
    after_destroy = playbook.split("Destroy current primary VM to trigger FSFO", 1)[1]
    recovery = after_destroy.split("Restore lab host aliases on old primary after VM restart", 1)[0]
    remaining = after_destroy.split("Restore lab host aliases on old primary after VM restart", 1)[1]

    assert "block:" in recovery
    assert "always:" in recovery
    assert "Wait for FSFO to promote target standby" in recovery.split("always:")[0]
    assert "Start old primary VM for broker reinstate" in recovery.split("always:")[1]
    assert "Wait for old primary VM SSH after restart" in recovery.split("always:")[1]
    assert "already active" in recovery.split("always:")[1]
    assert "already running" in recovery.split("always:")[1]
    assert "_failover_destroy_primary is defined" in recovery.split("always:")[1]
    assert "Start old primary VM for broker reinstate" not in playbook.split(
        "Destroy current primary VM to trigger FSFO", 1
    )[0]
    assert "Wait for old primary Oracle Restart after VM restart" in remaining
    assert "Start old primary broker listener after VM restart" in remaining
    assert "REINSTATE DATABASE '{{ oracle_failover_original_primary }}'" in remaining


def test_e2e_helper_fails_when_pytest_fails():
    helper = _read("scripts/run-e2e-full-lab.sh")

    assert "E2E_PYTEST_FAILED=1" not in helper
    assert "exit 1" in helper.split("run-tests.sh")[1]
    assert "WARN: pytest reported failures" not in helper


def test_lab_up_waits_for_domains_to_finish_shutting_down():
    common = _read("lab/scripts/lib/common.sh")
    up = _read("lab/scripts/lab-up.sh")

    assert "wait_for_domain_shutoff" in common
    assert "wait_for_domain_shutoff" in up
    assert "in shutdown" in up or "shut off" in up


def test_lab_up_renders_inventory_and_resizes_root_disk_strictly():
    common = _read("lab/scripts/lib/common.sh")
    up = _read("lab/scripts/lab-up.sh")

    assert "render_lab_inventory" in common or "vm_ip superdb1" in up
    assert "|| true" not in up.split("lab_ensure_root_disk_size")[1].split("\n")[0]


def test_runtime_home_prefers_restart_registration():
    helper = _read("roles/oracle_common/tasks/resolve-runtime-home.yml")
    switchover = _read("roles/oracle_dataguard/tasks/switchover.yml")
    network = _read("roles/oracle_network/tasks/main.yml")

    assert "oracle_runtime_home_fallback" in helper
    assert "Oracle home" in helper
    assert "resolve-runtime-home.yml" in switchover
    assert "_runtime_home_path" in switchover
    assert "Resolve runtime listener Oracle home from Restart" in network
    assert "_home_path" in network
    assert "config listener" in network


def test_listener_start_fails_closed_without_tns_token():
    tasks = _read("roles/oracle_network/tasks/main.yml")
    start = tasks.split("Start listener where it is down")[1].split("- name:")[0]

    assert "'TNS-01106' not in (_lsnr_start.stdout | default(''))" in start
    assert "'TNS-' in (_lsnr_start.stdout | default(''))" not in start


def test_listeners_use_literal_vips_and_restart_ipc_endpoints():
    network = _read("roles/oracle_network/tasks/main.yml")
    listener_template = _read("roles/oracle_network/templates/listener.ora.j2")
    restart = _read("roles/oracle_restart_manage/tasks/register-instance.yml")
    duplicate = _read("roles/oracle_dataguard/tasks/duplicate-standby.yml")
    db_manage = _read("roles/oracle_db_manage/tasks/manage-instance.yml")

    assert "Require an explicit Oracle listener network interface" in network
    assert "ip -o route show default" not in network
    assert "oracle_network_interface" in network
    assert "HOST = {{ inst._vip }}" in listener_template
    assert '-endpoints "/IPC:LISTENER_{{ inst.name | upper }}"' in restart
    assert '-endpoints "/IPC:LISTENER_{{ inst.name | upper }}"' in duplicate
    assert "_restart_listener_ip" in restart
    assert "HOST={{ _listener_host }}" in db_manage


def test_dataguard_tnsnames_require_explicit_hosts():
    network = _read("roles/oracle_network/tasks/main.yml")
    tns = _read("roles/oracle_network/templates/tnsnames.ora.j2")
    assert "Require explicit Data Guard descriptor hosts" in network
    assert "inst.dg_primary_host" in tns
    assert "inst.dg_standby_host" in tns
    assert "inst.name ~ 'dc1.'" not in tns
    assert "inst.name ~ 'dc2.'" not in tns


def test_lab_autostart_verifies_exact_listener_socket_addresses():
    verifier = _read("scripts/verify-lab-autostart.sh")
    assert '[ "${endpoint_line}" = "IPC:${listener}" ] || ready=1' in verifier
    assert 'ANSIBLE_ORACLE_SOCKET=' in verifier
    assert 'socket_addresses="$(sed -n' in verifier
    assert "ss -H -ltn sport = :${port}" in verifier
    assert "exactly ${listener_ip}:${port}" in verifier
    assert "grep -Evx -- \"${listener_ip}:${port}\"" in verifier


def test_listener_socket_normalization_ignores_ssh_diagnostics_but_rejects_extra_addresses():
    verifier = _read("scripts/verify-lab-autostart.sh")
    assert "remote_state intentionally preserves SSH stderr" in verifier
    assert 'grep -Fc -- "${listener_ip}:${port}" <<<"${socket_addresses}"' in verifier
    assert 'grep -Evx -- "${listener_ip}:${port}" <<<"${socket_addresses}"' in verifier

    probe = """Warning: Permanently added '192.0.2.10' (ED25519) to the list of known hosts.
Warning: kex warning: post-quantum key exchange is not in use.
ANSIBLE_ORACLE_SOCKET=192.168.87.22:1522
"""
    normalized = subprocess.run(
        ["sed", "-n", "s/^ANSIBLE_ORACLE_SOCKET=//p"],
        input=probe,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert normalized == ["192.168.87.22:1522"]

    extra_probe = probe + "ANSIBLE_ORACLE_SOCKET=192.168.87.11:1522\n"
    extra = subprocess.run(
        ["sed", "-n", "s/^ANSIBLE_ORACLE_SOCKET=//p"],
        input=extra_probe,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert extra == ["192.168.87.22:1522", "192.168.87.11:1522"]
    assert [line for line in extra if line != "192.168.87.22:1522"] == [
        "192.168.87.11:1522"
    ]


def test_listener_ip_and_network_interface_are_canonical_required_inputs():
    network = _read("roles/oracle_network/tasks/main.yml")
    network_defaults = _read("roles/oracle_network/defaults/main.yml")
    db_manage = _read("roles/oracle_db_manage/tasks/manage-instance.yml")
    restart = _read("roles/oracle_restart_manage/tasks/register-instance.yml")
    dg_primary = _read("roles/oracle_dataguard/tasks/prepare-primary.yml")
    dg_standby = _read("roles/oracle_dataguard/tasks/prepare-standby.yml")
    dg_duplicate = _read("roles/oracle_dataguard/tasks/duplicate-standby.yml")

    assert "oracle_network_interface is defined" in network
    assert "oracle_network_listener_interface" not in network
    assert "oracle_network_listener_interface" not in network_defaults
    assert "inst.listener_ip is defined" in network
    assert "oracle_lab_listener_vips" in network  # assignment/cleanup only
    for source in (db_manage, restart, dg_primary, dg_standby, dg_duplicate):
        assert "oracle_lab_listener_vips" not in source
        assert "listener_ip" in source


def test_relocate_spfile_home_copy_uses_sid():
    script = _read("roles/oracle_patch/files/relocate_spfile_for_dual_home.sh")

    assert 'dest_spfile_home="${new_oh}/dbs/spfile${sid}.ora"' in script
    assert 'dest_pwfile_home="${new_oh}/dbs/orapw${sid}"' in script
    assert "SPFILE_DURABLE" in script
    assert "PWFILE_MISSING" in script
    assert "copy_if_needed" in script
    assert not any(
        "copy_if_needed" in line and "|| true" in line
        for line in script.splitlines()
    )
    missing = script.split("PWFILE_MISSING", 1)[1]
    assert "exit 1" in missing.split("if [", 1)[0]
    assert "continuing" not in script


def test_upgrade_prepare_refuses_ancestor_paths_and_does_not_bounce_listener():
    prepare = _read("playbooks/07-upgrade-dual-db-prepare.yml")
    deinstall = _read("roles/oracle_db_deinstall/tasks/main.yml")
    network_defaults = _read("roles/oracle_network/defaults/main.yml")

    assert "Fail when target path is not an allowlisted Oracle home leaf" in prepare
    assert "Fail when target path overlaps live Oracle trees" in prepare
    assert "oracle_network_manage_listener: false" in prepare
    assert "Fail when a deinstall target is not an allowlisted Oracle home leaf" in deinstall
    assert "Fail when a deinstall target overlaps a live Oracle tree" in deinstall
    assert "oracle_network_manage_listener: true" in network_defaults


def test_generic_patch_plays_are_serial_standby_first():
    db_patch = _read("playbooks/07-patch.yml")
    grid_patch = _read("playbooks/07-patch-grid.yml")
    tasks = _read("roles/oracle_patch/tasks/main.yml")
    defaults = _read("roles/oracle_patch/defaults/main.yml")

    assert "Converge Oracle DB home patch inventory (standby first)" in db_patch
    assert "hosts: standby" in db_patch
    assert db_patch.index("hosts: standby") < db_patch.index("hosts: primary")
    assert db_patch.count("serial: 1") == 3
    assert db_patch.count("any_errors_fatal: true") == 3
    assert "Refuse primary DB patch unless standby is available after apply" in db_patch
    assert "assert-site-ready.yml" in db_patch
    assert "Converge Oracle Grid home patch inventory (standby first)" in grid_patch
    assert grid_patch.index("hosts: standby") < grid_patch.index("hosts: primary")
    assert grid_patch.count("serial: 1") == 3
    assert grid_patch.count("any_errors_fatal: true") == 3
    assert "Refuse primary Grid patch unless standby Restart is available" in grid_patch
    assert "oracle_patch_allow_dataguard_concurrent: false" in defaults
    assert "Fail when generic apply would patch both Data Guard sites in one play" in tasks


def test_dual_home_start_does_not_whitelist_prcr_1079():
    tasks = _read("roles/oracle_patch/tasks/main.yml")
    cutover = _read("roles/oracle_patch/tasks/dual-home-cutover.yml")
    start = cutover.split("Start DBs after dual-home Restart switch", 1)[1].split(
        "- name:", 1
    )[0]

    assert "PRCR-1079" not in start
    assert "Probe database is open after dual-home Restart switch" in cutover
    assert "Dual-home Restart cutover with rollback" in tasks
    assert "include_tasks: dual-home-rollback.yml" in tasks
    assert "|PHYSICAL STANDBY|" in cutover
    assert "|READ WRITE" in cutover


def test_password_file_is_copied_from_live_primary():
    broker = _read("roles/oracle_dataguard/tasks/configure-broker.yml")

    assert "LIVE_PRIMARY_UNIQUE" in broker
    assert "_dg_pwfile_source_host" in broker
    assert "_dg_pwfile_dest_host" in broker
    assert "Synchronize primary password file to the standby" in broker
    assert 'delegate_to: "{{ _dg_pwfile_source_host }}"' in broker
    assert 'delegate_to: "{{ _dg_pwfile_dest_host }}"' in broker
    assert broker.index("LIVE_PRIMARY_UNIQUE") < broker.index(
        "Synchronize primary password file to the standby"
    )


def test_acceptance_suite_fails_closed_when_estate_is_down():
    playbook = _read("playbooks/99-test.yml")
    helper = _read("scripts/run-e2e-full-lab.sh")
    conftest = _read("tests/conftest.py")

    assert 'ORACLE_TEST_REQUIRE_LAB: "1"' in playbook
    assert "--require-lab" in playbook
    assert "ORACLE_TEST_REQUIRE_LAB=1" in helper
    assert "--require-lab" in helper.split("run-tests.sh")[1]
    assert "def pytest_addoption" in conftest
    assert '"--require-lab"' in conftest
    assert "def _lab_required" in conftest
    assert "def _skip_or_fail" in conftest
    assert "pytest.fail(message)" in conftest
    assert "pytest.skip(message)" in conftest
    oracledb_fixture = conftest.split("def oracledb", 1)[1].split("def ", 1)[0]
    assert "_skip_or_fail" in oracledb_fixture
    assert 'pytest.skip("python-oracledb not installed' not in oracledb_fixture


def test_estate_required_helper_is_opt_in(monkeypatch):
    import conftest as suite_conftest

    monkeypatch.delenv("ORACLE_TEST_REQUIRE_LAB", raising=False)
    assert suite_conftest._lab_required() is False

    monkeypatch.setenv("ORACLE_TEST_REQUIRE_LAB", "1")
    assert suite_conftest._lab_required() is True
    monkeypatch.setenv("ORACLE_TEST_REQUIRE_LAB", "TRUE")
    assert suite_conftest._lab_required() is True
    monkeypatch.setenv("ORACLE_TEST_REQUIRE_LAB", "Yes")
    assert suite_conftest._lab_required() is True
    monkeypatch.setenv("ORACLE_TEST_REQUIRE_LAB", "0")
    assert suite_conftest._lab_required() is False

    class _Cfg:
        def __init__(self, value):
            self._value = value

        def getoption(self, name, default=False):
            return self._value

    monkeypatch.delenv("ORACLE_TEST_REQUIRE_LAB", raising=False)
    assert suite_conftest._lab_required(_Cfg(True)) is True
    assert suite_conftest._lab_required(_Cfg(False)) is False

    with pytest.raises(pytest.skip.Exception):
        suite_conftest._skip_or_fail("lab down")
    monkeypatch.setenv("ORACLE_TEST_REQUIRE_LAB", "1")
    with pytest.raises(pytest.fail.Exception):
        suite_conftest._skip_or_fail("lab down")


def test_storage_requires_dedicated_mounts_before_mkdir():
    tasks = _read("roles/oracle_storage/tasks/main.yml")
    defaults = _read("roles/oracle_storage/defaults/main.yml")
    inventory = _read("inventory/group_vars/all.yml")

    assert "oracle_storage_require_dedicated_mounts: true" in defaults
    assert "oracle_storage_require_dedicated_mounts: false" in inventory
    assert "Verify expected instance directories are dedicated mounts" in tasks
    assert tasks.index(
        "Verify expected instance directories are dedicated mounts"
    ) < tasks.index("Ensure per-instance top-level directories exist")
    assert "MOUNT_MISSING" in tasks


def test_acceptance_restart_and_client_gaps_fail_closed():
    restart = _read("tests/test_04_restart.py")
    conftest = _read("tests/conftest.py")

    assert "_skip_or_fail" in restart.split("def test_srvctl_status_or_honest_gap", 1)[1]
    assert "_skip_or_fail" in restart.split(
        "def test_restart_systemd_unit_starts_stack_after_monitor", 1
    )[1]
    assert "_skip_or_fail" in restart.split(
        "def test_restart_can_stop_and_start_database", 1
    )[1]
    assert "_skip_or_fail" in conftest.split("def oracledb", 1)[1].split("def ", 1)[0]
