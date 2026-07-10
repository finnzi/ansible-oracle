"""Tests for host/group Oracle instance override resolution."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FILTER_PATH = REPO_ROOT / "filter_plugins/oracle_instances.py"
MULTI_INSTANCE_EXAMPLE = REPO_ROOT / "inventory/examples/multi-instance.yml"
MULTI_INSTANCE_SMOKE = REPO_ROOT / "inventory/examples/multi-instance-smoke.yml"

spec = importlib.util.spec_from_file_location("oracle_instances_filter", FILTER_PATH)
assert spec is not None and spec.loader is not None
oracle_instances_filter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle_instances_filter)


def test_overrides_are_dormant_for_standalone_instances():
    instances = [
        {
            "name": "super",
            "dataguard": False,
            "listener_vip": "superdb.domain.is",
        }
    ]
    overrides = {
        "super": {
            "listener_vip": "superdc1.domain.is",
            "db_unique_name": "super",
        }
    }

    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        instances, overrides
    )

    assert resolved[0]["listener_vip"] == "superdb.domain.is"
    assert "db_unique_name" not in resolved[0]


def test_overrides_apply_for_dataguard_instances():
    instances = [
        {
            "name": "super",
            "dataguard": True,
            "listener_vip": "superdb.domain.is",
        }
    ]
    overrides = {
        "super": {
            "listener_vip": "superdc2.domain.is",
            "db_unique_name": "super_sby",
            "dg_role": "standby",
        }
    }

    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        instances, overrides
    )

    assert resolved[0]["listener_vip"] == "superdc2.domain.is"
    assert resolved[0]["db_unique_name"] == "super_sby"
    assert resolved[0]["dg_role"] == "standby"


def test_string_false_disables_dataguard_requirement_for_cli_extra_vars():
    instances = [{"name": "super", "dataguard": False}]
    overrides = {"super": {"dataguard": True, "dg_role": "standby"}}

    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        instances, overrides, require_dataguard="false"
    )

    assert resolved[0]["dataguard"] is True
    assert resolved[0]["dg_role"] == "standby"


def test_string_true_keeps_overrides_dormant_for_standalone_instances():
    instances = [{"name": "super", "dataguard": False}]
    overrides = {"super": {"dataguard": True, "dg_role": "standby"}}

    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        instances, overrides, require_dataguard="true"
    )

    assert resolved[0] == {"name": "super", "dataguard": False}


def test_overrides_do_not_mutate_source_instances():
    instances = [{"name": "super", "dataguard": True}]
    overrides = {"super": {"listener_vip": "superdc1.domain.is"}}

    oracle_instances_filter.oracle_apply_instance_overrides(instances, overrides)

    assert "listener_vip" not in instances[0]


def test_ansible_config_loads_filter_plugins():
    ansible_cfg = (REPO_ROOT / "ansible.cfg").read_text(encoding="utf-8")

    assert "filter_plugins = filter_plugins" in ansible_cfg


def test_multi_instance_example_uses_distinct_instance_identities():
    example = yaml.safe_load(MULTI_INSTANCE_EXAMPLE.read_text(encoding="utf-8"))
    instances = example["oracle_instances"]

    assert [inst["name"] for inst in instances] == ["super", "duper", "fluff"]
    assert {inst["oracle_base"] for inst in instances} == {
        "/super/app/oracle",
        "/duper/app/oracle",
        "/fluff/app/oracle",
    }
    assert {inst["listener_vip"] for inst in instances} == {
        "superdb.domain.is",
        "duperdb.domain.is",
        "fluffdb.domain.is",
    }
    assert {inst["listener_port"] for inst in instances} == {1521, 1522, 1523}
    assert {inst["service_name"] for inst in instances} == {
        "super_svc",
        "duper_svc",
        "fluff_svc",
    }
    assert {f"LISTENER_{inst['name'].upper()}" for inst in instances} == {
        "LISTENER_SUPER",
        "LISTENER_DUPER",
        "LISTENER_FLUFF",
    }
    for inst in instances:
        assert inst["dirs"] == {
            "data": f"/{inst['name']}/d01",
            "archive": f"/{inst['name']}/a01",
            "flashback": f"/{inst['name']}/f01",
            "redo": f"/{inst['name']}/r01",
        }
        assert len([home for home in inst["db_homes"] if home["current"]]) == 1
        assert len([home for home in inst["gi_homes"] if home["current"]]) == 1


def test_multi_instance_overrides_only_touch_named_dataguard_instance():
    example = yaml.safe_load(MULTI_INSTANCE_EXAMPLE.read_text(encoding="utf-8"))

    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        example["oracle_instances"],
        example["oracle_instance_overrides"],
    )

    by_name = {inst["name"]: inst for inst in resolved}
    assert by_name["super"]["listener_vip"] == "superdc1.domain.is"
    assert by_name["super"]["db_unique_name"] == "super"
    assert by_name["super"]["dg_role"] == "primary"
    assert by_name["duper"]["listener_vip"] == "duperdb.domain.is"
    assert "db_unique_name" not in by_name["duper"]
    assert by_name["fluff"]["listener_vip"] == "fluffdb.domain.is"
    assert "db_unique_name" not in by_name["fluff"]


def test_multi_instance_example_maps_every_listener_hostname_to_a_lab_vip():
    example = yaml.safe_load(MULTI_INSTANCE_EXAMPLE.read_text(encoding="utf-8"))
    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        example["oracle_instances"],
        example["oracle_instance_overrides"],
    )
    listener_hosts = {inst["listener_vip"] for inst in resolved}

    host_aliases = {
        alias
        for entry in example["oracle_lab_guest_hosts"]
        for alias in entry["names"].split()
    }
    vip_aliases = {
        alias
        for entry in example["oracle_lab_listener_vips"]
        for alias in entry["names"].split()
    }

    assert listener_hosts <= host_aliases
    assert listener_hosts <= vip_aliases


def test_multi_instance_smoke_is_primary_host_super_duper_fluff():
    smoke = yaml.safe_load(MULTI_INSTANCE_SMOKE.read_text(encoding="utf-8"))
    instances = smoke["oracle_instances"]
    resolved = oracle_instances_filter.oracle_apply_instance_overrides(
        instances,
        smoke["oracle_instance_overrides"],
        require_dataguard=False,
    )
    by_name = {inst["name"]: inst for inst in resolved}

    assert [inst["name"] for inst in instances] == ["super", "duper", "fluff"]
    assert smoke["oracle_network_dataguard_enabled"] is True
    assert smoke["oracle_lab_host_map_mode"] == "dataguard"
    assert smoke["oracle_db_manage_apply_instance_overrides_require_dataguard"] is False
    assert smoke["oracle_restart_apply_instance_overrides_require_dataguard"] is False
    assert smoke["oracle_service_apply_instance_overrides_require_dataguard"] is False
    assert by_name["super"]["dataguard"] is True
    assert by_name["super"]["listener_vip"] == "superdc1.domain.is"
    assert by_name["duper"]["dataguard"] is False
    assert by_name["duper"]["listener_vip"] == "duperdb.domain.is"
    assert by_name["duper"]["listener_port"] == 1522
    assert by_name["duper"]["service_name"] == "duper_svc"
    assert by_name["fluff"]["dataguard"] is False
    assert by_name["fluff"]["archivelog"] is False
    assert by_name["fluff"]["force_logging"] is False
    assert by_name["fluff"]["listener_vip"] == "fluffdb.domain.is"
    assert by_name["fluff"]["listener_port"] == 1523
    assert by_name["fluff"]["service_name"] == "fluff_svc"

    vip_aliases = {
        alias
        for entry in smoke["oracle_lab_listener_vips"]
        for alias in entry["names"].split()
    }
    assert {inst["listener_vip"] for inst in resolved} <= vip_aliases
