"""Tests for host/group Oracle instance override resolution."""
from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FILTER_PATH = REPO_ROOT / "filter_plugins/oracle_instances.py"

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
            "db_unique_name": "super_pri",
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


def test_overrides_do_not_mutate_source_instances():
    instances = [{"name": "super", "dataguard": True}]
    overrides = {"super": {"listener_vip": "superdc1.domain.is"}}

    oracle_instances_filter.oracle_apply_instance_overrides(instances, overrides)

    assert "listener_vip" not in instances[0]


def test_ansible_config_loads_filter_plugins():
    ansible_cfg = (REPO_ROOT / "ansible.cfg").read_text(encoding="utf-8")

    assert "filter_plugins = filter_plugins" in ansible_cfg
