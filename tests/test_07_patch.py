"""Oracle DB home patch inventory and convergence assertions."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE_HOME = os.environ.get("ORACLE_TEST_ORACLE_HOME", "/super/app/oracle/db_home1")
EXPECTED_DB_RU = os.environ.get("ORACLE_TEST_DB_RU_PATCH_ID", "39034528")

pytestmark = pytest.mark.slice


def test_patch_role_db_apply_contract():
    defaults = (REPO_ROOT / "roles/oracle_patch/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    tasks = (REPO_ROOT / "roles/oracle_patch/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    playbook = (REPO_ROOT / "playbooks/07-patch.yml").read_text(encoding="utf-8")

    assert "oracle_patch_apply_enabled: false" in defaults
    assert "oracle_patch_expected_patch_ids: []" in defaults
    assert "oracle_patch_target: db" in defaults
    assert "oracle_patch_mode: inplace" in defaults
    assert "oracle_patch_discover_oratab: true" in defaults
    assert "oracle_patch_extra_homes: []" in defaults
    assert "Fail when patch target is not implemented" in tasks
    assert "Resolve expected DB patch IDs" in tasks
    assert "'Database Release Update' in description" in tasks
    assert "selectattr('standby_first'" not in tasks
    assert "Read /etc/oratab DB homes for brownfield patching" in tasks
    assert "Resolve extra brownfield DB patch targets" in tasks
    assert "oracle_patch_extra_homes" in tasks
    assert "Check DB home patch inventory" in tasks
    assert "installed_patch_ids" in tasks
    assert "Fail when patches are missing but apply is disabled" in tasks
    assert "Fail when standby-first orchestration is required but not implemented" in tasks
    assert "Apply DB patch with opatchauto" in tasks
    assert "Run datapatch for patched DB homes" in tasks
    assert "Converge Oracle DB home patch inventory" in playbook


def test_patch_applied_to_db_home(lab_exec):
    cmd = (
        f"export ORACLE_HOME={ORACLE_HOME} && "
        f"{ORACLE_HOME}/OPatch/opatch lspatches"
    )
    r = lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert EXPECTED_DB_RU in r.stdout
    assert "Database Release Update" in r.stdout
    assert "OPatch succeeded" in r.stdout


def test_patch_playbook_converges_when_ru_already_present():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/07-patch.yml",
        "-e",
        "oracle_patch_apply_enabled=true",
    ]
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    env.setdefault("XDG_CACHE_HOME", "/tmp/ansible-cache")
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout


def test_dual_home_switch():
    pytest.skip(
        "Dual-home patching is not implemented yet. Once implemented, this asserts "
        "srvctl config database -d super points at the NEW home post-switch."
    )
