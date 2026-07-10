"""Live checks for a primary host managing more than one database instance."""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slice
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def multi_instance_smoke_ready(lab_exec):
    """Converge the super+duper smoke inventory before live assertions."""
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    executable = str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook")
    commands = [
        [
            executable,
            "-i",
            "inventory/hosts.yml",
            "playbooks/03-create-instance.yml",
            "-e",
            "@inventory/examples/multi-instance-smoke.yml",
            "--limit",
            "superdb1",
        ],
        [
            executable,
            "-i",
            "inventory/hosts.yml",
            "playbooks/04-register-restart.yml",
            "-e",
            "@inventory/examples/multi-instance-smoke.yml",
            "--limit",
            "superdb1",
        ],
    ]

    for cmd in commands:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def _duper_sql(lab_exec, sql: str, timeout: int = 60):
    probe = lab_exec(
        "stat -c '%s' /duper/app/oracle/db_home1/bin/sqlplus 2>/dev/null || echo 0"
    )
    size = int((probe.stdout or "0").strip().splitlines()[-1] or "0")
    if size == 0:
        pytest.fail(
            "duper is not installed; run inventory/examples/multi-instance-smoke.yml"
        )

    cmd = (
        "export ORACLE_HOME=/duper/app/oracle/db_home1 ORACLE_SID=duper && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        f"{sql}\n"
        "EXIT;\n"
        "SQL"
    )
    return lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=timeout)


def test_super_dataguard_remains_maximum_availability(lab_exec):
    cmd = (
        "export ORACLE_HOME=/super/app/oracle/db_home1 ORACLE_SID=super && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        "SELECT name || '|' || database_role || '|' || open_mode || '|' || "
        "protection_mode || '|' || protection_level FROM v$database;\n"
        "EXIT;\n"
        "SQL"
    )
    result = lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=60)

    assert result.returncode == 0, result.stderr
    assert (
        "SUPER|PRIMARY|READ WRITE|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
        in result.stdout
    )


def test_duper_standalone_instance_is_read_write(lab_exec):
    result = _duper_sql(
        lab_exec,
        "SELECT name || '|' || database_role || '|' || open_mode || '|' || "
        "log_mode || '|' || flashback_on || '|' || force_logging FROM v$database;",
    )

    assert result.returncode == 0, result.stderr
    assert "DUPER|PRIMARY|READ WRITE|ARCHIVELOG|NO|YES" in result.stdout


def test_duper_listener_vip_and_service_are_available(lab_exec):
    lookup = lab_exec("getent hosts duperdb.domain.is | awk '{print $1}'")
    if lookup.returncode != 0 or lookup.stdout.strip() != "192.168.87.22":
        pytest.fail("duper listener hostname is not mapped in this lab run.")

    vip_addr = lab_exec("ip -4 addr show | grep -w '192.168.87.22/24'")
    assert vip_addr.returncode == 0, vip_addr.stderr

    with socket.create_connection(("192.168.87.22", 1522), timeout=5):
        pass

    result = _duper_sql(
        lab_exec,
        "SELECT name FROM v$active_services WHERE name = 'duper_svc';",
    )
    assert result.returncode == 0, result.stderr
    assert "duper_svc" in result.stdout
