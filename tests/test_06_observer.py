"""Observer-node Oracle Client and Data Guard broker connectivity assertions."""
from __future__ import annotations

import os
import shlex
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVER_HOME = "/observer/app/oracle/client_home1"

pytestmark = pytest.mark.slice


def test_observer_role_installs_client_and_tns_contract():
    playbook = (REPO_ROOT / "playbooks/06-observer.yml").read_text(encoding="utf-8")
    defaults = (
        REPO_ROOT / "roles/oracle_observer/defaults/main.yml"
    ).read_text(encoding="utf-8")
    tasks = (REPO_ROOT / "roles/oracle_observer/tasks/main.yml").read_text(
        encoding="utf-8"
    ) + (REPO_ROOT / "roles/oracle_observer/tasks/client-config.yml").read_text(
        encoding="utf-8"
    )
    tns = (REPO_ROOT / "roles/oracle_observer/templates/tnsnames.ora.j2").read_text(
        encoding="utf-8"
    )
    service = (
        REPO_ROOT / "roles/oracle_observer/templates/fsfo-observer.service.j2"
    ).read_text(encoding="utf-8")
    env = (
        REPO_ROOT / "roles/oracle_observer/templates/fsfo-observer.env.j2"
    ).read_text(encoding="utf-8")
    start = (
        REPO_ROOT / "roles/oracle_observer/templates/fsfo-observer-start.j2"
    ).read_text(encoding="utf-8")
    response = (
        REPO_ROOT / "roles/oracle_observer/templates/client_install.rsp.j2"
    ).read_text(encoding="utf-8")
    meta = (REPO_ROOT / "roles/oracle_observer/meta/main.yml").read_text(
        encoding="utf-8"
    )

    assert "oracle_observer_install_client: true" in playbook
    assert "oracle_observer_install_client: false" in defaults
    assert "oracle_observer_enabled: false" in defaults
    assert "oracle_observer_enabled: true" in (
        REPO_ROOT / "inventory/group_vars/observer.yml"
    ).read_text(encoding="utf-8")
    assert "observer_create_ol9_linker_compat_symlink: true" in defaults
    assert "observer_dg_connect_identifier: super_dgb" in defaults
    assert "observer_dg_primary_unique_name: super" in defaults
    assert "observer_dg_standby_unique_name: super_sby" in defaults
    assert "observer_dg_standby_connect_identifier: super_sby_dgb" in defaults
    assert "observer_sysdg_password: \"{{ oracle_lab_dg_password" in defaults
    assert "Verify the client installer zip is staged" in tasks
    assert "Run Oracle Client installer for observer" in tasks
    assert "Write native client aliases and broker aliases" in tasks
    assert "Validate observer DGMGRL can inspect Data Guard broker" in tasks
    assert "Configure Fast-Start Failover target and threshold" in tasks
    assert "ENABLE FAST_START FAILOVER" in tasks
    assert "Enable and start FSFO observer service" in tasks
    assert "Validate Fast-Start Failover observer status" in tasks
    assert "observer_create_ol9_linker_compat_symlink | bool" in tasks
    assert "Protection Mode: MaxAvailability" in tasks
    assert "is reserved for the full FSFO lifecycle" not in tasks
    assert "role: oracle_common" in meta
    assert "oracle.install.client.installType={{ observer_install_type }}" in response
    assert "{{ observer_dg_connect_identifier }} =" in tns
    assert "{{ observer_dg_standby_connect_identifier }} =" in tns
    assert "_DGMGRL" in tns
    assert "DGMGRL_CONNECT={{ observer_sysdg_user }}/{{ observer_sysdg_password }}" in env
    assert "Type=simple" in service
    assert "Restart=on-failure" in service
    assert "EnvironmentFile=/etc/sysconfig/{{ observer_service_name }}" in service
    assert "START OBSERVER ${OBSERVER_NAME} FILE IS" in start
    assert "IN BACKGROUND" not in start


