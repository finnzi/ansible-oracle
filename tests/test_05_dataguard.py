"""
test_05_dataguard.py — Data Guard assertions.

SKIPPED in the vertical slice: DG creation is scaffolded. These tests assert
the project requirements that will apply once DG lands:
  - broker protection mode is MAXIMUM AVAILABILITY.
  - standby is OPEN READ ONLY WITH APPLY (not MOUNTED).
  - DGMGRL reports the broker configuration healthy.
  - switchover swaps primary/standby roles.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dataguard_defaults_use_maximum_availability():
    defaults_text = (
        REPO_ROOT / "roles/oracle_dataguard/defaults/main.yml"
    ).read_text(encoding="utf-8")

    assert (
        "dg_protection_mode: MAXIMUM AVAILABILITY" in defaults_text
    )


def test_dataguard_inventory_and_network_prerequisites_are_wired():
    all_vars = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(
        encoding="utf-8"
    )
    primary_vars = (REPO_ROOT / "inventory/group_vars/primary.yml").read_text(
        encoding="utf-8"
    )
    standby_vars = (REPO_ROOT / "inventory/group_vars/standby.yml").read_text(
        encoding="utf-8"
    )
    network_tasks = (
        REPO_ROOT / "roles/oracle_network/tasks/main.yml"
    ).read_text(encoding="utf-8")
    listener_template = (
        REPO_ROOT / "roles/oracle_network/templates/listener.ora.j2"
    ).read_text(encoding="utf-8")
    tns_template = (
        REPO_ROOT / "roles/oracle_network/templates/tnsnames.ora.j2"
    ).read_text(encoding="utf-8")
    dataguard_tasks = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/main.yml"
    ).read_text(encoding="utf-8")
    service_tasks = (
        REPO_ROOT / "roles/oracle_service_manage/tasks/main.yml"
    ).read_text(encoding="utf-8")

    assert "superdc1.domain.is superdc1" in all_vars
    assert "superdc2.domain.is superdc2" in all_vars
    assert "listener_vip: \"superdc1.domain.is\"" in primary_vars
    assert "db_unique_name: super_pri" in primary_vars
    assert "listener_vip: \"superdc2.domain.is\"" in standby_vars
    assert "db_unique_name: super_sby" in standby_vars
    assert "oracle_apply_instance_overrides" in network_tasks
    assert "'dc2' if 'standby' in group_names else 'dc1'" in network_tasks
    assert "lab_domain | default('domain.is')" in network_tasks
    assert "oracle_apply_instance_overrides" in dataguard_tasks
    assert "_DGMGRL" in listener_template
    assert "dg_primary_unique = inst.dg_primary_db_unique_name" in tns_template
    assert "dg_standby_unique = inst.dg_standby_db_unique_name" in tns_template
    assert "inst.name ~ 'dc1.'" in tns_template
    assert "inst.name ~ 'dc2.'" in tns_template
    assert "(FAILOVER = ON)" in tns_template
    assert "(LOAD_BALANCE = OFF)" in tns_template
    assert "SERVICE_NAME = {{ inst.service_name" in tns_template
    assert "dg_primary_unique ~ '_dgb'" in tns_template
    assert "dg_standby_unique ~ '_dgb'" in tns_template
    assert "DGMGRL can create, inspect, and switchover" in tns_template
    assert "Data Guard current-primary service requires Restart ownership" in service_tasks
    assert "would not follow the current primary after" in service_tasks
    assert "oracle_restart_available | default(false)" in service_tasks


@pytest.mark.scaffolded
def test_dataguard_role_present_or_skipped(db_connection):
    """In the slice there is no standby; skip cleanly with a clear reason."""
    cur = db_connection.cursor()
    cur.execute("SELECT database_role FROM v$database")
    role = cur.fetchone()[0]
    cur.close()
    if role == "PRIMARY" and not _dg_configured(db_connection):
        pytest.skip(
            "Data Guard not configured in this slice (oracle_dataguard is "
            "scaffolded). Re-run after DG lands to assert standby READ ONLY WITH APPLY."
        )


@pytest.mark.scaffolded
def test_standby_is_read_only_with_apply(db_connection):
    pytest.skip(
        "Standby open-mode assertion: requires Data Guard (scaffolded). "
        "Will assert open_mode == 'READ ONLY WITH APPLY'."
    )


@pytest.mark.scaffolded
def test_dgmgrrl_configuration_healthy():
    pytest.skip(
        "DGMGRL broker health assertion: requires Data Guard (scaffolded). "
        "Will run `dgmgrl ... SHOW CONFIGURATION`."
    )


@pytest.mark.scaffolded
def test_manual_switchover():
    pytest.skip(
        "Manual switchover assertion: requires Data Guard (scaffolded). "
        "Will run `dgmgrl ... SWITCHOVER TO super_sby` and assert role swap."
    )


def _dg_configured(conn) -> bool:
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM v$database "
            "WHERE database_role IN ('PHYSICAL STANDBY','LOGICAL STANDBY')"
        )
        return cur.fetchone()[0] > 0
    except Exception:
        return False
