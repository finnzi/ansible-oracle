"""Role-service and native client availability contracts."""
from __future__ import annotations

import re
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
    tac_helper = (REPO_ROOT / "scripts/run-tac-fcf-poc.sh").read_text()
    tac_client = (
        REPO_ROOT / "roles/oracle_tac_fcf_poc/files/TacFcfPoc.java"
    ).read_text()
    fan_role = (REPO_ROOT / "roles/oracle_fan_manage/tasks/main.yml").read_text()
    fan_defaults = (REPO_ROOT / "roles/oracle_fan_manage/defaults/main.yml").read_text()
    docs = (REPO_ROOT / "CLIENT_AVAILABILITY.md").read_text()

    assert "name: super_pri" in inventory
    assert "role: PHYSICAL_STANDBY" in inventory
    assert "name: super_stb" in inventory
    assert "-failovertype" in service
    assert "-failoverretry" in service
    assert "'modify', 'service'" in service
    assert "Management policy: AUTOMATIC" in service
    assert "Service role: " in service
    assert "Read Restart service resource profile" in service
    assert "Read Restart service resource status" in service
    inspect_service = service.index("Inspect Restart service configuration")
    resolve_output = service.index("Resolve Restart service command output")
    resolve_probes = service.index("Resolve Restart service registration probes")
    assert inspect_service < resolve_output < resolve_probes
    assert '"{{ _svc_home_path }}/bin/srvctl"' in service
    assert "_svc_home_path ~ '/bin/srvctl'" in service
    assert 'ORACLE_HOME: "{{ _svc_home_path }}"' in service
    assert "oracle_gi_home }}/bin/srvctl" not in service
    assert "_svc_crs_service_exists" in service
    assert "_svc_srvctl_config_output" in service
    assert "_svc_srvctl_config_usable" in service
    assert "_svc_crs_service_contract_ok" in service
    assert "TAF_FAILOVER_DELAY" in service
    assert "AQ_HA_NOTIFICATION" in service
    assert "svc.notification | default(true)" in service
    assert "Fail when an existing Restart service cannot be reconciled safely" in service
    assert "Refusing to mutate an ora.* resource with crsctl" in service
    assert "Fail when a Restart service is absent and srvctl is unavailable" in service
    assert "Accept matching Restart service state without SRVCTL mutation" in service
    assert "Fail when a matching current-role service is not online" in service
    assert "crsctl\" start resource" not in service
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
    assert "name: super_tac" in inventory
    assert "failover_type: AUTO" in inventory
    assert "commit_outcome: true" in inventory
    assert "-replay_init_time" in service
    assert "{{ observer_client_tac_alias }}" in client_tns
    assert 'srvctl", "enable", "ons"' in fan_role
    assert "'ONS daemon is running' not in" in fan_role
    assert "PRKO-0?2458|PRKO-0?2465" in fan_role
    assert "PRKO-00371" not in fan_role
    assert '"-onsremoteport"' in fan_role
    assert '"{{ oracle_fan_remote_port }}"' in fan_role
    assert "PRKO-0?2452" in fan_role
    assert "PRKO-0?2576" in fan_role
    assert "PRKO-0?2569" in fan_role
    for diagnostic in ("PRKO-02576", "PRKO-2576", "PRKO-02569", "PRKO-2569"):
        assert re.search(r"PRKO-0?25(?:76|69)", diagnostic)
    ons_lifecycle = fan_role.split("Read initial Oracle Notification Services state", 1)[1].split(
        "Probe firewalld for remote ONS", 1
    )[0]
    assert "failed_when: false" not in ons_lifecycle
    assert "Classify initial ONS resource probe" in ons_lifecycle
    assert "Fail when ONS status probe reports an operational error" not in ons_lifecycle
    assert "Validate Oracle Notification Services after lifecycle convergence" in ons_lifecycle
    assert "become_user: \"{{ oracle_user }}\"" in ons_lifecycle
    assert "oracle_fan_remote_port: 6200" in fan_defaults
    assert "--confirm TAC_FCF_SWITCHOVER" in tac_helper
    assert "POC_RESULT|fan_down=true|fcf=true" in tac_helper
    assert "oracle.jdbc.replay.OracleDataSourceImpl" in tac_client
    assert "setFastConnectionFailoverEnabled(true)" in tac_client
    assert "FAN_DOWN|" in tac_client