def test_observer_client_home_installed(observer_exec):
    r = observer_exec(
        f"test -x {OBSERVER_HOME}/bin/dgmgrl && "
        f"test -x {OBSERVER_HOME}/bin/sqlplus && "
        f"test -f {OBSERVER_HOME}/.install_complete"
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_observer_tns_aliases_reach_both_dataguard_sites(observer_exec):
    tns = observer_exec(f"cat {OBSERVER_HOME}/network/admin/tnsnames.ora")
    assert tns.returncode == 0, tns.stderr
    assert "super_dgb" in tns.stdout
    assert "super_sby_dgb" in tns.stdout
    assert "HOST = superdc1.domain.is" in tns.stdout
    assert "HOST = superdc2.domain.is" in tns.stdout
    assert "SERVICE_NAME = super_DGMGRL" in tns.stdout
    assert "SERVICE_NAME = super_sby_DGMGRL" in tns.stdout

    hosts = observer_exec("getent hosts superdc1.domain.is superdc2.domain.is")
    assert hosts.returncode == 0, hosts.stderr
    assert "192.168.87.31" in hosts.stdout
    assert "192.168.87.32" in hosts.stdout


def test_observer_dgmgrl_can_inspect_broker(observer_exec):
    sys_password = os.environ.get("ORACLE_TEST_PASSWORD", "SysPassword1_")
    connect_identifier = shlex.quote(f"sys/{sys_password}@super_dgb")
    cmd = (
        f"export ORACLE_HOME={OBSERVER_HOME} "
        f"TNS_ADMIN={OBSERVER_HOME}/network/admin && "
        f"$ORACLE_HOME/bin/dgmgrl -silent {connect_identifier} "
        "'SHOW CONFIGURATION'"
    )
    last = None
    for _ in range(18):
        last = observer_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=120)
        assert last.returncode == 0, last.stdout + last.stderr
        if (
            "SUCCESS" in last.stdout
            and "ORA-" not in last.stdout
            and "Error:" not in last.stdout
        ):
            break
        time.sleep(10)
    assert last is not None
    assert "Configuration - dg_super" in last.stdout
    assert "Protection Mode: MaxAvailability" in last.stdout
    assert "SUCCESS" in last.stdout
    assert "super_sby" in last.stdout
    assert "ORA-" not in last.stdout
    assert "Error:" not in last.stdout


def test_fast_start_failover_enabled(observer_exec):
    sys_password = os.environ.get("ORACLE_TEST_PASSWORD", "SysPassword1_")
    connect_identifier = shlex.quote(f"sys/{sys_password}@super_dgb")
    service = observer_exec(
        "systemctl is-enabled oracle-fsfo-observer.service && "
        "systemctl is-active oracle-fsfo-observer.service"
    )
    assert service.returncode == 0, service.stdout + service.stderr
    assert "enabled" in service.stdout
    assert "active" in service.stdout

    cmd = (
        f"export ORACLE_HOME={OBSERVER_HOME} "
        f"TNS_ADMIN={OBSERVER_HOME}/network/admin && "
        f"$ORACLE_HOME/bin/dgmgrl -silent {connect_identifier} "
        "'SHOW FAST_START FAILOVER'"
    )
    last = None
    for _ in range(18):
        last = observer_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=120)
        assert last.returncode == 0, last.stdout + last.stderr
        if (
            "Fast-Start Failover: Enabled" in last.stdout
            and "Observer:" in last.stdout
            and "Observer:           (none)" not in last.stdout
            and "ORA-" not in last.stdout
            and "Error:" not in last.stdout
        ):
            break
        time.sleep(10)
    assert last is not None
    assert "Fast-Start Failover: Enabled" in last.stdout
    assert "Protection Mode:    MaxAvailability" in last.stdout
    assert "Active Target:      super_sby" in last.stdout
    assert "Observer:           (none)" not in last.stdout
    assert "ORA-" not in last.stdout
    assert "Error:" not in last.stdout
