"""
test_01_os.py — OS substrate assertions for the vertical slice.

Verifies the oracle user/groups, the per-instance directory tree
(/super/{app,d01,a01,f01,r01}, /grid), ownership, and kernel parameters.
Runs against the running superdb1 container via docker exec.

GREEN in the vertical slice once 00-prep-os.yml has converged.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slice


def test_oracle_user_exists(docker_exec):
    r = docker_exec("id oracle")
    assert r.returncode == 0, f"oracle user missing: {r.stderr}"
    out = r.stdout
    assert "oracle" in out


def test_required_groups_exist(docker_exec):
    r = docker_exec("getent group oinstall dba oper backupdba dgdba kmdba")
    assert r.returncode == 0, f"groups missing: {r.stderr}"
    for grp in ("oinstall", "dba", "oper", "backupdba", "dgdba", "kmdba"):
        assert grp in r.stdout, f"group {grp} not found"


@pytest.mark.parametrize("path", [
    "/super",
    "/super/app/oracle",       # ORACLE_BASE
    "/super/app/oracle/db_home1",
    "/super/app/oracle/db_home2",
    "/super/d01",              # data
    "/super/a01",              # archive
    "/super/f01",              # flashback
    "/super/r01",              # redo
    "/grid",
])
def test_instance_directories_exist(docker_exec, path):
    r = docker_exec(f"test -d {path} && stat -c '%U:%G %n' {path}")
    assert r.returncode == 0, f"{path} missing or not a dir: {r.stderr}"
    assert "oracle:oinstall" in r.stdout, f"{path} not owned by oracle:oinstall: {r.stdout}"


def test_kernel_params_applied(docker_exec):
    # Spot-check a representative Oracle-recommended sysctl value.
    r = docker_exec("sysctl kernel.sem")
    assert r.returncode == 0, r.stderr
    # kernel.sem should be the Oracle-recommended "1024 32000 100 128".
    assert "1024 32000 100 128" in r.stdout, f"kernel.sem not set: {r.stdout}"


def test_oracle_limits_configured(docker_exec):
    r = docker_exec("cat /etc/security/limits.d/oracle.conf")
    assert r.returncode == 0, r.stderr
    assert "oracle" in r.stdout
    assert "nofile" in r.stdout
    assert "nproc" in r.stdout


def test_sudoers_entry_for_oracle(docker_exec):
    r = docker_exec("cat /etc/sudoers.d/oracle")
    assert r.returncode == 0, r.stderr
    assert "oracle ALL=(ALL) NOPASSWD: ALL" in r.stdout


def test_per_instance_env_fragment(docker_exec):
    r = docker_exec("cat /etc/profile.d/oracle-instance.d/super.sh")
    assert r.returncode == 0, r.stderr
    assert "ORACLE_BASE=/super/app/oracle" in r.stdout
    assert "ORACLE_HOME=/super/app/oracle/db_home1" in r.stdout
    assert "ORACLE_SID=super" in r.stdout
