"""Unit tests for library/oracle_db_facts.py helpers."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "library" / "oracle_db_facts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("oracle_db_facts", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db_facts = _load_module()


def test_resolve_auth_mode_maps_sysdg_to_python_oracledb_constant():
    assert db_facts.resolve_auth_mode_attr("sysdg") == "AUTH_MODE_SYSDGD"
    assert db_facts.resolve_auth_mode_attr("SYSDBA") == "AUTH_MODE_SYSDBA"
    assert db_facts.resolve_auth_mode_attr("sysbackup") == "AUTH_MODE_SYSBKP"
    assert db_facts.resolve_auth_mode_attr("") is None


def test_resolve_auth_mode_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unsupported Oracle authentication role"):
        db_facts.resolve_auth_mode_attr("not-a-role")
