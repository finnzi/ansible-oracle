"""Path-safety helpers for dual-home deinstall and upgrade prepare."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def oracle_normalize_unix_path(path: Any) -> str:
    """Collapse a Unix path without following symlinks or touching the host.

    Relative paths, empty values, and ``..`` components are rejected so a typo
    cannot walk above the intended tree.
    """
    if path is None:
        return ""
    text = str(path).strip()
    if not text:
        return ""
    if not text.startswith("/"):
        raise ValueError(f"path must be absolute: {path!r}")
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"path contains '..': {path!r}")
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def oracle_path_is_ancestor_of(ancestor: Any, descendant: Any) -> bool:
    """True when *ancestor* is *descendant* or a parent directory of it."""
    try:
        parent = oracle_normalize_unix_path(ancestor)
        child = oracle_normalize_unix_path(descendant)
    except ValueError:
        return False
    if not parent or not child:
        return False
    if parent == "/":
        return child != "/"
    return child == parent or child.startswith(parent + "/")


def oracle_deinstall_conflicts(target: Any, protected_paths: Iterable[Any] | None = None) -> list[str]:
    """Return protected paths that recursive removal of *target* would delete."""
    try:
        normalized = oracle_normalize_unix_path(target)
    except ValueError as exc:
        return [f"invalid:{exc}"]
    if not normalized or normalized == "/":
        return ["/"]
    conflicts: list[str] = []
    seen: set[str] = set()
    for raw in protected_paths or []:
        if raw is None or str(raw).strip() == "":
            continue
        try:
            protected = oracle_normalize_unix_path(raw)
        except ValueError:
            continue
        if oracle_path_is_ancestor_of(normalized, protected) and protected not in seen:
            seen.add(protected)
            conflicts.append(protected)
    return conflicts


class FilterModule:
    """Ansible filter plugin entry point."""

    def filters(self) -> dict[str, Any]:
        return {
            "oracle_normalize_unix_path": oracle_normalize_unix_path,
            "oracle_path_is_ancestor_of": oracle_path_is_ancestor_of,
            "oracle_deinstall_conflicts": oracle_deinstall_conflicts,
        }
