"""Filters for resolving per-host Oracle instance definitions."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


_TRUE_STRINGS = {"true", "yes", "on", "1"}
_FALSE_STRINGS = {"false", "no", "off", "0", "", "none", "null"}


def _ansible_bool(value: Any) -> bool:
    """Coerce booleans the same way operators expect from Ansible extra vars.

    Unrecognized strings such as ``flase`` must not become true. Fail closed so
    a typo cannot silently enable Data Guard overrides.
    """
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _FALSE_STRINGS:
            return False
        if normalized in _TRUE_STRINGS:
            return True
        raise ValueError(
            f"Unrecognized boolean string {value!r}; "
            "use true/false, yes/no, on/off, or 1/0"
        )
    return bool(value)


def oracle_apply_instance_overrides(
    instances: list[dict[str, Any]] | None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    require_dataguard: Any = True,
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
        if "dataguard" in merged:
            merged["dataguard"] = _ansible_bool(merged.get("dataguard"))
        if name and (
            not _ansible_bool(require_dataguard)
            or _ansible_bool(merged.get("dataguard"))
        ):
            merged.update(deepcopy(dict(overrides.get(name, {}))))
            if "dataguard" in merged:
                merged["dataguard"] = _ansible_bool(merged.get("dataguard"))
        resolved.append(merged)

    return resolved


class FilterModule:
    """Ansible filter plugin entry point."""

    def filters(self) -> dict[str, Any]:
        return {
            "oracle_apply_instance_overrides": oracle_apply_instance_overrides,
        }