def test_live_role_services_and_client_aliases(lab_exec, standby_exec, observer_exec):
    command = (
            "/grid/19c/gi_home1/bin/crsctl status resource "
            "ora.super.super_pri.svc -t; "
            "/grid/19c/gi_home1/bin/crsctl status resource "
            "ora.super.super_stb.svc -t; "
            "/grid/19c/gi_home1/bin/crsctl status resource "
            "ora.super.super_tac.svc -t; "
            "ORACLE_HOME=/super/app/oracle/dbhome_1 "
            "/super/app/oracle/dbhome_1/bin/srvctl config service "
            "-db super -service super_pri; "
            "ORACLE_HOME=/super/app/oracle/dbhome_1 "
            "/super/app/oracle/dbhome_1/bin/srvctl config service "
            "-db super -service super_stb; "
            "ORACLE_HOME=/super/app/oracle/dbhome_1 "
            "/super/app/oracle/dbhome_1/bin/srvctl config service "
            "-db super -service super_tac; "
            "/grid/19c/gi_home1/bin/srvctl status ons"
    )
    primary = lab_exec(f"su - oracle -c {shlex.quote(command)}", timeout=90)
    assert primary.returncode == 0, primary.stdout + primary.stderr
    assert "Service role: PRIMARY" in primary.stdout
    assert "Failover type: SELECT" in primary.stdout
    assert "Failover method: BASIC" in primary.stdout
    assert "Service role: PHYSICAL_STANDBY" in primary.stdout
    assert "Failover type: AUTO" in primary.stdout
    assert "Commit Outcome: true" in primary.stdout
    assert "Failover restore: LEVEL1" in primary.stdout
    assert "ora.super.super_pri.svc\n      1        ONLINE  ONLINE" in primary.stdout
    assert "ora.super.super_stb.svc\n      1        OFFLINE OFFLINE" in primary.stdout
    assert "ora.super.super_tac.svc\n      1        ONLINE  ONLINE" in primary.stdout
    assert "ONS daemon is running" in primary.stdout

    # Verify the public SRVCTL view first, then independently inspect the
    # persisted Oracle Restart resource properties through read-only CRSCTL.
    standby = standby_exec(
        "su - oracle -c 'ORACLE_HOME=/super/app/oracle/dbhome_1 "
        "/super/app/oracle/dbhome_1/bin/srvctl config service -db super_sby'; "
        "/grid/19c/gi_home1/bin/crsctl status resource "
        "-w 'TYPE = ora.service.type' -p; "
        "/grid/19c/gi_home1/bin/crsctl status resource "
        "ora.super_sby.super_pri.svc -t; "
        "/grid/19c/gi_home1/bin/crsctl status resource "
        "ora.super_sby.super_stb.svc -t; "
        "su - oracle -c '/grid/19c/gi_home1/bin/srvctl status ons'",
        timeout=90,
    )
    assert standby.returncode == 0, standby.stdout + standby.stderr
    assert "NAME=ora.super_sby.super_pri.svc" in standby.stdout
    assert "ROLE=PRIMARY" in standby.stdout
    assert "FAILOVER_TYPE=SELECT" in standby.stdout
    assert "FAILOVER_METHOD=BASIC" in standby.stdout
    assert "NAME=ora.super_sby.super_stb.svc" in standby.stdout
    assert "ROLE=PHYSICAL_STANDBY" in standby.stdout
    assert "NAME=ora.super_sby.super_tac.svc" in standby.stdout
    assert "FAILOVER_TYPE=AUTO" in standby.stdout
    assert "COMMIT_OUTCOME=1" in standby.stdout
    assert "FAILOVER_RESTORE=LEVEL1" in standby.stdout
    assert "ora.super_sby.super_pri.svc\n      1        OFFLINE OFFLINE" in standby.stdout
    assert "ora.super_sby.super_stb.svc\n      1        ONLINE  ONLINE" in standby.stdout
    assert "ONS daemon is running" in standby.stdout

    tns = observer_exec(
        "sed -n '/^super_primary =/,/^super_standby =/p' "
        "/observer/app/oracle/client_home1/network/admin/tnsnames.ora"
    )
    assert tns.returncode == 0, tns.stderr
    assert "HOST = superdc1.domain.is" in tns.stdout
    assert "HOST = superdc2.domain.is" in tns.stdout
    assert "SERVICE_NAME = super_pri" in tns.stdout
    assert "TYPE = SELECT" in tns.stdout

    tac = observer_exec(
        "test -f /observer/app/oracle/tac-fcf-poc/TacFcfPoc.class && "
        "sed -n '/^super_tac =/,$p' "
        "/observer/app/oracle/client_home1/network/admin/tnsnames.ora"
    )
    assert tac.returncode == 0, tac.stderr
    assert "SERVICE_NAME = super_tac" in tac.stdout
