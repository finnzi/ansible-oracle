"""Role-service and native client availability contracts."""
from __future__ import annotations

import shlex
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_client_availability_contract_is_wired():
    inventory = (REPO_ROOT / "inventory/group_vars/all.yml").read_text()
    service = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/reconcile-service.yml"
    ).read_text()
    client_tns = (
        REPO_ROOT / "roles/oracle_observer/templates/tnsnames.ora.j2"
    ).read_text()
    playbook = (REPO_ROOT / "playbooks/08-client-availability.yml").read_text()
    helper = (REPO_ROOT / "scripts/run-client-switchover-test.sh").read_text()
    docs = (REPO_ROOT / "CLIENT_AVAILABILITY.md").read_text()

    assert "name: super_pri" in inventory
    assert "role: PHYSICAL_STANDBY" in inventory
    assert "name: super_stb" in inventory
    assert "-failovertype" in service
    assert "-failoverretry" in service
    assert "Service role: " in service
    assert "Prime standby-role service for broker role transitions" in service
    assert "srvctl\" stop service" in service
    assert "{{ observer_client_primary_alias }}" in client_tns
    assert "(TYPE = SELECT)" in client_tns
    assert "(METHOD = BASIC)" in client_tns
    assert "superdc1.domain.is" in client_tns
    assert "superdc2.domain.is" in client_tns
    assert "tasks_from: client-config" in playbook
    assert "--confirm CLIENT_SWITCHOVER" in helper
    assert "CLIENT_HA_POST" in helper
    assert "5000" in helper
    assert "transactions still roll back" in docs
    assert "Application Continuity" in docs


def test_live_role_services_and_client_aliases(lab_exec, standby_exec, observer_exec):
    expected = {
        "super": lab_exec,
        "super_sby": standby_exec,
    }
    states = {}
    for db_unique_name, execute in expected.items():
        command = (
            "/grid/19c/gi_home1/bin/srvctl status service "
            f"-db {db_unique_name} 2>&1; "
            "/grid/19c/gi_home1/bin/srvctl config service "
            f"-db {db_unique_name} -service super_pri; "
            "/grid/19c/gi_home1/bin/srvctl config service "
            f"-db {db_unique_name} -service super_stb"
        )
        result = execute(f"su - oracle -c {shlex.quote(command)}", timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Service role: PRIMARY" in result.stdout
        assert "Failover type: SELECT" in result.stdout
        assert "Failover method: BASIC" in result.stdout
        assert "Service role: PHYSICAL_STANDBY" in result.stdout
        states[db_unique_name] = result.stdout

    assert sum("Service super_pri is running" in value for value in states.values()) == 1
    assert sum("Service super_stb is running" in value for value in states.values()) == 1

    tns = observer_exec(
        "sed -n '/^super_primary =/,/^super_standby =/p' "
        "/observer/app/oracle/client_home1/network/admin/tnsnames.ora"
    )
    assert tns.returncode == 0, tns.stderr
    assert "HOST = superdc1.domain.is" in tns.stdout
    assert "HOST = superdc2.domain.is" in tns.stdout
    assert "SERVICE_NAME = super_pri" in tns.stdout
    assert "TYPE = SELECT" in tns.stdout
