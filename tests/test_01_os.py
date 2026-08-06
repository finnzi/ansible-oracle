"""
test_01_os.py — OS substrate assertions for the vertical slice.

Verifies the oracle user/groups, the per-instance directory tree, ownership,
and kernel parameters on the primary lab VM.

GREEN in the vertical slice once 00-prep-os.yml has converged.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.slice

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_os_prep_grows_root_disk_via_oracle_common():
    """Root headroom must be playbook-driven (repeatable), not one-off manual."""
    common_main = (REPO_ROOT / "roles/oracle_common/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    grow = (REPO_ROOT / "roles/oracle_common/tasks/grow-root.yml").read_text(
        encoding="utf-8"
    )
    defaults = (REPO_ROOT / "roles/oracle_common/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    prep = (REPO_ROOT / "playbooks/00-prep-os.yml").read_text(encoding="utf-8")
    common_sh = (REPO_ROOT / "lab/scripts/lib/common.sh").read_text(encoding="utf-8")
    lab_up = (REPO_ROOT / "lab/scripts/lab-up.sh").read_text(encoding="utf-8")

    assert "include_tasks: grow-root.yml" in common_main
    assert "growpart" in grow
    assert "lvextend" in grow
    assert "xfs_growfs" in grow
    # Role default is opt-in false; the KVM lab inventory enables growth.
    assert "oracle_common_grow_root: false" in defaults
    assert "cloud-utils-growpart" in defaults
    all_vars = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(encoding="utf-8")
    assert "oracle_common_grow_root: true" in all_vars
    assert "role: oracle_common" in prep
    assert "hosts: observer" in prep
    assert 'LAB_ROOT_DISK_SIZE="${LAB_ROOT_DISK_SIZE:-250G}"' in common_sh
    assert "lab_ensure_root_disk_size" in common_sh
    assert "lab_ensure_root_disk_size" in lab_up


def test_oracle_user_exists(lab_exec):
    r = lab_exec("id oracle")
    assert r.returncode == 0, f"oracle user missing: {r.stderr}"
    out = r.stdout
    assert "oracle" in out


def test_required_groups_exist(lab_exec):
    r = lab_exec("getent group oinstall dba oper asmadmin backupdba dgdba kmdba")
    assert r.returncode == 0, f"groups missing: {r.stderr}"
    for grp in ("oinstall", "dba", "oper", "asmadmin", "backupdba", "dgdba", "kmdba"):
        assert grp in r.stdout, f"group {grp} not found"


def test_grid_asm_disk_is_writable_by_oracle(lab_exec):
    r = lab_exec("stat -c '%U:%G %a' /dev/vdb")
    assert r.returncode == 0, f"Grid ASM disk missing: {r.stderr}"
    assert r.stdout.strip() == "oracle:asmadmin 660", (
        f"Grid ASM disk has invalid installer permissions: {r.stdout}"
    )


@pytest.mark.parametrize("path", [
    "/super",
    "/super/app/oracle",       # ORACLE_BASE
    "/super/app/oracle/dbhome_1",
    "/super/app/oracle/dbhome_2",
    "/super/d01",              # data
    "/super/a01",              # archive
    "/super/f01",              # flashback
    "/super/r01",              # redo
    "/grid",
])
def test_instance_directories_exist(lab_exec, path):
    r = lab_exec(f"test -d {path} && stat -c '%U:%G %n' {path}")
    assert r.returncode == 0, f"{path} missing or not a dir: {r.stderr}"
    assert "oracle:oinstall" in r.stdout, f"{path} not owned by oracle:oinstall: {r.stdout}"


def test_kernel_params_applied(lab_exec):
    # Spot-check a representative Oracle-recommended sysctl value.
    r = lab_exec("sysctl kernel.sem")
    assert r.returncode == 0, r.stderr
    # sysctl renders SEM arrays with tabs or spaces; normalise before checking.
    normalised = " ".join(r.stdout.split())
    # kernel.sem should be the Oracle-recommended "1024 32000 100 128".
    assert "1024 32000 100 128" in normalised, f"kernel.sem not set: {r.stdout}"


def test_oracle_limits_configured(lab_exec):
    r = lab_exec("cat /etc/security/limits.d/oracle.conf")
    assert r.returncode == 0, r.stderr
    assert "oracle" in r.stdout
    assert "nofile" in r.stdout
    assert "nproc" in r.stdout


def test_sudoers_entry_for_oracle(lab_exec):
    r = lab_exec("cat /etc/sudoers.d/oracle")
    assert r.returncode == 0, r.stderr
    assert "oracle ALL=(ALL) NOPASSWD: ALL" in r.stdout


def test_per_instance_env_fragment(lab_exec):
    r = lab_exec("cat /etc/profile.d/oracle-instance.d/super.sh")
    assert r.returncode == 0, r.stderr
    assert "ORACLE_BASE=/super/app/oracle" in r.stdout
    assert (
        "ORACLE_HOME=/super/app/oracle/dbhome_1" in r.stdout
        or "ORACLE_HOME=/super/app/oracle/dbhome_2" in r.stdout
    )
    assert "ORACLE_SID=super" in r.stdout
