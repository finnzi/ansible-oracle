"""Filters for resolving per-host Oracle instance definitions."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


def oracle_apply_instance_overrides(
    instances: list[dict[str, Any]] | None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    require_dataguard: bool = True,
) -> list[dict[str, Any]]:
    """Merge host/group overrides into instance dictionaries.

    The inventory carries primary/standby overrides before Data Guard is
    enabled. By default, keep those dormant until ``inst.dataguard`` is true so
    the standalone lab continues to bind its standalone listener name.
    """
    resolved: list[dict[str, Any]] = []
    overrides = overrides or {}

    for inst in instances or []:
        merged = deepcopy(inst)
        name = str(merged.get("name", ""))
        if name and (not require_dataguard or bool(merged.get("dataguard"))):
            merged.update(deepcopy(dict(overrides.get(name, {}))))
        resolved.append(merged)

    return resolved


class FilterModule:
    """Ansible filter plugin entry point."""

    def filters(self) -> dict[str, Any]:
        return {
            "oracle_apply_instance_overrides": oracle_apply_instance_overrides,
        }
