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
    """Converge the super+duper+fluff smoke inventory before live assertions."""
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


def _instance_sql(lab_exec, name: str, sql: str, timeout: int = 60):
    oracle_home = (
        "/super/app/oracle/db_home2"
        if name == "super"
        else f"/{name}/app/oracle/db_home1"
    )
    probe = lab_exec(
        f"stat -c '%s' {oracle_home}/bin/sqlplus 2>/dev/null || echo 0"
    )
    size = int((probe.stdout or "0").strip().splitlines()[-1] or "0")
    if size == 0:
        pytest.fail(
            f"{name} is not installed; run inventory/examples/multi-instance-smoke.yml"
        )

    cmd = (
        f"export ORACLE_HOME={oracle_home} ORACLE_SID={name} && "
        "$ORACLE_HOME/bin/sqlplus -S / as sysdba <<'SQL'\n"
        "SET PAGES 0 LINESIZE 32767 FEEDBACK OFF HEADING OFF VERIFY OFF\n"
        f"{sql}\n"
        "EXIT;\n"
        "SQL"
    )
    return lab_exec(f"su - oracle -c {shlex.quote(cmd)}", timeout=timeout)


def test_super_dataguard_remains_maximum_availability(lab_exec):
    cmd = (
        "export ORACLE_HOME=/super/app/oracle/db_home2 ORACLE_SID=super && "
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
    result = _instance_sql(
        lab_exec,
        "duper",
        "SELECT name || '|' || database_role || '|' || open_mode || '|' || "
        "log_mode || '|' || flashback_on || '|' || force_logging FROM v$database;",
    )

    assert result.returncode == 0, result.stderr
    assert "DUPER|PRIMARY|READ WRITE|ARCHIVELOG|NO|YES" in result.stdout


def test_fluff_standalone_instance_is_read_write(lab_exec):
    result = _instance_sql(
        lab_exec,
        "fluff",
        "SELECT name || '|' || database_role || '|' || open_mode || '|' || "
        "log_mode || '|' || flashback_on || '|' || force_logging FROM v$database;",
    )

    assert result.returncode == 0, result.stderr
    assert "FLUFF|PRIMARY|READ WRITE|NOARCHIVELOG|NO|NO" in result.stdout


@pytest.mark.parametrize(
    ("name", "sga_target", "pga_aggregate_target"),
    [
        ("super", 2 * 1024 * 1024 * 1024, 1 * 1024 * 1024 * 1024),
        ("duper", 1 * 1024 * 1024 * 1024, 512 * 1024 * 1024),
        ("fluff", 1 * 1024 * 1024 * 1024, 512 * 1024 * 1024),
    ],
)
def test_instance_memory_parameters_match_inventory(
    lab_exec, name, sga_target, pga_aggregate_target
):
    result = _instance_sql(
        lab_exec,
        name,
        """
SELECT name || '|' || value
  FROM v$parameter
 WHERE name IN ('sga_target', 'pga_aggregate_target');
""",
    )

    assert result.returncode == 0, result.stderr
    values = dict(
        line.strip().split("|", 1)
        for line in result.stdout.splitlines()
        if "|" in line
    )
    assert values == {
        "sga_target": str(sga_target),
        "pga_aggregate_target": str(pga_aggregate_target),
    }


@pytest.mark.parametrize(
    ("name", "open_cursors"),
    [
        ("duper", "450"),
        ("fluff", "350"),
    ],
)
def test_custom_instance_parameters_match_inventory(lab_exec, name, open_cursors):
    result = _instance_sql(
        lab_exec,
        name,
        """
SELECT value
  FROM v$parameter
 WHERE name = 'open_cursors';
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == open_cursors


@pytest.mark.parametrize("name", ["duper", "fluff"])
def test_standalone_instance_files_are_filesystem_backed(lab_exec, name):
    result = _instance_sql(
        lab_exec,
        name,
        f"""
SELECT 'DATAFILES_IN_D01|' || COUNT(*) FROM v$datafile WHERE name LIKE '/{name}/d01/%';
SELECT 'TEMPFILES_IN_D01|' || COUNT(*) FROM v$tempfile WHERE name LIKE '/{name}/d01/%';
SELECT 'CONTROLFILES_IN_FS|' || COUNT(*)
  FROM v$controlfile
 WHERE name LIKE '/{name}/d01/%' OR name LIKE '/{name}/f01/%';
SELECT 'ONLINE_REDO_GROUPS|' || COUNT(DISTINCT group#) FROM v$log;
SELECT 'ONLINE_REDO_GROUPS_WITH_R01|' || COUNT(DISTINCT group#)
  FROM v$logfile
 WHERE type = 'ONLINE' AND member LIKE '/{name}/r01/%';
SELECT 'ONLINE_REDO_MEMBERS|' || COUNT(*)
  FROM v$logfile
 WHERE type = 'ONLINE';
SELECT 'ONLINE_REDO_MEMBERS_IN_R01|' || COUNT(*)
  FROM v$logfile
 WHERE type = 'ONLINE' AND member LIKE '/{name}/r01/%';
SELECT 'ASM_FILE_COUNT|' || COUNT(*) FROM (
  SELECT name path FROM v$datafile
  UNION ALL SELECT name FROM v$tempfile
  UNION ALL SELECT member FROM v$logfile
  UNION ALL SELECT name FROM v$controlfile
) WHERE path LIKE '+%';
SELECT 'DB_CREATE_FILE_DEST|' || value
  FROM v$parameter
 WHERE name = 'db_create_file_dest';
SELECT 'DB_RECOVERY_FILE_DEST|' || value
  FROM v$parameter
 WHERE name = 'db_recovery_file_dest';
SELECT 'LOG_ARCHIVE_DEST_1|' || value
  FROM v$parameter
 WHERE name = 'log_archive_dest_1';
""",
    )

    assert result.returncode == 0, result.stderr
    facts = dict(
        line.strip().split("|", 1)
        for line in result.stdout.splitlines()
        if "|" in line
    )
    assert int(facts["DATAFILES_IN_D01"]) > 0
    assert int(facts["TEMPFILES_IN_D01"]) > 0
    assert int(facts["CONTROLFILES_IN_FS"]) > 0
    assert facts["ASM_FILE_COUNT"] == "0"
    assert facts["DB_CREATE_FILE_DEST"] == f"/{name}/d01"
    assert facts["DB_RECOVERY_FILE_DEST"] == f"/{name}/f01"
    assert facts["LOG_ARCHIVE_DEST_1"] == f"LOCATION=/{name}/a01"
    assert int(facts["ONLINE_REDO_GROUPS"]) > 0
    assert facts["ONLINE_REDO_GROUPS_WITH_R01"] == facts["ONLINE_REDO_GROUPS"]
    assert facts["ONLINE_REDO_MEMBERS_IN_R01"] == facts["ONLINE_REDO_MEMBERS"]


@pytest.mark.parametrize(
    ("name", "listener", "service"),
    [
        ("duper", "LISTENER_DUPER", "duper_svc"),
        ("fluff", "LISTENER_FLUFF", "fluff_svc"),
    ],
)
def test_standalone_instance_restart_resources_are_active(
    lab_exec, name, listener, service
):
    database_status = lab_exec(f"/grid/19c/gi_home1/bin/srvctl status database -d {name}")
    assert database_status.returncode == 0, database_status.stdout + database_status.stderr
    assert "Database is running." in database_status.stdout

    listener_status = lab_exec(
        f"/grid/19c/gi_home1/bin/srvctl status listener -listener {listener}"
    )
    assert listener_status.returncode == 0, listener_status.stdout + listener_status.stderr
    assert f"Listener {listener} is enabled" in listener_status.stdout
    assert f"Listener {listener} is running" in listener_status.stdout

    service_status = lab_exec(f"/grid/19c/gi_home1/bin/srvctl status service -d {name}")
    assert service_status.returncode == 0, service_status.stdout + service_status.stderr
    assert f"Service {service} is running" in service_status.stdout


def test_duper_listener_vip_and_service_are_available(lab_exec):
    lookup = lab_exec("getent hosts duperdb.domain.is | awk '{print $1}'")
    if lookup.returncode != 0 or lookup.stdout.strip() != "192.168.87.22":
        pytest.fail("duper listener hostname is not mapped in this lab run.")

    vip_addr = lab_exec("ip -4 addr show | grep -w '192.168.87.22/24'")
    assert vip_addr.returncode == 0, vip_addr.stderr

    with socket.create_connection(("192.168.87.22", 1522), timeout=5):
        pass

    result = _instance_sql(
        lab_exec,
        "duper",
        "SELECT name FROM v$active_services WHERE name = 'duper_svc';",
    )
    assert result.returncode == 0, result.stderr
    assert "duper_svc" in result.stdout


def test_fluff_listener_vip_and_service_are_available(lab_exec):
    lookup = lab_exec("getent hosts fluffdb.domain.is | awk '{print $1}'")
    if lookup.returncode != 0 or lookup.stdout.strip() != "192.168.87.23":
        pytest.fail("fluff listener hostname is not mapped in this lab run.")

    vip_addr = lab_exec("ip -4 addr show | grep -w '192.168.87.23/24'")
    assert vip_addr.returncode == 0, vip_addr.stderr

    with socket.create_connection(("192.168.87.23", 1523), timeout=5):
        pass

    result = _instance_sql(
        lab_exec,
        "fluff",
        "SELECT name FROM v$active_services WHERE name = 'fluff_svc';",
    )
    assert result.returncode == 0, result.stderr
    assert "fluff_svc" in result.stdout
